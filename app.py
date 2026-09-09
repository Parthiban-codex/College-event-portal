import os
import uuid
import csv
import io
import qrcode
from datetime import datetime, date, time
from functools import wraps
from PIL import Image

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, send_file, Response
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from database import get_db_connection, init_db, ensure_upload_dirs

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directories exist
ensure_upload_dirs()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def generate_ticket_qr(ticket_code):
    """Generate high-contrast QR code for digital Admit-One pass."""
    filename = f"{ticket_code}.png"
    filepath = os.path.join(Config.TICKETS_FOLDER, filename)
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=3,
    )
    qr.add_data(ticket_code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F172A", back_color="white")
    img.save(filepath)
    return filename

def generate_payment_qr(upi_id, event_title):
    """Generate dynamic UPI QR code for paid event tickets."""
    unique_id = uuid.uuid4().hex[:8]
    filename = f"upi_{unique_id}.png"
    filepath = os.path.join(Config.PAYMENT_QRS_FOLDER, filename)
    
    clean_title = "".join(c for c in event_title if c.isalnum() or c in (' ', '-', '_')).strip()
    upi_payload = f"upi://pay?pa={upi_id}&pn=College%20Events&tn={clean_title.replace(' ', '%20')}&cu=INR"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(upi_payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1D4ED8", back_color="white")
    img.save(filepath)
    return filename

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'student':
            flash('Access restricted to enrolled students.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Faculty / Organizer administration access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
@app.context_processor
def inject_global_data():
    current_user = None
    unread_notifs = 0
    
    if 'user_id' in session:
        db = get_db_connection()
        try:
            with db.cursor() as cursor:
                if session.get('role') == 'student':
                    cursor.execute("SELECT * FROM students WHERE id = %s", (session['user_id'],))
                    current_user = cursor.fetchone()
                    if current_user:
                        current_user['user_type'] = 'student'
                    cursor.execute("SELECT COUNT(*) as count FROM notifications WHERE target_audience IN ('all', 'registered_students')")
                    unread_notifs = cursor.fetchone()['count']
                elif session.get('role') == 'admin':
                    cursor.execute("SELECT * FROM admins WHERE id = %s", (session['user_id'],))
                    current_user = cursor.fetchone()
                    if current_user:
                        current_user['user_type'] = 'admin'
        finally:
            db.close()
            
    categories = ['Hackathon', 'Cultural Fest', 'Workshop', 'Tech & Robotics', 'Music & Arts', 'Gaming', 'Seminar', 'Sports']
    return dict(current_user=current_user, unread_notifications_count=unread_notifs, categories=categories)

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%B %d, %Y'):
    if value is None or value == '':
        return 'TBD'
    if isinstance(value, str):
        try:
            value = datetime.strptime(value[:10], '%Y-%m-%d')
        except ValueError:
            return value
    if isinstance(value, (datetime, date)):
        return value.strftime(format)
    return str(value)

@app.template_filter('timeformat')
def timeformat(value, format='%I:%M %p'):
    if value is None or value == '':
        return ''
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%H:%M:%S').time()
        except ValueError:
            return value
    if isinstance(value, (time, datetime)):
        return value.strftime(format)
    if hasattr(value, 'total_seconds'):
        total_seconds = int(value.total_seconds())
        hours = (total_seconds // 3600) % 24
        minutes = (total_seconds % 3600) // 60
        t = time(hours, minutes)
        return t.strftime(format)
    return str(value)
@app.route('/')
def index():
    category = request.args.get('category', 'all')
    search = request.args.get('search', '').strip()
    fee_type = request.args.get('fee_type', 'all')
    
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            query = """
                SELECT e.*, v.name as venue_name, v.building as venue_building,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status IN ('registered', 'approved', 'attended')) as registered_count
                FROM events e
                LEFT JOIN venues v ON e.venue_id = v.id
                WHERE 1=1
            """
            params = []
            
            if category and category != 'all':
                query += " AND e.category = %s"
                params.append(category)
                
            if search:
                query += " AND (e.title LIKE %s OR e.description LIKE %s OR v.name LIKE %s)"
                term = f"%{search}%"
                params.extend([term, term, term])
                
            if fee_type == 'free':
                query += " AND e.fee = 0"
            elif fee_type == 'paid':
                query += " AND e.fee > 0"
                
            query += " ORDER BY e.event_date ASC, e.start_time ASC"
            cursor.execute(query, params)
            events = cursor.fetchall()
            
            cursor.execute("SELECT * FROM venues ORDER BY name")
            venues = cursor.fetchall()
            
            cursor.execute("SELECT COUNT(*) as total_events FROM events WHERE status != 'cancelled'")
            total_events = cursor.fetchone()['total_events']
            
            cursor.execute("SELECT COUNT(*) as total_registrations FROM registrations WHERE status != 'cancelled'")
            total_registrations = cursor.fetchone()['total_registrations']
            
            cursor.execute("SELECT COUNT(*) as total_students FROM students")
            total_students = cursor.fetchone()['total_students']
    finally:
        db.close()
        
    return render_template(
        'index.html',
        events=events,
        venues=venues,
        selected_category=category,
        search_query=search,
        fee_type=fee_type,
        stats={
            'total_events': total_events,
            'total_registrations': total_registrations,
            'total_students': total_students
        }
    )

@app.route('/event/<int:event_id>')
def event_details(event_id):
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, v.name as venue_name, v.building as venue_building, v.capacity as venue_capacity, v.location_details,
                       a.name as organizer_name, a.email as organizer_email, a.role as organizer_role,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status IN ('registered', 'approved', 'attended')) as registered_count,
                       (SELECT AVG(rating) FROM feedback f WHERE f.event_id = e.id) as avg_rating,
                       (SELECT COUNT(*) FROM feedback f WHERE f.event_id = e.id) as feedback_count
                FROM events e
                LEFT JOIN venues v ON e.venue_id = v.id
                LEFT JOIN admins a ON e.created_by = a.id
                WHERE e.id = %s
            """, (event_id,))
            event = cursor.fetchone()
            
            if not event:
                flash('Event not found.', 'danger')
                return redirect(url_for('index'))
                
            user_registration = None
            user_feedback = None
            if 'user_id' in session and session.get('role') == 'student':
                cursor.execute("""
                    SELECT * FROM registrations 
                    WHERE student_id = %s AND event_id = %s
                """, (session['user_id'], event_id))
                user_registration = cursor.fetchone()
                
                cursor.execute("""
                    SELECT * FROM feedback 
                    WHERE student_id = %s AND event_id = %s
                """, (session['user_id'], event_id))
                user_feedback = cursor.fetchone()
                
            cursor.execute("""
                SELECT f.*, s.name as student_name, s.department as student_dept
                FROM feedback f
                JOIN students s ON f.student_id = s.id
                WHERE f.event_id = %s
                ORDER BY f.created_at DESC LIMIT 5
            """, (event_id,))
            feedbacks = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('event_details.html', event=event, registration=user_registration, feedback=user_feedback, feedbacks=feedbacks)

@app.route('/event/<int:event_id>/register', methods=['POST'])
@student_required
def register_event(event_id):
    student_id = session['user_id']
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
            event = cursor.fetchone()
            
            if not event:
                flash('Event not found.', 'danger')
                return redirect(url_for('index'))
                
            if event['status'] == 'cancelled':
                flash('This event has been cancelled.', 'danger')
                return redirect(url_for('event_details', event_id=event_id))
                
            cursor.execute("""
                SELECT COUNT(*) as count FROM registrations 
                WHERE event_id = %s AND status IN ('registered', 'approved', 'attended')
            """, (event_id,))
            reg_count = cursor.fetchone()['count']
            
            if reg_count >= event['capacity']:
                flash('Sorry, this event has reached full capacity!', 'warning')
                return redirect(url_for('event_details', event_id=event_id))
                
            cursor.execute("""
                SELECT id FROM registrations WHERE student_id = %s AND event_id = %s
            """, (student_id, event_id))
            existing = cursor.fetchone()
            if existing:
                flash('You have already claimed a pass for this event!', 'info')
                return redirect(url_for('event_details', event_id=event_id))
                
            ticket_code = f"EVT-2026-{uuid.uuid4().hex[:6].upper()}"
            qr_filename = generate_ticket_qr(ticket_code)
            
            if event['fee'] == 0:
                payment_status = 'free'
                status = 'approved'
                ref_no = None
                receipt_filename = None
            else:
                payment_status = 'pending'
                status = 'registered'
                ref_no = request.form.get('payment_ref_no', '').strip()
                receipt_filename = None
                
                if 'payment_receipt' in request.files:
                    file = request.files['payment_receipt']
                    if file and file.filename != '' and allowed_file(file.filename):
                        sec_fname = secure_filename(file.filename)
                        receipt_filename = f"rec_{uuid.uuid4().hex[:8]}_{sec_fname}"
                        file.save(os.path.join(Config.RECEIPTS_FOLDER, receipt_filename))
                        
            cursor.execute("""
                INSERT INTO registrations (
                    student_id, event_id, ticket_code, payment_status,
                    payment_ref_no, payment_screenshot, status, qr_code_image
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                student_id, event_id, ticket_code, payment_status,
                ref_no, receipt_filename, status, qr_filename
            ))
            
            reg_id = cursor.lastrowid
            
            flash('Event Pass successfully reserved!', 'success')
            return redirect(url_for('view_ticket', registration_id=reg_id))
    finally:
        db.close()

@app.route('/registration/<int:registration_id>/unregister', methods=['POST'])
@student_required
def unregister_event(registration_id):
    student_id = session['user_id']
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM registrations WHERE id = %s AND student_id = %s
            """, (registration_id, student_id))
            reg = cursor.fetchone()
            
            if not reg:
                flash('Registration record not found.', 'danger')
                return redirect(url_for('student_dashboard'))
                
            if reg['status'] == 'attended':
                flash('Cannot cancel a pass that has already been checked in.', 'warning')
                return redirect(url_for('student_dashboard'))
                
            cursor.execute("DELETE FROM registrations WHERE id = %s", (registration_id,))
            flash('Event pass registration cancelled.', 'info')
    finally:
        db.close()
        
    return redirect(url_for('student_dashboard'))

@app.route('/ticket/<int:registration_id>')
def view_ticket(registration_id):
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT r.*, e.title as event_title, e.category as event_category, e.event_date, e.start_time, e.end_time,
                       e.fee as event_fee, v.name as venue_name, v.building as venue_building,
                       s.name as student_name, s.roll_number, s.department, s.year_of_study, s.email as student_email
                FROM registrations r
                JOIN events e ON r.event_id = e.id
                LEFT JOIN venues v ON e.venue_id = v.id
                JOIN students s ON r.student_id = s.id
                WHERE r.id = %s
            """, (registration_id,))
            ticket = cursor.fetchone()
            
            if not ticket:
                flash('Ticket pass not found.', 'danger')
                return redirect(url_for('index'))
                
            if 'user_id' not in session or (session.get('role') == 'student' and session['user_id'] != ticket['student_id']):
                flash('Access denied to this pass.', 'danger')
                return redirect(url_for('login'))
                
            if not ticket.get('qr_code_image'):
                qr_img = generate_ticket_qr(ticket['ticket_code'])
                cursor.execute("UPDATE registrations SET qr_code_image = %s WHERE id = %s", (qr_img, registration_id))
                ticket['qr_code_image'] = qr_img
    finally:
        db.close()
        
    return render_template('ticket.html', ticket=ticket)

@app.route('/certificate/<int:registration_id>')
@student_required
def view_certificate(registration_id):
    student_id = session['user_id']
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT r.*, e.title as event_title, e.category as event_category, e.event_date,
                       s.name as student_name, s.roll_number, s.department
                FROM registrations r
                JOIN events e ON r.event_id = e.id
                JOIN students s ON r.student_id = s.id
                WHERE r.id = %s AND r.student_id = %s
            """, (registration_id, student_id))
            cert = cursor.fetchone()
            
            if not cert or cert['status'] != 'attended':
                flash('Certificate is only available for attended and verified events.', 'warning')
                return redirect(url_for('student_dashboard'))
    finally:
        db.close()
        
    return render_template('certificate.html', cert=cert)
@app.route('/calendar')
def calendar_view():
    return render_template('calendar.html')

@app.route('/api/calendar-events')
def api_calendar_events():
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT id, title, category, event_date, start_time, end_time, fee
                FROM events WHERE status != 'cancelled'
            """)
            events = cursor.fetchall()
            
            colors = {
                'Hackathon': '#2563eb',
                'Cultural Fest': '#ec4899',
                'Workshop': '#0284c7',
                'Tech & Robotics': '#d97706',
                'Gaming': '#10b981',
                'Seminar': '#8b5cf6',
                'Sports': '#ef4444'
            }
            
            cal_events = []
            for ev in events:
                cal_events.append({
                    'id': ev['id'],
                    'title': f"{ev['title']} ({'FREE' if ev['fee'] == 0 else '₹' + str(int(ev['fee']))})",
                    'start': f"{ev['event_date']}T{ev['start_time']}",
                    'end': f"{ev['event_date']}T{ev['end_time']}",
                    'color': colors.get(ev['category'], '#64748b'),
                    'url': url_for('event_details', event_id=ev['id'])
                })
    finally:
        db.close()
        
    return jsonify(cal_events)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('student_dashboard' if session.get('role') == 'student' else 'admin_dashboard'))
        
    if request.method == 'POST':
        user_type = request.form.get('user_type', 'student')
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        db = get_db_connection()
        try:
            with db.cursor() as cursor:
                if user_type == 'student':
                    cursor.execute("SELECT * FROM students WHERE email = %s", (email,))
                    user = cursor.fetchone()
                    
                    if user and check_password_hash(user['password_hash'], password):
                        session['user_id'] = user['id']
                        session['name'] = user['name']
                        session['email'] = user['email']
                        session['roll_number'] = user['roll_number']
                        session['department'] = user['department']
                        session['role'] = 'student'
                        
                        flash(f'Welcome back, {user["name"]}!', 'success')
                        return redirect(url_for('student_dashboard'))
                    else:
                        flash('Invalid student email or password.', 'danger')
                else:
                    cursor.execute("SELECT * FROM admins WHERE email = %s", (email,))
                    admin = cursor.fetchone()
                    
                    if admin and check_password_hash(admin['password_hash'], password):
                        session['user_id'] = admin['id']
                        session['name'] = admin['name']
                        session['email'] = admin['email']
                        session['role'] = 'admin'
                        
                        flash(f'Welcome, {admin["name"]} (Organizer Desk)!', 'success')
                        return redirect(url_for('admin_dashboard'))
                    else:
                        flash('Invalid organizer email or password.', 'danger')
        finally:
            db.close()
            
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        roll_number = request.form.get('roll_number', '').strip().upper()
        department = request.form.get('department', '').strip()
        year_of_study = request.form.get('year_of_study', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html')
            
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'warning')
            return render_template('auth/register.html')
            
        db = get_db_connection()
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT id FROM students WHERE email = %s OR roll_number = %s", (email, roll_number))
                if cursor.fetchone():
                    flash('A student account with that email or roll number already exists.', 'warning')
                    return render_template('auth/register.html')
                    
                hashed_pw = generate_password_hash(password)
                cursor.execute("""
                    INSERT INTO students (name, email, roll_number, department, year_of_study, phone, password_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (name, email, roll_number, department, year_of_study, phone, hashed_pw))
                
                student_id = cursor.lastrowid
                
                session['user_id'] = student_id
                session['name'] = name
                session['email'] = email
                session['roll_number'] = roll_number
                session['department'] = department
                session['role'] = 'student'
                
                flash('Student enrollment complete! Welcome to CampusPulse.', 'success')
                return redirect(url_for('student_dashboard'))
        finally:
            db.close()
            
    return render_template('auth/register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have successfully signed out of the desk.', 'info')
    return redirect(url_for('index'))

@app.route('/student/dashboard')
@student_required
def student_dashboard():
    student_id = session['user_id']
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT r.*, e.title as event_title, e.category as event_category, e.event_date, e.start_time,
                       e.fee as event_fee, v.name as venue_name
                FROM registrations r
                JOIN events e ON r.event_id = e.id
                LEFT JOIN venues v ON e.venue_id = v.id
                WHERE r.student_id = %s
                ORDER BY e.event_date ASC
            """, (student_id,))
            registrations = cursor.fetchall()
            
            cursor.execute("SELECT COUNT(*) as count FROM registrations WHERE student_id = %s", (student_id,))
            total = cursor.fetchone()['count']
            
            cursor.execute("""
                SELECT COUNT(*) as count FROM registrations r
                JOIN events e ON r.event_id = e.id
                WHERE r.student_id = %s AND e.event_date >= CURRENT_DATE AND r.status != 'cancelled'
            """, (student_id,))
            upcoming = cursor.fetchone()['count']
            
            cursor.execute("""
                SELECT COUNT(*) as count FROM registrations WHERE student_id = %s AND status = 'attended'
            """, (student_id,))
            attended = cursor.fetchone()['count']
            
            cursor.execute("""
                SELECT COUNT(*) as count FROM registrations WHERE student_id = %s AND payment_status = 'pending'
            """, (student_id,))
            pending = cursor.fetchone()['count']
            
            stats = {'total': total, 'upcoming': upcoming, 'attended': attended, 'pending': pending}
    finally:
        db.close()
        
    return render_template('student/dashboard.html', registrations=registrations, stats=stats)

