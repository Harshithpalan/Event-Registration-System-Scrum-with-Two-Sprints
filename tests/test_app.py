"""
Automated Test Suite for Event Registration System
Tests all Sprint 1 & Sprint 2 user stories, business rules, and validation edge cases.
"""

import os
import tempfile
import pytest
from app import app
import database


@pytest.fixture
def client():
    """Create and configure a clean test database and Flask test client."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    app.config['DATABASE'] = db_path
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'

    with app.app_context():
        database.init_db(db_path)
        # Create initial test events
        # Event 1: Normal open event (capacity 10)
        e1_id = database.create_event(
            title="PyTest Conference 2026",
            description="Testing automated web application workflows in Flask.",
            date="2026-11-20",
            time="10:00",
            venue="Hall A, Main Campus",
            capacity=10,
            category="Technology"
        )
        # Event 2: Low capacity event (capacity 2) to test full capacity rejection
        e2_id = database.create_event(
            title="Limited Workshop 2026",
            description="Limited seats workshop.",
            date="2026-11-22",
            time="14:00",
            venue="Lab 2",
            capacity=2,
            category="Workshop"
        )
        # Event 3: Cancelled event to test cancelled registration blocking
        e3_id = database.create_event(
            title="Cancelled Tech Talk",
            description="Speaker unavailable.",
            date="2026-11-25",
            time="16:00",
            venue="Online",
            capacity=20,
            category="Seminar"
        )
        database.set_event_status(e3_id, "cancelled")

    with app.test_client() as client:
        yield client

    os.close(db_fd)
    if os.path.exists(db_path):
        os.remove(db_path)


# ==============================================================================
# Sprint 1 Tests: Attendee Workflow, Event Listing & Registration
# ==============================================================================

def test_01_homepage_displays_upcoming_events(client):
    """Test 1: Open the homepage -> Upcoming events are displayed."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"PyTest Conference 2026" in response.data
    assert b"Limited Workshop 2026" in response.data
    assert b"EventHub" in response.data


def test_02_open_existing_event_details(client):
    """Test 2: Open an existing event -> Correct event details appear."""
    response = client.get('/events/1')
    assert response.status_code == 200
    assert b"PyTest Conference 2026" in response.data
    assert b"Testing automated web application workflows in Flask." in response.data
    assert b"Hall A, Main Campus" in response.data
    assert b"10 Attendees" in response.data


