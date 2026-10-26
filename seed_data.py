"""
Database seeding script with realistic sample events, attendees, and registrations.
Provides instant showcase data for Sprint 1 & Sprint 2 demonstrations.
"""

import os
import sqlite3
from datetime import datetime, timedelta
from database import init_db, get_db, register_attendee_for_event, DEFAULT_DB_PATH


def seed_database(db_path=DEFAULT_DB_PATH):
    """Seed the database with diverse events and registrations."""
    print(f"Initializing database at: {db_path}")
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    # Check if events already exist
    cursor.execute("SELECT COUNT(*) FROM events;")
    if cursor.fetchone()[0] > 0:
        print("Database already contains events. Skipping seed.")
        conn.close()
        return

    now = datetime.now()
    d1 = (now + timedelta(days=5)).strftime("%Y-%m-%d")
    d2 = (now + timedelta(days=12)).strftime("%Y-%m-%d")
    d3 = (now + timedelta(days=20)).strftime("%Y-%m-%d")
    d4 = (now + timedelta(days=30)).strftime("%Y-%m-%d")
    d_past = (now - timedelta(days=10)).strftime("%Y-%m-%d")

    sample_events = [
        (
            "Global AI & Cloud Innovation Summit 2026",
            "Explore cutting-edge advancements in Generative AI, cloud architectures, and machine learning scalability with world-class keynote speakers and live tech demos.",
            d1,
            "10:00",
            "Grand Tech Auditorium, Tech Park, City Center",
            80,
            "Technology",
            "open"
        ),
        (
            "Agile Scrum & Modern DevOps Hands-on Workshop",
            "Deep dive into sprint planning, user story grooming, sprint retrospectives, CI/CD pipelines, and practical automated testing workflows.",
            d2,
            "14:00",
            "Innovation Lab 3, Computer Science Block",
            3,  # Low capacity so we can fill it to demonstrate SOLD OUT
            "Workshop",
            "open"
        ),
        (
            "National Student Hackathon: CodeSprint 2026",
            "A 24-hour intense coding hackathon focusing on Sustainable Tech, Fintech, and AI Healthcare solutions with $10,000 in grand prizes.",
            d3,
            "09:00",
            "Campus Gymnasium & Hackerspace",
            150,
            "Cultural",
            "open"
        ),
        (
            "Cybersecurity & Cloud Defense Seminar",
            "Learn offensive and defensive cybersecurity strategies, zero-trust cloud infrastructure, and modern threat mitigation techniques.",
            d4,
            "11:30",
            "Seminar Hall B, Engineering Complex",
            50,
            "Seminar",
            "open"
        ),
        (
            "Legacy Systems Migration & Modernization (Cancelled)",
            "Step-by-step strategies for refactoring legacy monolithic applications into modern microservices. (Note: Cancelled due to speaker scheduling conflict)",
            d2,
            "16:00",
            "Online Webinar Hall",
            40,
            "Technology",
            "cancelled"
        ),
        (
            "Foundations of Python & Git Version Control (Completed)",
            "A beginner-friendly bootcamp covering Python fundamentals, virtual environments, and collaborative Git workflow with GitHub.",
            d_past,
            "10:00",
            "Lab 101, Science Block",
            40,
            "Workshop",
            "completed"
        )
    ]

    for ev in sample_events:
        cursor.execute(
            """
            INSERT INTO events (title, description, date, time, venue, capacity, category, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            ev
        )

    conn.commit()
    conn.close()

    print("Sample events inserted successfully.")

    # Now register attendees using the database transaction logic
    # Let's fill the workshop (Event ID 2) completely to 3/3 capacity!
    attendees_to_register = [
        # For Event 1 (AI Summit)
        (1, "Alice Morgan", "alice.morgan@example.com", "+1-555-0101"),
        (1, "David Chen", "david.chen@example.com", "+1-555-0102"),
        (1, "Sophia Patel", "sophia.patel@example.com", "+1-555-0103"),
        # For Event 2 (Workshop: 3 capacity -> fills it completely)
        (2, "Michael Scott", "michael.scott@example.com", "+1-555-0201"),
        (2, "Pam Beesly", "pam.beesly@example.com", "+1-555-0202"),
        (2, "Jim Halpert", "jim.halpert@example.com", "+1-555-0203"),
        # For Event 3 (Hackathon)
        (3, "Alex Turner", "alex.turner@example.com", "+1-555-0301"),
        (3, "Elena Rostova", "elena.rostova@example.com", "+1-555-0302")
    ]

    # We need a dummy Flask app context or direct sqlite connection for register_attendee_for_event
    from flask import Flask
    app = Flask(__name__)
    app.config['DATABASE'] = db_path

    with app.app_context():
        for ev_id, name, email, phone in attendees_to_register:
            try:
                res = register_attendee_for_event(ev_id, name, email, phone)
                print(f"Registered {name} for Event {ev_id} (Ticket: {res['ticket_code']})")
            except Exception as e:
                print(f"Failed to register {name}: {e}")

    print("\nDatabase seeding completed successfully!")
    print("Default Admin Credentials: username='admin', password='admin123'")


if __name__ == '__main__':
    seed_database()