@app.route('/student/notifications')
@student_required
def student_notifications():
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT n.*, e.title as event_title
                FROM notifications n
                LEFT JOIN events e ON n.event_id = e.id
                WHERE n.target_audience IN ('all', 'registered_students')
                ORDER BY n.created_at DESC
            """)
            notifications = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('student/notifications.html', notifications=notifications)

@app.route('/student/profile', methods=['GET', 'POST'])
@student_required
def student_profile():
    student_id = session['user_id']
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            if request.method == 'POST':
                name = request.form.get('name', '').strip()
                phone = request.form.get('phone', '').strip()
                department = request.form.get('department', '').strip()
                year_of_study = request.form.get('year_of_study', '').strip()
                new_pw = request.form.get('new_password', '')
                
                if new_pw and len(new_pw) >= 6:
                    hashed = generate_password_hash(new_pw)
                    cursor.execute("""
                        UPDATE students SET name = %s, phone = %s, department = %s, year_of_study = %s, password_hash = %s
                        WHERE id = %s
                    """, (name, phone, department, year_of_study, hashed, student_id))
                else:
                    cursor.execute("""
                        UPDATE students SET name = %s, phone = %s, department = %s, year_of_study = %s
                        WHERE id = %s
                    """, (name, phone, department, year_of_study, student_id))
                    
                session['name'] = name
                session['department'] = department
                flash('Profile updated successfully!', 'success')
                return redirect(url_for('student_profile'))
                
            cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
            student = cursor.fetchone()
    finally:
        db.close()
        
    return render_template('student/profile.html', student=student)

@app.route('/event/<int:event_id>/feedback', methods=['POST'])
@student_required
def submit_feedback(event_id):
    student_id = session['user_id']
    rating = int(request.form.get('rating', 5))
    comments = request.form.get('comments', '').strip()
    
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                INSERT INTO feedback (student_id, event_id, rating, comments)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE rating = %s, comments = %s, created_at = CURRENT_TIMESTAMP
            """, (student_id, event_id, rating, comments, rating, comments))
            flash('Thank you for rating this event!', 'success')
    finally:
        db.close()
        
    return redirect(url_for('event_details', event_id=event_id))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM events WHERE status != 'cancelled'")
            total_events = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM registrations WHERE status != 'cancelled'")
            total_registrations = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM registrations WHERE status = 'attended'")
            total_attended = cursor.fetchone()['count']
            
            cursor.execute("""
                SELECT COALESCE(SUM(e.fee), 0) as revenue
                FROM registrations r
                JOIN events e ON r.event_id = e.id
                WHERE r.payment_status = 'verified'
            """)
            total_revenue = cursor.fetchone()['revenue']
            
            cursor.execute("""
                SELECT e.*, v.name as venue_name,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status IN ('registered', 'approved', 'attended')) as registered_count
                FROM events e
                LEFT JOIN venues v ON e.venue_id = v.id
                ORDER BY e.event_date ASC LIMIT 8
            """)
            events = cursor.fetchall()
            
            stats = {
                'total_events': total_events,
                'total_registrations': total_registrations,
                'total_attended': total_attended,
                'total_revenue': total_revenue
            }
    finally:
        db.close()
        
    return render_template('admin/dashboard.html', stats=stats, events=events)

