"""
Database management module for Event Registration System.
Handles SQLite connections, schema initialization, parameterized queries,
and atomic business logic transactions.
"""

import os
import sqlite3
import uuid
from datetime import datetime
from flask import g, current_app
from werkzeug.security import generate_password_hash, check_password_hash

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'events.db')


def get_db_path():
    """Return the active database path from Flask config or default."""
    if current_app and 'DATABASE' in current_app.config:
        return current_app.config['DATABASE']
    return DEFAULT_DB_PATH


def get_db(custom_path=None):
    """
    Open a unique database connection per request context.
    Row factory is set to sqlite3.Row for dict-like access.
    """
    db_path = custom_path or get_db_path()

    # Ensure parent directory exists
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    if 'db' not in g or g.get('db_path') != db_path:
        conn = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=10.0,
            isolation_level=None  # Enable explicit transaction control
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")  # Fast concurrent reads/writes
        g.db = conn
        g.db_path = db_path

    return g.db


def close_db(e=None):
    """Close the database connection on request teardown."""
    db = g.pop('db', None)
    g.pop('db_path', None)
    if db is not None:
        db.close()


def init_db(custom_path=None):
    """Initialize database tables using schema.sql and seed default admin."""
    db_path = custom_path or get_db_path()
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")

    schema_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    with open(schema_file, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())

    # Create default admin if none exists
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM admins WHERE username = 'admin';")
    if not cursor.fetchone():
        hashed = generate_password_hash('admin123')
        cursor.execute(
            "INSERT INTO admins (username, password_hash, role) VALUES (?, ?, ?);",
            ('admin', hashed, 'admin')
        )
        conn.commit()

    conn.close()


# ==========================================
# EVENT QUERIES & BUSINESS LOGIC
# ==========================================

def get_all_events(include_cancelled=False, search_query=None, category=None):
    """
    Fetch all events along with their live confirmed registration count
    and calculated available seats.
    """
    db = get_db()
    query = """
        SELECT 
            e.*,
            COALESCE(COUNT(r.id), 0) AS registered_count,
            (e.capacity - COALESCE(COUNT(r.id), 0)) AS available_seats
        FROM events e
        LEFT JOIN registrations r 
            ON e.id = r.event_id AND r.status = 'confirmed'
        WHERE 1=1
    """
    params = []

    if not include_cancelled:
        query += " AND e.status != 'cancelled'"

    if search_query:
        query += " AND (e.title LIKE ? OR e.description LIKE ? OR e.venue LIKE ?)"
        term = f"%{search_query.strip()}%"
        params.extend([term, term, term])

    if category and category != 'All':
        query += " AND e.category = ?"
        params.append(category)

    query += " GROUP BY e.id ORDER BY e.date ASC, e.time ASC;"
    cursor = db.execute(query, params)
    return cursor.fetchall()


def get_event_by_id(event_id):
    """Fetch single event with registration counts."""
    db = get_db()
    query = """
        SELECT 
            e.*,
            COALESCE(COUNT(r.id), 0) AS registered_count,
            (e.capacity - COALESCE(COUNT(r.id), 0)) AS available_seats
        FROM events e
        LEFT JOIN registrations r 
            ON e.id = r.event_id AND r.status = 'confirmed'
        WHERE e.id = ?
        GROUP BY e.id;
    """
    return db.execute(query, (event_id,)).fetchone()