def test_03_submit_valid_registration(client):
    """Test 3: Submit valid registration details -> Registration is saved and confirmed."""
    response = client.post('/events/1/register', data={
        'name': 'Sarah Connor',
        'email': 'sarah.connor@example.com',
        'phone': '1234567890'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Registration Successful!" in response.data
    assert b"Sarah Connor" in response.data
    assert b"sarah.connor@example.com" in response.data
    assert b"TKT-001-" in response.data  # Ticket code pattern


def test_04_submit_empty_registration_form(client):
    """Test 4: Submit an empty form -> Validation error is shown."""
    response = client.post('/events/1/register', data={
        'name': '',
        'email': '',
        'phone': ''
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Please enter your full name" in response.data
    assert b"Please enter a valid email address" in response.data


def test_05_register_same_email_twice_rejected(client):
    """Test 5: Register the same email twice for one event -> Duplicate rejected."""
    # First registration
    client.post('/events/1/register', data={
        'name': 'John Doe',
        'email': 'john.doe@example.com',
        'phone': '111-222-3333'
    }, follow_redirects=True)

    # Second registration with identical email
    dup_response = client.post('/events/1/register', data={
        'name': 'John Doe',
        'email': 'john.doe@example.com',
        'phone': '111-222-3333'
    }, follow_redirects=True)

    assert dup_response.status_code == 200
    assert b"already registered" in dup_response.data


def test_06_register_for_full_event_rejected(client):
    """Test 6: Register for a full event -> Registration is rejected."""
    # Event 2 has capacity = 2. Register two attendees to fill it.
    client.post('/events/2/register', data={
        'name': 'Attendee One',
        'email': 'one@example.com',
        'phone': '1111'
    })
    client.post('/events/2/register', data={
        'name': 'Attendee Two',
        'email': 'two@example.com',
        'phone': '2222'
    })

    # Third registration attempt must be rejected
    full_response = client.post('/events/2/register', data={
        'name': 'Attendee Three',
        'email': 'three@example.com',
        'phone': '3333'
    }, follow_redirects=True)

    assert full_response.status_code == 200
    assert (b"completely sold out" in full_response.data or b"full capacity" in full_response.data)


def test_06b_register_for_cancelled_event_rejected(client):
    """Business rule: Cancelled event cannot accept registrations."""
    response = client.post('/events/3/register', data={
        'name': 'Test User',
        'email': 'test@example.com'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"cancelled" in response.data


# ==============================================================================
# Sprint 2 Tests: Admin Authentication, CRUD & Capacity Guard
# ==============================================================================

def test_07_access_admin_dashboard_without_login_redirects(client):
    """Test 7: Access admin dashboard without login -> Access is denied or redirected."""
    response = client.get('/admin', follow_redirects=False)
    assert response.status_code == 302
    assert '/admin/login' in response.headers['Location']


def test_07b_admin_login_success_and_logout(client):
    """Test: Admin login with valid credentials and subsequent logout."""
    login_resp = client.post('/admin/login', data={
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)

    assert login_resp.status_code == 200
    assert b"Event Management Operations" in login_resp.data
    assert b"Logged in successfully" in login_resp.data

    # Log out
    logout_resp = client.post('/admin/logout', follow_redirects=True)
    assert logout_resp.status_code == 200
    assert b"You have been securely logged out" in logout_resp.data


def test_08_create_event_as_admin(client):
    """Test 8: Create an event as admin -> Event appears in listing."""
    # Login as admin
    client.post('/admin/login', data={'username': 'admin', 'password': 'admin123'})

    create_resp = client.post('/admin/events/new', data={
        'title': 'New Cloud Architecture Summit',
        'description': 'Exploring serverless and multi-cloud architectures.',
        'date': '2026-12-01',
        'time': '09:30',
        'venue': 'Cloud Hall 4',
        'capacity': '75',
        'category': 'Technology'
    }, follow_redirects=True)

    assert create_resp.status_code == 200
    assert b"created successfully" in create_resp.data

    # Check homepage to verify it appears
    home_resp = client.get('/')
    assert b"New Cloud Architecture Summit" in home_resp.data


def test_09_edit_event_details(client):
    """Test 9: Edit an event -> Updated details are displayed."""
    client.post('/admin/login', data={'username': 'admin', 'password': 'admin123'})

    edit_resp = client.post('/admin/events/1/edit', data={
        'title': 'PyTest Conference 2026 (Updated Edition)',
        'description': 'Updated comprehensive testing description.',
        'date': '2026-11-21',
        'time': '11:00',
        'venue': 'Auditorium Grand C',
        'capacity': '30',
        'category': 'Technology',
        'status': 'open'
    }, follow_redirects=True)

    assert edit_resp.status_code == 200
    assert b"updated successfully" in edit_resp.data

    # Verify event details page
    detail_resp = client.get('/events/1')
    assert b"PyTest Conference 2026 (Updated Edition)" in detail_resp.data
    assert b"Auditorium Grand C" in detail_resp.data
    assert b"30 Attendees" in detail_resp.data


def test_10_cancel_and_delete_event(client):
    """Test 10: Delete or cancel an event -> Event is updated/removed."""
    client.post('/admin/login', data={'username': 'admin', 'password': 'admin123'})

    # Cancel event 1
    cancel_resp = client.post('/admin/events/1/cancel', follow_redirects=True)
    assert cancel_resp.status_code == 200
    assert b"has been cancelled" in cancel_resp.data

    # Delete event 3
    delete_resp = client.post('/admin/events/3/delete', follow_redirects=True)
    assert delete_resp.status_code == 200
    assert b"permanently deleted" in delete_resp.data

    # Event 3 should no longer exist
    detail_resp = client.get('/events/3')
    assert b"not found" in detail_resp.data or detail_resp.status_code == 302


def test_11_open_event_with_no_registrations_shows_empty_state(client):
    """Test 11: Open an event with no registrations -> Empty state is displayed."""
    client.post('/admin/login', data={'username': 'admin', 'password': 'admin123'})

    # Event 1 was updated and has no registrations in this isolated test
    roster_resp = client.get('/admin/events/1/registrations')
    assert roster_resp.status_code == 200
    assert b"No Registrations Yet" in roster_resp.data


def test_12_reduce_capacity_below_existing_registrations_rejected(client):
    """Test 12: Try to reduce capacity below existing registrations -> Update is rejected."""
    # Register 2 attendees for Event 1
    client.post('/events/1/register', data={'name': 'User A', 'email': 'usera@example.com'})
    client.post('/events/1/register', data={'name': 'User B', 'email': 'userb@example.com'})

    client.post('/admin/login', data={'username': 'admin', 'password': 'admin123'})

    # Attempt to reduce capacity from 10 down to 1 (which is less than 2 registered)
    reduce_resp = client.post('/admin/events/1/edit', data={
        'title': 'PyTest Conference 2026',
        'description': 'Testing reduction',
        'date': '2026-11-20',
        'time': '10:00',
        'venue': 'Hall A',
        'capacity': '1',  # ILLEGAL: 2 already registered!
        'category': 'Technology',
        'status': 'open'
    }, follow_redirects=True)

    assert reduce_resp.status_code == 200
    assert b"Capacity cannot be reduced" in reduce_resp.data