@app.route('/admin/events')
@admin_required
def admin_events():
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, v.name as venue_name,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status IN ('registered', 'approved', 'attended')) as total_registered,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.payment_status = 'pending') as pending_payments
                FROM events e
                LEFT JOIN venues v ON e.venue_id = v.id
                ORDER BY e.event_date ASC
            """)
            events = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('admin/events.html', events=events)

@app.route('/admin/events/create', methods=['GET', 'POST'])
@admin_required
def admin_create_event():
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            if request.method == 'POST':
                title = request.form.get('title', '').strip()
                category = request.form.get('category', '').strip()
                description = request.form.get('description', '').strip()
                venue_id = int(request.form.get('venue_id'))
                event_date = request.form.get('event_date')
                start_time = request.form.get('start_time')
                end_time = request.form.get('end_time')
                capacity = int(request.form.get('capacity', 50))
                fee = float(request.form.get('fee', 0.00))
                upi_id = request.form.get('upi_id', '').strip()
                status = request.form.get('status', 'upcoming')
                
                banner_filename = None
                if 'banner' in request.files:
                    file = request.files['banner']
                    if file and file.filename != '' and allowed_file(file.filename):
                        sec_fname = secure_filename(file.filename)
                        banner_filename = f"ban_{uuid.uuid4().hex[:8]}_{sec_fname}"
                        file.save(os.path.join(Config.BANNERS_FOLDER, banner_filename))
                        
                payment_qr_filename = None
                if fee > 0 and upi_id:
                    payment_qr_filename = generate_payment_qr(upi_id, title)
                    
                cursor.execute("""
                    INSERT INTO events (
                        title, category, description, venue_id, event_date,
                        start_time, end_time, capacity, fee, banner_image,
                        payment_qr_image, upi_id, status, created_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    title, category, description, venue_id, event_date,
                    start_time, end_time, capacity, fee, banner_filename,
                    payment_qr_filename, upi_id, status, session['user_id']
                ))
                
                flash(f'Event "{title}" published successfully!', 'success')
                return redirect(url_for('admin_events'))
                
            cursor.execute("SELECT * FROM venues ORDER BY name")
            venues = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('admin/event_form.html', venues=venues, event=None)