def create_event(title, description, date, time, venue, capacity, category='Technology'):
    """Create a new event record."""
    title = title.strip()
    description = description.strip()
    venue = venue.strip()
    capacity = int(capacity)

    if capacity <= 0:
        raise ValueError("Event capacity must be greater than zero.")

    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO events (title, description, date, time, venue, capacity, category, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'open');
        """,
        (title, description, date, time, venue, capacity, category)
    )
    return cursor.lastrowid


def update_event(event_id, title, description, date, time, venue, capacity, category, status='open'):
    """
    Update an event.
    Enforces business rule: Capacity cannot be reduced below current confirmed registrations.
    """
    capacity = int(capacity)
    if capacity <= 0:
        raise ValueError("Event capacity must be greater than zero.")

    db = get_db()
    event = get_event_by_id(event_id)
    if not event:
        raise ValueError("Event not found.")

    current_registrations = event['registered_count']
    if capacity < current_registrations:
        raise ValueError(
            f"Capacity cannot be reduced to {capacity}. There are already "
            f"{current_registrations} confirmed registrations for this event."
        )

    db.execute(
        """
        UPDATE events 
        SET title = ?, description = ?, date = ?, time = ?, venue = ?, 
            capacity = ?, category = ?, status = ?
        WHERE id = ?;
        """,
        (title.strip(), description.strip(), date, time, venue.strip(), capacity, category, status, event_id)
    )
    return True


def delete_event(event_id):
    """Delete an event and safely cascade delete registrations."""
    db = get_db()
    db.execute("DELETE FROM events WHERE id = ?;", (event_id,))
    return True


def set_event_status(event_id, status):
    """Update event status (e.g. 'open', 'cancelled', 'completed')."""
    if status not in ('open', 'cancelled', 'completed'):
        raise ValueError("Invalid event status.")
    db = get_db()
    db.execute("UPDATE events SET status = ? WHERE id = ?;", (status, event_id))
    return True


# ==========================================
# ATTENDEE & REGISTRATION LOGIC
# ==========================================

def register_attendee_for_event(event_id, name, email, phone=None):
    """
    Atomic event registration transaction:
    1. Validates inputs & email format.
    2. Validates event existence and open status.
    3. Atomically checks capacity constraint to prevent overbooking.
    4. Upserts attendee record by normalized email.
    5. Checks duplicate registration for this event and email.
    6. Issues unique ticket code and records registration.
    """
    name = name.strip()
    email = email.strip().lower()
    phone = phone.strip() if phone else None

    if not name:
        raise ValueError("Full name is required.")
    if not email or '@' not in email or '.' not in email:
        raise ValueError("Please provide a valid email address.")

    db = get_db()

    # BEGIN EXCLUSIVE TRANSACTION to guarantee atomicity and prevent race conditions
    db.execute("BEGIN IMMEDIATE;")
    try:
        # 1. Fetch event inside transaction
        cursor = db.execute("SELECT * FROM events WHERE id = ?;", (event_id,))
        event = cursor.fetchone()
        if not event:
            raise ValueError("The requested event does not exist.")

        if event['status'] == 'cancelled':
            raise ValueError("This event has been cancelled and is no longer accepting registrations.")

        if event['status'] == 'completed':
            raise ValueError("This event has already taken place.")

        # Optional check: Past event date validation
        try:
            event_datetime = datetime.strptime(f"{event['date']} {event['time']}", "%Y-%m-%d %H:%M")
            if event_datetime < datetime.now():
                raise ValueError("This event is in the past and registrations are closed.")
        except ValueError as dt_err:
            # If date format is different or past error raised, handle appropriately
            if "in the past" in str(dt_err):
                raise

        # 2. Check current confirmed registrations count
        cursor = db.execute(
            "SELECT COUNT(*) AS count FROM registrations WHERE event_id = ? AND status = 'confirmed';",
            (event_id,)
        )
        count_row = cursor.fetchone()
        current_count = count_row['count'] if count_row else 0

        if current_count >= event['capacity']:
            raise ValueError("Sorry, this event is completely sold out! Maximum capacity reached.")

        # 3. Find or create Attendee
        cursor = db.execute("SELECT id FROM attendees WHERE email = ?;", (email,))
        attendee_row = cursor.fetchone()

        if attendee_row:
            attendee_id = attendee_row['id']
            # Update name/phone if changed
            db.execute("UPDATE attendees SET name = ?, phone = ? WHERE id = ?;", (name, phone, attendee_id))
        else:
            cursor = db.execute(
                "INSERT INTO attendees (name, email, phone) VALUES (?, ?, ?);",
                (name, email, phone)
            )
            attendee_id = cursor.lastrowid

        # 4. Check for duplicate registration
        cursor = db.execute(
            "SELECT id, ticket_code FROM registrations WHERE event_id = ? AND attendee_id = ? AND status = 'confirmed';",
            (event_id, attendee_id)
        )
        existing_reg = cursor.fetchone()
        if existing_reg:
            raise ValueError(
                f"You are already registered for this event with ticket code #{existing_reg['ticket_code']}."
            )

        # 5. Generate ticket code: EVT-{event_id}-{unique_hash}
        ticket_code = f"TKT-{event_id:03d}-{uuid.uuid4().hex[:6].upper()}"

        cursor = db.execute(
            """
            INSERT INTO registrations (event_id, attendee_id, ticket_code, status)
            VALUES (?, ?, ?, 'confirmed');
            """,
            (event_id, attendee_id, ticket_code)
        )
        registration_id = cursor.lastrowid

        # Commit transaction
        db.execute("COMMIT;")
        return {
            'registration_id': registration_id,
            'ticket_code': ticket_code,
            'event_id': event_id,
            'attendee_id': attendee_id
        }

    except Exception:
        db.execute("ROLLBACK;")
        raise


def get_registration_details(registration_id):
    """Retrieve full registration info with event & attendee details."""
    db = get_db()
    query = """
        SELECT 
            r.id AS registration_id,
            r.ticket_code,
            r.registered_at,
            r.status AS registration_status,
            e.id AS event_id,
            e.title AS event_title,
            e.description AS event_description,
            e.date AS event_date,
            e.time AS event_time,
            e.venue AS event_venue,
            e.category AS event_category,
            a.id AS attendee_id,
            a.name AS attendee_name,
            a.email AS attendee_email,
            a.phone AS attendee_phone
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN attendees a ON r.attendee_id = a.id
        WHERE r.id = ?;
    """
    return db.execute(query, (registration_id,)).fetchone()


def get_registration_by_ticket(ticket_code):
    """Retrieve full registration info by ticket code."""
    db = get_db()
    query = """
        SELECT 
            r.id AS registration_id,
            r.ticket_code,
            r.registered_at,
            r.status AS registration_status,
            e.id AS event_id,
            e.title AS event_title,
            e.description AS event_description,
            e.date AS event_date,
            e.time AS event_time,
            e.venue AS event_venue,
            e.category AS event_category,
            a.id AS attendee_id,
            a.name AS attendee_name,
            a.email AS attendee_email,
            a.phone AS attendee_phone
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN attendees a ON r.attendee_id = a.id
        WHERE r.ticket_code = ?;
    """
    return db.execute(query, (ticket_code,)).fetchone()


def get_attendees_for_event(event_id):
    """Fetch attendee list registered for a specific event."""
    db = get_db()
    query = """
        SELECT 
            r.id AS registration_id,
            r.ticket_code,
            r.registered_at,
            r.status AS registration_status,
            a.id AS attendee_id,
            a.name AS attendee_name,
            a.email AS attendee_email,
            a.phone AS attendee_phone
        FROM registrations r
        JOIN attendees a ON r.attendee_id = a.id
        WHERE r.event_id = ?
        ORDER BY r.registered_at DESC;
    """
    return db.execute(query, (event_id,)).fetchall()


def get_all_registrations(limit=100):
    """Fetch all registrations across all events for admin overview."""
    db = get_db()
    query = """
        SELECT 
            r.id AS registration_id,
            r.ticket_code,
            r.registered_at,
            r.status AS registration_status,
            e.id AS event_id,
            e.title AS event_title,
            e.date AS event_date,
            e.time AS event_time,
            a.name AS attendee_name,
            a.email AS attendee_email
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN attendees a ON r.attendee_id = a.id
        ORDER BY r.registered_at DESC
        LIMIT ?;
    """
    return db.execute(query, (limit,)).fetchall()


# ==========================================
# ADMIN & DASHBOARD METRICS
# ==========================================

def get_admin_by_username(username):
    """Fetch admin credentials by username."""
    db = get_db()
    return db.execute(
        "SELECT * FROM admins WHERE username = ? COLLATE NOCASE;",
        (username.strip(),)
    ).fetchone()


def get_dashboard_stats():
    """Calculate dashboard KPIs for administrators."""
    db = get_db()

    total_events = db.execute("SELECT COUNT(*) AS count FROM events;").fetchone()['count']
    active_events = db.execute("SELECT COUNT(*) AS count FROM events WHERE status = 'open';").fetchone()['count']
    total_registrations = db.execute(
        "SELECT COUNT(*) AS count FROM registrations WHERE status = 'confirmed';"
    ).fetchone()['count']
    total_attendees = db.execute("SELECT COUNT(*) AS count FROM attendees;").fetchone()['count']

    # Sold out events
    sold_out_count = db.execute("""
        SELECT COUNT(*) AS count FROM (
            SELECT e.id
            FROM events e
            JOIN registrations r ON e.id = r.event_id AND r.status = 'confirmed'
            WHERE e.status = 'open'
            GROUP BY e.id, e.capacity
            HAVING COUNT(r.id) >= e.capacity
        );
    """).fetchone()['count']

    return {
        'total_events': total_events,
        'active_events': active_events,
        'total_registrations': total_registrations,
        'total_attendees': total_attendees,
        'sold_out_count': sold_out_count
    }
