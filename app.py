"""
Event Registration System - Flask Web Application
Iterative Scrum MVP with Attendee Registration & Full Admin Management.
"""

import os
import re
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, abort, jsonify
)
from werkzeug.security import check_password_hash, generate_password_hash
import database

app = Flask(__name__)

# Application Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'event-registration-scrum-secret-key-2026')
app.config['DATABASE'] = os.path.join(app.instance_path, 'events.db')

# Ensure instance folder exists and initialize DB if needed
os.makedirs(app.instance_path, exist_ok=True)
with app.app_context():
    database.init_db()


# Database connection teardown
@app.teardown_appcontext
def close_connection(exception):
    database.close_db(exception)


# -----------------------------------------------------------------------------
# Authentication & Authorization Helpers
# -----------------------------------------------------------------------------

def login_required(f):
    """Decorator to protect administrative endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash("Administrator login required to access this resource.", "warning")
            return redirect(url_for('admin_login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


# Context processor for templates (e.g. current year, session info)
@app.context_processor
def inject_global_data():
    return {
        'is_admin': 'admin_id' in session,
        'admin_username': session.get('admin_username', ''),
        'app_name': 'EventHub'
    }


# Template filter for formatting dates nicely
@app.template_filter('format_date')
def format_date_filter(value):
    if not value:
        return ""
    try:
        from datetime import datetime
        dt = datetime.strptime(value, "%Y-%m-%d")
        return dt.strftime("%B %d, %Y")
    except Exception:
        return value


# -----------------------------------------------------------------------------
# Attendee & Public Routes (Sprint 1 Core Deliverables)
# -----------------------------------------------------------------------------

@app.route('/')
def index():
    """
    US01: Display upcoming events.
    Supports real-time search term and category filtering.
    """
    search_query = request.args.get('q', '').strip()
    category = request.args.get('category', 'All')

    events = database.get_all_events(
        include_cancelled=True,
        search_query=search_query if search_query else None,
        category=category if category != 'All' else None
    )

    stats = database.get_dashboard_stats()
    return render_template(
        'index.html',
        events=events,
        search_query=search_query,
        selected_category=category,
        stats=stats
    )


@app.route('/events/<int:event_id>')
def event_detail(event_id):
    """
    US02: Display detailed event specifications, capacity status, and location.
    """
    event = database.get_event_by_id(event_id)
    if not event:
        flash("The requested event was not found.", "danger")
        return redirect(url_for('index'))

    return render_template('event_detail.html', event=event)


@app.route('/events/<int:event_id>/register', methods=['GET', 'POST'])
def register(event_id):
    """
    US03 & US05: Event Registration with validation, duplicate check, and capacity check.
    """
    event = database.get_event_by_id(event_id)
    if not event:
        flash("The event you are trying to register for does not exist.", "danger")
        return redirect(url_for('index'))

    if event['status'] == 'cancelled':
        flash("This event has been cancelled and cannot accept new registrations.", "warning")
        return redirect(url_for('event_detail', event_id=event_id))

    if event['available_seats'] <= 0:
        flash("This event has reached full capacity. No additional seats are available.", "danger")
        return redirect(url_for('event_detail', event_id=event_id))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()

        # Validation
        errors = []
        if not name or len(name) < 2:
            errors.append("Please enter your full name (minimum 2 characters).")

        email_pattern = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
        if not email or not re.match(email_pattern, email):
            errors.append("Please enter a valid email address.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template('register.html', event=event, name=name, email=email, phone=phone)

        # Process registration atomically
        try:
            result = database.register_attendee_for_event(
                event_id=event_id,
                name=name,
                email=email,
                phone=phone
            )
            flash("Registration successful! Your ticket has been confirmed.", "success")
            return redirect(url_for('confirmation', registration_id=result['registration_id']))

        except ValueError as val_err:
            flash(str(val_err), "danger")
            return render_template('register.html', event=event, name=name, email=email, phone=phone)
        except Exception as e:
            flash("An unexpected error occurred while processing your registration. Please try again.", "danger")
            return render_template('register.html', event=event, name=name, email=email, phone=phone)

    return render_template('register.html', event=event)


@app.route('/confirmation/<int:registration_id>')
def confirmation(registration_id):
    """
    US04: Show registration confirmation ticket with details.
    """
    reg = database.get_registration_details(registration_id)
    if not reg:
        flash("Registration confirmation not found.", "danger")
        return redirect(url_for('index'))

    return render_template('confirmation.html', registration=reg)


# -----------------------------------------------------------------------------
# Admin Authentication & Dashboard Routes (Sprint 2 Core Deliverables)
# -----------------------------------------------------------------------------

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """
    US06: Admin authentication with secure session handling.
    """
    if 'admin_id' in session:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash("Please enter both username and password.", "danger")
            return render_template('admin_login.html', username=username)

        admin = database.get_admin_by_username(username)
        if admin and check_password_hash(admin['password_hash'], password):
            session['admin_id'] = admin['id']
            session['admin_username'] = admin['username']
            session['admin_role'] = admin['role']
            flash(f"Welcome back, {admin['username']}! Logged in successfully.", "success")

            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid administrator credentials. Please check username and password.", "danger")
            return render_template('admin_login.html', username=username)

    return render_template('admin_login.html')


@app.route('/admin/logout', methods=['POST', 'GET'])
def admin_logout():
    """Log out admin session."""
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    session.pop('admin_role', None)
    flash("You have been securely logged out.", "info")
    return redirect(url_for('admin_login'))


@app.route('/admin')
@login_required
def admin_dashboard():
    """
    US09: Admin dashboard displaying events, attendee counts, and KPI statistics.
    """
    events = database.get_all_events(include_cancelled=True)
    stats = database.get_dashboard_stats()
    recent_registrations = database.get_all_registrations(limit=15)

    return render_template(
        'admin_dashboard.html',
        events=events,
        stats=stats,
        recent_registrations=recent_registrations
    )


@app.route('/admin/events/new', methods=['GET', 'POST'])
@login_required
def admin_create_event():
    """
    US07: Create a new event.
    """
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        date = request.form.get('date', '').strip()
        time = request.form.get('time', '').strip()
        venue = request.form.get('venue', '').strip()
        capacity = request.form.get('capacity', '').strip()
        category = request.form.get('category', 'Technology')

        # Validation
        errors = []
        if not title:
            errors.append("Event title is required.")
        if not description:
            errors.append("Event description is required.")
        if not date:
            errors.append("Event date is required.")
        if not time:
            errors.append("Event time is required.")
        if not venue:
            errors.append("Event venue is required.")
        try:
            cap_val = int(capacity)
            if cap_val <= 0:
                errors.append("Capacity must be greater than zero.")
        except (ValueError, TypeError):
            errors.append("Capacity must be a positive whole number.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template('admin_event_form.html', is_edit=False, event=request.form)

        try:
            event_id = database.create_event(
                title=title,
                description=description,
                date=date,
                time=time,
                venue=venue,
                capacity=int(capacity),
                category=category
            )
            flash(f"Event '{title}' created successfully!", "success")
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            flash(f"Error creating event: {str(e)}", "danger")
            return render_template('admin_event_form.html', is_edit=False, event=request.form)

    return render_template('admin_event_form.html', is_edit=False, event={})


@app.route('/admin/events/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_event(event_id):
    """
    US07: Edit event with capacity constraint guard.
    """
    event = database.get_event_by_id(event_id)
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        date = request.form.get('date', '').strip()
        time = request.form.get('time', '').strip()
        venue = request.form.get('venue', '').strip()
        capacity = request.form.get('capacity', '').strip()
        category = request.form.get('category', 'Technology')
        status = request.form.get('status', 'open')

        # Validation
        errors = []
        if not title:
            errors.append("Event title is required.")
        if not description:
            errors.append("Event description is required.")
        if not date:
            errors.append("Event date is required.")
        if not time:
            errors.append("Event time is required.")
        if not venue:
            errors.append("Event venue is required.")
        try:
            cap_val = int(capacity)
            if cap_val <= 0:
                errors.append("Capacity must be greater than zero.")
        except (ValueError, TypeError):
            errors.append("Capacity must be a positive whole number.")

        if errors:
            for error in errors:
                flash(error, "danger")
            event_data = dict(request.form)
            event_data['id'] = event_id
            event_data['registered_count'] = event['registered_count']
            return render_template('admin_event_form.html', is_edit=True, event=event_data)

        try:
            database.update_event(
                event_id=event_id,
                title=title,
                description=description,
                date=date,
                time=time,
                venue=venue,
                capacity=int(capacity),
                category=category,
                status=status
            )
            flash(f"Event '{title}' updated successfully!", "success")
            return redirect(url_for('admin_dashboard'))
        except ValueError as val_err:
            flash(str(val_err), "danger")
            event_data = dict(request.form)
            event_data['id'] = event_id
            event_data['registered_count'] = event['registered_count']
            return render_template('admin_event_form.html', is_edit=True, event=event_data)
        except Exception as e:
            flash(f"Error updating event: {str(e)}", "danger")
            event_data = dict(request.form)
            event_data['id'] = event_id
            event_data['registered_count'] = event['registered_count']
            return render_template('admin_event_form.html', is_edit=True, event=event_data)

    return render_template('admin_event_form.html', is_edit=True, event=event)


@app.route('/admin/events/<int:event_id>/cancel', methods=['POST'])
@login_required
def admin_cancel_event(event_id):
    """
    US08: Cancel an event (closes registrations while preserving attendee history).
    """
    event = database.get_event_by_id(event_id)
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for('admin_dashboard'))

    database.set_event_status(event_id, 'cancelled')
    flash(f"Event '{event['title']}' has been cancelled.", "warning")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/events/<int:event_id>/delete', methods=['POST'])
@login_required
def admin_delete_event(event_id):
    """
    US08: Delete an event and safely cascade associated registrations.
    """
    event = database.get_event_by_id(event_id)
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for('admin_dashboard'))

    database.delete_event(event_id)
    flash(f"Event '{event['title']}' was permanently deleted.", "info")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/events/<int:event_id>/registrations')
@login_required
def admin_event_registrations(event_id):
    """
    US09: View detailed attendee list for a specific event.
    """
    event = database.get_event_by_id(event_id)
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for('admin_dashboard'))

    attendees = database.get_attendees_for_event(event_id)
    return render_template('admin_registrations.html', event=event, attendees=attendees)


# -----------------------------------------------------------------------------
# Error Handlers
# -----------------------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


if __name__ == '__main__':
    # Run development server
    app.run(host='127.0.0.1', port=5000, debug=True)