@app.route('/admin/events/<int:event_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_event(event_id):
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
            event = cursor.fetchone()
            if not event:
                flash('Event not found.', 'danger')
                return redirect(url_for('admin_events'))
                
            if request.method == 'POST':
                title = request.form.get('title', '').strip()
                category = request.form.get('category', '').strip()
                description = request.form.get('description', '').strip()
                venue_id = int(request.form.get('venue_id'))
                event_date = request.form.get('event_date')
                start_time = request.form.get('start_time')
                end_time = request.form.get('end_time')
                capacity = int(request.form.get('capacity', 50))
                fee = float(request.form.get('fee', 0.00))
                upi_id = request.form.get('upi_id', '').strip()
                status = request.form.get('status', 'upcoming')
                
                banner_filename = event['banner_image']
                if 'banner' in request.files:
                    file = request.files['banner']
                    if file and file.filename != '' and allowed_file(file.filename):
                        sec_fname = secure_filename(file.filename)
                        banner_filename = f"ban_{uuid.uuid4().hex[:8]}_{sec_fname}"
                        file.save(os.path.join(Config.BANNERS_FOLDER, banner_filename))
                        
                payment_qr_filename = event['payment_qr_image']
                if fee > 0 and upi_id and (upi_id != event.get('upi_id') or not payment_qr_filename):
                    payment_qr_filename = generate_payment_qr(upi_id, title)
                    
                cursor.execute("""
                    UPDATE events SET
                        title = %s, category = %s, description = %s, venue_id = %s,
                        event_date = %s, start_time = %s, end_time = %s, capacity = %s,
                        fee = %s, banner_image = %s, payment_qr_image = %s, upi_id = %s, status = %s
                    WHERE id = %s
                """, (
                    title, category, description, venue_id, event_date,
                    start_time, end_time, capacity, fee, banner_filename,
                    payment_qr_filename, upi_id, status, event_id
                ))
                
                flash(f'Event "{title}" updated successfully!', 'success')
                return redirect(url_for('admin_events'))
                
            cursor.execute("SELECT * FROM venues ORDER BY name")
            venues = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('admin/event_form.html', venues=venues, event=event)

@app.route('/admin/events/<int:event_id>/delete', methods=['POST'])
@admin_required
def admin_delete_event(event_id):
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
            flash('Event deleted from system.', 'info')
    finally:
        db.close()
        
    return redirect(url_for('admin_events'))

@app.route('/admin/registrations')
@admin_required
def admin_registrations():
    event_id = request.args.get('event_id')
    payment_status = request.args.get('payment_status', 'all')
    
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            query = """
                SELECT r.*, s.name as student_name, s.roll_number, s.department, s.email as student_email,
                       e.title as event_title, e.fee as event_fee
                FROM registrations r
                JOIN students s ON r.student_id = s.id
                JOIN events e ON r.event_id = e.id
                WHERE 1=1
            """
            params = []
            if event_id:
                query += " AND r.event_id = %s"
                params.append(event_id)
            if payment_status != 'all':
                query += " AND r.payment_status = %s"
                params.append(payment_status)
                
            query += " ORDER BY r.registered_at DESC"
            cursor.execute(query, params)
            registrations = cursor.fetchall()
            
            cursor.execute("SELECT id, title FROM events ORDER BY title")
            events = cursor.fetchall()
    finally:
        db.close()
        
    return render_template(
        'admin/registrations.html',
        registrations=registrations,
        events=events,
        selected_event_id=int(event_id) if event_id else None,
        selected_payment_status=payment_status
    )

@app.route('/admin/registrations/<int:registration_id>/verify/<action>', methods=['POST'])
@admin_required
def admin_verify_payment(registration_id, action):
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            if action == 'approve':
                cursor.execute("""
                    UPDATE registrations SET payment_status = 'verified', status = 'approved'
                    WHERE id = %s
                """, (registration_id,))
                flash('Payment approved & event pass activated!', 'success')
            elif action == 'reject':
                cursor.execute("""
                    UPDATE registrations SET payment_status = 'rejected', status = 'rejected'
                    WHERE id = %s
                """, (registration_id,))
                flash('Payment rejected.', 'warning')
    finally:
        db.close()
        
    return redirect(url_for('admin_registrations'))

@app.route('/admin/scanner')
@admin_required
def admin_scanner():
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT id, title, event_date FROM events WHERE status != 'cancelled' ORDER BY event_date ASC")
            events = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('admin/scanner.html', events=events)

@app.route('/api/scan-ticket', methods=['POST'])
@admin_required
def api_scan_ticket():
    data = request.get_json() or {}
    ticket_code = data.get('ticket_code', '').strip()
    event_id = data.get('event_id')
    
    if not ticket_code:
        return jsonify({'success': False, 'message': 'Ticket code is required.'}), 400
        
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            query = """
                SELECT r.*, s.name as student_name, s.roll_number, s.department, s.email as student_email,
                       e.title as event_title, e.id as actual_event_id
                FROM registrations r
                JOIN students s ON r.student_id = s.id
                JOIN events e ON r.event_id = e.id
                WHERE r.ticket_code = %s
            """
            cursor.execute(query, (ticket_code,))
            reg = cursor.fetchone()
            
            if not reg:
                return jsonify({'success': False, 'message': 'Invalid ticket pass. Code not found in database.'}), 404
                
            if event_id and int(event_id) != reg['actual_event_id']:
                return jsonify({
                    'success': False,
                    'message': f'Ticket belongs to "{reg["event_title"]}", not the selected gate event.'
                }), 400
                
            if reg['status'] == 'rejected':
                return jsonify({
                    'success': False,
                    'message': f'Access Denied: Pass was rejected for {reg["student_name"]}.'
                }), 403
                
            if reg['status'] == 'attended':
                attended_str = reg['attended_at'].strftime('%I:%M %p, %b %d') if reg['attended_at'] else 'Earlier'
                return jsonify({
                    'success': False,
                    'already_attended': True,
                    'message': f'Already Checked In at {attended_str}',
                    'student': {
                        'name': reg['student_name'],
                        'roll_number': reg['roll_number'],
                        'department': reg['department'],
                        'event': reg['event_title']
                    }
                })
                
            if reg['payment_status'] == 'pending':
                return jsonify({
                    'success': False,
                    'message': f'Payment Pending: Student {reg["student_name"]} has not verified payment yet.'
                }), 400
                
            now = datetime.now()
            cursor.execute("""
                UPDATE registrations SET status = 'attended', attended_at = %s
                WHERE id = %s
            """, (now, reg['id']))
            
            return jsonify({
                'success': True,
                'message': 'Attendance Verified!',
                'timestamp': now.strftime('%I:%M:%S %p'),
                'student': {
                    'name': reg['student_name'],
                    'roll_number': reg['roll_number'],
                    'department': reg['department'],
                    'event': reg['event_title'],
                    'ticket_code': reg['ticket_code']
                }
            })
    finally:
        db.close()
@app.route('/admin/participants')
@admin_required
def admin_participants():
    event_id = request.args.get('event_id')
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            query = """
                SELECT r.*, s.name as student_name, s.email, s.roll_number, s.department, s.year_of_study, s.phone,
                       e.title as event_title, e.event_date
                FROM registrations r
                JOIN students s ON r.student_id = s.id
                JOIN events e ON r.event_id = e.id
                WHERE 1=1
            """
            params = []
            if event_id:
                query += " AND r.event_id = %s"
                params.append(event_id)
                
            query += " ORDER BY e.event_date DESC, r.registered_at DESC"
            cursor.execute(query, params)
            participants = cursor.fetchall()
            
            cursor.execute("SELECT id, title FROM events ORDER BY title")
            events = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('admin/participants.html', participants=participants, events=events, selected_event_id=int(event_id) if event_id else None)

@app.route('/admin/participants/export/<int:event_id>')
@admin_required
def export_participants_csv(event_id):
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT title, event_date FROM events WHERE id = %s", (event_id,))
            event = cursor.fetchone()
            if not event:
                flash('Event not found.', 'danger')
                return redirect(url_for('admin_participants'))
                
            cursor.execute("""
                SELECT s.name, s.roll_number, s.department, s.year_of_study, s.email, s.phone,
                       r.ticket_code, r.payment_status, r.payment_ref_no, r.status, r.registered_at, r.attended_at
                FROM registrations r
                JOIN students s ON r.student_id = s.id
                WHERE r.event_id = %s
                ORDER BY s.name ASC
            """, (event_id,))
            participants = cursor.fetchall()
            
            si = io.StringIO()
            writer = csv.writer(si)
            writer.writerow([
                'Student Name', 'Roll Number', 'Department', 'Year', 'Email', 'Phone',
                'Ticket Code', 'Payment Status', 'Payment Ref No', 'Attendance Status', 'Registered At', 'Attended At'
            ])
            
            for p in participants:
                writer.writerow([
                    p['name'],
                    p['roll_number'],
                    p['department'],
                    p['year_of_study'],
                    p['email'],
                    p['phone'],
                    p['ticket_code'],
                    p['payment_status'],
                    p['payment_ref_no'] or 'N/A',
                    p['status'],
                    p['registered_at'],
                    p['attended_at'] or 'Not Checked In'
                ])
                
            output = si.getvalue()
            safe_title = "".join(c for c in event['title'] if c.isalnum() or c in (' ', '_', '-')).rstrip()
            filename = f"Attendees_{safe_title}_{datetime.now().strftime('%Y%m%d')}.csv"
            
            return Response(
                output,
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment;filename={filename}"}
            )
    finally:
        db.close()

@app.route('/admin/announcements', methods=['GET', 'POST'])
@admin_required
def admin_announcements():
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            if request.method == 'POST':
                title = request.form.get('title', '').strip()
                message = request.form.get('message', '').strip()
                event_id = request.form.get('event_id') or None
                target_audience = request.form.get('target_audience', 'all')
                
                if title and message:
                    cursor.execute("""
                        INSERT INTO notifications (title, message, event_id, target_audience)
                        VALUES (%s, %s, %s, %s)
                    """, (title, message, event_id, target_audience))
                    flash('Notice broadcasted to campus students!', 'success')
                    return redirect(url_for('admin_announcements'))
                    
            cursor.execute("""
                SELECT n.*, e.title as event_title
                FROM notifications n
                LEFT JOIN events e ON n.event_id = e.id
                ORDER BY n.created_at DESC
            """)
            announcements = cursor.fetchall()
            
            cursor.execute("SELECT id, title FROM events ORDER BY title")
            events = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('admin/announcements.html', announcements=announcements, events=events)

@app.route('/admin/announcements/<int:announcement_id>/delete', methods=['POST'])
@admin_required
def admin_delete_announcement(announcement_id):
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM notifications WHERE id = %s", (announcement_id,))
            flash('Notice removed.', 'info')
    finally:
        db.close()
    return redirect(url_for('admin_announcements'))

@app.route('/admin/feedback')
@admin_required
def admin_feedback():
    event_id = request.args.get('event_id')
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            query = """
                SELECT f.*, s.name as student_name, s.roll_number, s.department,
                       e.title as event_title, e.category as event_category
                FROM feedback f
                JOIN students s ON f.student_id = s.id
                JOIN events e ON f.event_id = e.id
                WHERE 1=1
            """
            params = []
            if event_id:
                query += " AND f.event_id = %s"
                params.append(event_id)
                
            query += " ORDER BY f.created_at DESC"
            cursor.execute(query, params)
            feedbacks = cursor.fetchall()
            
            cursor.execute("SELECT AVG(rating) as avg_rating, COUNT(*) as total_feedback FROM feedback")
            feedback_stats = cursor.fetchone()
            
            cursor.execute("SELECT id, title FROM events ORDER BY title")
            events = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('admin/feedback.html', feedbacks=feedbacks, stats=feedback_stats, events=events, selected_event_id=int(event_id) if event_id else None)

@app.route('/admin/venues', methods=['GET', 'POST'])
@admin_required
def admin_venues():
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            if request.method == 'POST':
                name = request.form.get('name', '').strip()
                building = request.form.get('building', '').strip()
                capacity = int(request.form.get('capacity', 100))
                location_details = request.form.get('location_details', '').strip()
                
                cursor.execute("""
                    INSERT INTO venues (name, building, capacity, location_details)
                    VALUES (%s, %s, %s, %s)
                """, (name, building, capacity, location_details))
                flash(f'Campus venue "{name}" registered!', 'success')
                return redirect(url_for('admin_venues'))
                
            cursor.execute("""
                SELECT v.*, (SELECT COUNT(*) FROM events e WHERE e.venue_id = v.id) as total_events
                FROM venues v
                ORDER BY v.name ASC
            """)
            venues = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('admin/venues.html', venues=venues)
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
