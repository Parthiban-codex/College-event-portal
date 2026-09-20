import os
import uuid
import csv
import io
from datetime import datetime, date, time, timedelta
from functools import wraps
from PIL import Image

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, send_file, Response
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import qrcode

from config import Config
from database import (
    get_db_connection, init_db, ensure_upload_dirs, generate_member_qr
)

app = Flask(__name__)
app.config.from_object(Config)

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
    img = qr.make_image(fill_color="#1E3A8A", back_color="white")
    img.save(filepath)
    return filename

def generate_payment_qr(upi_id, event_title):
    """Generate dynamic UPI QR code for paid event tickets."""
    unique_id = uuid.uuid4().hex[:8]
    filename = f"upi_{unique_id}.png"
    filepath = os.path.join(Config.PAYMENT_QRS_FOLDER, filename)
    
    clean_title = "".join(c for c in event_title if c.isalnum() or c in (' ', '-', '_')).strip()
    upi_payload = f"upi://pay?pa={upi_id}&pn=RGCET%20Events&tn={clean_title.replace(' ', '%20')}&cu=INR"
    
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

def build_attendance_excel(event, participants):
    """Create a professionally formatted Excel (.xlsx) file using openpyxl."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance Ledger"
    
    # Enable grid lines
    ws.views.sheetView[0].showGridLines = True
    
    # Palette styling
    navy_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    attended_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    absent_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    
    white_bold = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Arial", size=14, bold=True, color="FFFFFF")
    sub_font = Font(name="Arial", size=10, italic=True, color="E2E8F0")
    bold_font = Font(name="Arial", size=10, bold=True)
    regular_font = Font(name="Arial", size=10)
    attended_font = Font(name="Arial", size=10, bold=True, color="166534")
    absent_font = Font(name="Arial", size=10, bold=True, color="991B1B")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # Row 1-2: College Header Banner
    ws.merge_cells('A1:K1')
    ws['A1'] = "RAJIV GANDHI COLLEGE OF ENGINEERING AND TECHNOLOGY (RGCET)"
    ws['A1'].font = title_font
    ws['A1'].fill = navy_fill
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells('A2:K2')
    ws['A2'] = "Campus Event Attendance & Verification Ledger • Innovation Through Information"
    ws['A2'].font = sub_font
    ws['A2'].fill = navy_fill
    ws['A2'].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 18

    # Row 4-6: Event Meta Info
    ws['A4'] = "Event Title:"
    ws['B4'] = event['title']
    ws['E4'] = "Event Date:"
    ws['F4'] = str(event['event_date'])
    
    ws['A5'] = "Venue:"
    ws['B5'] = f"{event.get('venue_name', 'Campus')} ({event.get('venue_building', 'RGCET')})"
    ws['E5'] = "Host Club:"
    ws['F5'] = event.get('club_name', 'RGCET Central Desk')

    ws['A6'] = "Total Registrations:"
    ws['B6'] = len(participants)
    attended_count = sum(1 for p in participants if p['status'] == 'attended')
    ws['E6'] = "Attended (Verified):"
    ws['F6'] = attended_count

    for row_idx in range(4, 7):
        for col_letter in ['A', 'E']:
            ws[f'{col_letter}{row_idx}'].font = bold_font
            ws[f'{col_letter}{row_idx}'].alignment = Alignment(horizontal="right")
        for col_letter in ['B', 'F']:
            ws[f'{col_letter}{row_idx}'].font = regular_font

    # Row 8: Table Header
    headers = [
        "S.No", "Student Name", "Roll Number", "Department", "Year",
        "College Email", "Phone", "Ticket Pass Code", "Payment Status",
        "Attendance Status", "Check-in Timestamp"
    ]
    
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=8, column=col_idx, value=header)
        cell.font = white_bold
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
    ws.row_dimensions[8].height = 24

    # Data Rows
    current_row = 9
    for idx, p in enumerate(participants, 1):
        ws.cell(row=current_row, column=1, value=idx).alignment = Alignment(horizontal="center")
        ws.cell(row=current_row, column=2, value=p.get('student_name', ''))
        ws.cell(row=current_row, column=3, value=p.get('roll_number', '')).alignment = Alignment(horizontal="center")
        ws.cell(row=current_row, column=4, value=p.get('department', ''))
        ws.cell(row=current_row, column=5, value=p.get('year_of_study', '')).alignment = Alignment(horizontal="center")
        ws.cell(row=current_row, column=6, value=p.get('email', ''))
        ws.cell(row=current_row, column=7, value=p.get('phone', '')).alignment = Alignment(horizontal="center")
        ws.cell(row=current_row, column=8, value=p.get('ticket_code', '')).alignment = Alignment(horizontal="center")
        ws.cell(row=current_row, column=9, value=str(p.get('payment_status', '')).upper()).alignment = Alignment(horizontal="center")
        
        # Status styling
        status_cell = ws.cell(row=current_row, column=10, value="ATTENDED" if p['status'] == 'attended' else "REGISTERED")
        status_cell.alignment = Alignment(horizontal="center")
        if p['status'] == 'attended':
            status_cell.fill = attended_fill
            status_cell.font = attended_font
        else:
            status_cell.fill = absent_fill
            status_cell.font = absent_font

        # Attended time
        att_time_str = p['attended_at'].strftime('%Y-%m-%d %I:%M %p') if p.get('attended_at') else 'Not Checked In'
        ws.cell(row=current_row, column=11, value=att_time_str).alignment = Alignment(horizontal="center")

        # Borders and zebra striping
        for col_idx in range(1, len(headers) + 1):
            c = ws.cell(row=current_row, column=col_idx)
            c.border = thin_border
            if col_idx != 10 and current_row % 2 == 0:
                c.fill = zebra_fill
            if col_idx != 10:
                c.font = regular_font

        ws.row_dimensions[current_row].height = 20
        current_row += 1

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or '')
            if len(val_str) > max_len and cell.row > 2:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output



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
            flash('Access restricted to enrolled RGCET students.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Central Administration access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def club_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'club':
            flash('Club portal access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def club_leader_or_faculty_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'club' or session.get('club_role') not in ('leader', 'faculty'):
            flash('Only Club Faculty Advisors and Club Leaders have permission for this action.', 'warning')
            return redirect(url_for('club_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def club_faculty_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'club' or session.get('club_role') != 'faculty':
            flash('Club Faculty Advisor authorization required.', 'warning')
            return redirect(url_for('club_dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def inject_global_data():
    current_user = None
    unread_notifs = 0
    pending_faculty_count = 0
    pending_admin_count = 0
    pending_deletion_count = 0
    
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            if 'user_id' in session:
                user_role = session.get('role')
                if user_role == 'student':
                    cursor.execute("SELECT * FROM students WHERE id = %s", (session['user_id'],))
                    current_user = cursor.fetchone()
                    if current_user:
                        current_user['user_type'] = 'student'
                    cursor.execute("SELECT COUNT(*) as count FROM notifications WHERE target_audience IN ('all', 'registered_students')")
                    unread_notifs = cursor.fetchone()['count']
                elif user_role == 'admin':
                    cursor.execute("SELECT * FROM admins WHERE id = %s", (session['user_id'],))
                    current_user = cursor.fetchone()
                    if current_user:
                        current_user['user_type'] = 'admin'
                    # Count pending events waiting for admin
                    cursor.execute("SELECT COUNT(*) as count FROM events WHERE status = 'pending_admin'")
                    pending_admin_count = cursor.fetchone()['count']
                    # Count pending deletion requests
                    cursor.execute("SELECT COUNT(*) as count FROM event_deletion_requests WHERE status = 'pending'")
                    pending_deletion_count = cursor.fetchone()['count']
                elif user_role == 'club':
                    cursor.execute("""
                        SELECT m.*, c.name as club_name, c.code as club_code
                        FROM club_members m
                        JOIN clubs c ON m.club_id = c.id
                        WHERE m.id = %s
                    """, (session['user_id'],))
                    current_user = cursor.fetchone()
                    if current_user:
                        current_user['user_type'] = 'club'
                        if current_user['role'] == 'faculty':
                            cursor.execute("SELECT COUNT(*) as count FROM events WHERE club_id = %s AND status = 'pending_faculty'", (current_user['club_id'],))
                            pending_faculty_count = cursor.fetchone()['count']
    finally:
        db.close()
            
    categories = ['Hackathon', 'Symposium', 'Workshop', 'Cultural Fest', 'Tech & Robotics', 'Gaming', 'Seminar', 'Sports']
    return dict(
        current_user=current_user,
        unread_notifications_count=unread_notifs,
        pending_faculty_count=pending_faculty_count,
        pending_admin_count=pending_admin_count,
        pending_deletion_count=pending_deletion_count,
        categories=categories
    )

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

# ------------------------------------------------------------------------------
# PUBLIC HOMEPAGE (OPEN TO ALL WITHOUT LOGIN)
# ------------------------------------------------------------------------------

@app.route('/')
def index():
    """
    Public open page. Anyone, including non-logged-in students and visitors,
    can view Announcements, Event Pamphlets/Flyers, and the Interactive Calendar.
    """
    category = request.args.get('category', 'all')
    search = request.args.get('search', '').strip()
    fee_type = request.args.get('fee_type', 'all')
    
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            # 1. Fetch published upcoming events for pamphlet cards
            query = """
                SELECT e.*, v.name as venue_name, v.building as venue_building,
                       c.name as club_name, c.code as club_code,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status IN ('registered', 'approved', 'attended')) as registered_count
                FROM events e
                LEFT JOIN venues v ON e.venue_id = v.id
                LEFT JOIN clubs c ON e.club_id = c.id
                WHERE e.status = 'upcoming'
            """
            params = []
            
            if category and category != 'all':
                query += " AND e.category = %s"
                params.append(category)
                
            if search:
                query += " AND (e.title LIKE %s OR e.description LIKE %s OR v.name LIKE %s OR c.name LIKE %s)"
                term = f"%{search}%"
                params.extend([term, term, term, term])
                
            if fee_type == 'free':
                query += " AND e.fee = 0"
            elif fee_type == 'paid':
                query += " AND e.fee > 0"
                
            query += " ORDER BY e.event_date ASC, e.start_time ASC"
            cursor.execute(query, params)
            events = cursor.fetchall()
            
            # 2. Fetch live public announcements
            cursor.execute("""
                SELECT n.*, e.title as event_title
                FROM notifications n
                LEFT JOIN events e ON n.event_id = e.id
                WHERE n.target_audience IN ('all', 'registered_students')
                ORDER BY n.created_at DESC LIMIT 5
            """)
            announcements = cursor.fetchall()

            # 3. Fetch active campus clubs
            cursor.execute("SELECT * FROM clubs ORDER BY name ASC")
            clubs = cursor.fetchall()
            
            # 4. Overall statistics
            cursor.execute("SELECT COUNT(*) as total_events FROM events WHERE status = 'upcoming'")
            total_events = cursor.fetchone()['total_events']
            
            cursor.execute("SELECT COUNT(*) as total_registrations FROM registrations WHERE status != 'cancelled'")
            total_registrations = cursor.fetchone()['total_registrations']
            
            cursor.execute("SELECT COUNT(*) as total_students FROM students")
            total_students = cursor.fetchone()['total_students']

            cursor.execute("SELECT COUNT(*) as total_clubs FROM clubs")
            total_clubs = cursor.fetchone()['total_clubs']
    finally:
        db.close()
        
    return render_template(
        'index.html',
        events=events,
        announcements=announcements,
        clubs=clubs,
        selected_category=category,
        search_query=search,
        fee_type=fee_type,
        stats={
            'total_events': total_events,
            'total_registrations': total_registrations,
            'total_students': total_students,
            'total_clubs': total_clubs
        }
    )

@app.route('/event/<int:event_id>')
def event_details(event_id):
    """View event details & pamphlet. Visible to all."""
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, v.name as venue_name, v.building as venue_building, v.capacity as venue_capacity, v.location_details,
                       c.name as club_name, c.code as club_code, c.faculty_advisor_name,
                       a.name as admin_creator_name,
                       m.name as member_creator_name, m.role as member_creator_role,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status IN ('registered', 'approved', 'attended')) as registered_count,
                       (SELECT AVG(rating) FROM feedback f WHERE f.event_id = e.id) as avg_rating,
                       (SELECT COUNT(*) FROM feedback f WHERE f.event_id = e.id) as feedback_count
                FROM events e
                LEFT JOIN venues v ON e.venue_id = v.id
                LEFT JOIN clubs c ON e.club_id = c.id
                LEFT JOIN admins a ON e.created_by = a.id
                LEFT JOIN club_members m ON e.created_by_member_id = m.id
                WHERE e.id = %s
            """, (event_id,))
            event = cursor.fetchone()
            
            if not event:
                flash('Event pamphlet not found.', 'danger')
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

# ------------------------------------------------------------------------------
# CALENDAR
# ------------------------------------------------------------------------------

@app.route('/calendar')
def calendar_view():
    """Standalone full calendar page."""
    return render_template('calendar.html')

@app.route('/api/calendar-events')
def api_calendar_events():
    """Public JSON endpoint feeding FullCalendar on homepage and calendar page."""
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT e.id, e.title, e.category, e.event_date, e.start_time, e.end_time, e.fee,
                       v.name as venue_name, c.name as club_name
                FROM events e
                LEFT JOIN venues v ON e.venue_id = v.id
                LEFT JOIN clubs c ON e.club_id = c.id
                WHERE e.status = 'upcoming'
            """)
            events = cursor.fetchall()
            
            colors = {
                'Hackathon': '#1E3A8A',     # Navy Blue
                'Symposium': '#2563EB',     # Royal Blue
                'Workshop': '#0D9488',      # Teal
                'Cultural Fest': '#DB2777', # Pink/Magenta
                'Tech & Robotics': '#D97706',# Amber
                'Gaming': '#059669',        # Green
                'Seminar': '#7C3AED',       # Violet
                'Sports': '#DC2626'         # Red
            }
            
            cal_events = []
            for ev in events:
                cal_events.append({
                    'id': ev['id'],
                    'title': f"{ev['title']} ({'FREE' if ev['fee'] == 0 else '₹' + str(int(ev['fee']))})",
                    'start': f"{ev['event_date']}T{ev['start_time']}",
                    'end': f"{ev['event_date']}T{ev['end_time']}",
                    'color': colors.get(ev['category'], '#1E3A8A'),
                    'url': url_for('event_details', event_id=ev['id']),
                    'extendedProps': {
                        'venue': ev['venue_name'] or 'Campus',
                        'club': ev['club_name'] or 'RGCET',
                        'category': ev['category']
                    }
                })
    finally:
        db.close()
        
    return jsonify(cal_events)

# ------------------------------------------------------------------------------
# AUTHENTICATION (STUDENT, CLUB, ADMIN)
# ------------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        role = session.get('role')
        if role == 'student':
            return redirect(url_for('student_dashboard'))
        elif role == 'club':
            return redirect(url_for('club_dashboard'))
        else:
            return redirect(url_for('admin_dashboard'))
        
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT id, name, code FROM clubs ORDER BY name ASC")
            clubs = cursor.fetchall()
    finally:
        db.close()

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

                elif user_type == 'club':
                    club_role = request.form.get('club_role', 'volunteer')
                    cursor.execute("""
                        SELECT m.*, c.name as club_name, c.code as club_code
                        FROM club_members m
                        JOIN clubs c ON m.club_id = c.id
                        WHERE m.email = %s AND m.role = %s
                    """, (email, club_role))
                    member = cursor.fetchone()
                    
                    if member and check_password_hash(member['password_hash'], password):
                        session['user_id'] = member['id']
                        session['name'] = member['name']
                        session['email'] = member['email']
                        session['department'] = member['department']
                        session['role'] = 'club'
                        session['club_role'] = member['role']
                        session['club_id'] = member['club_id']
                        session['club_name'] = member['club_name']
                        session['member_code'] = member['member_code']
                        
                        flash(f'Welcome, {member["name"]} ({member["role"].capitalize()} - {member["club_name"]})!', 'success')
                        return redirect(url_for('club_dashboard'))
                    else:
                        flash(f'Invalid credentials for Club {club_role.capitalize()} login.', 'danger')

                elif user_type == 'admin':
                    cursor.execute("SELECT * FROM admins WHERE email = %s", (email,))
                    admin = cursor.fetchone()
                    if admin and check_password_hash(admin['password_hash'], password):
                        session['user_id'] = admin['id']
                        session['name'] = admin['name']
                        session['email'] = admin['email']
                        session['role'] = 'admin'
                        
                        flash(f'Welcome, {admin["name"]} (Central Admin Desk)!', 'success')
                        return redirect(url_for('admin_dashboard'))
                    else:
                        flash('Invalid Central Administrator credentials.', 'danger')
        finally:
            db.close()
            
    return render_template('auth/login.html', clubs=clubs)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registration for students and club members."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT id, name, code FROM clubs ORDER BY name ASC")
            clubs = cursor.fetchall()
    finally:
        db.close()
        
    if request.method == 'POST':
        reg_type = request.form.get('reg_type', 'student')
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        department = request.form.get('department', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html', clubs=clubs)
            
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'warning')
            return render_template('auth/register.html', clubs=clubs)
            
        db = get_db_connection()
        try:
            with db.cursor() as cursor:
                if reg_type == 'student':
                    roll_number = request.form.get('roll_number', '').strip().upper()
                    year_of_study = request.form.get('year_of_study', '').strip()
                    
                    cursor.execute("SELECT id FROM students WHERE email = %s OR roll_number = %s", (email, roll_number))
                    if cursor.fetchone():
                        flash('A student account with that email or roll number already exists.', 'warning')
                        return render_template('auth/register.html', clubs=clubs)
                        
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
                    
                    flash('Student registration successful! Welcome to RGCET Event Hub.', 'success')
                    return redirect(url_for('student_dashboard'))

                elif reg_type == 'club':
                    club_id = int(request.form.get('club_id'))
                    club_role = request.form.get('club_role', 'volunteer')

                    if club_role == 'leader':
                        cursor.execute("UPDATE club_members SET role = 'ex_leader' WHERE club_id = %s AND role = 'leader'", (club_id,))
                    
                    cursor.execute("SELECT id FROM club_members WHERE email = %s", (email,))
                    if cursor.fetchone():
                        flash('A club member with that email address already exists.', 'warning')
                        return render_template('auth/register.html', clubs=clubs)

                    member_code = f"RGCET-{club_role[:3].upper()}-{uuid.uuid4().hex[:6].upper()}"
                    qr_img = generate_member_qr(member_code)
                    hashed_pw = generate_password_hash(password)

                    cursor.execute("""
                        INSERT INTO club_members (club_id, name, email, phone, department, role, password_hash, member_code, qr_code_image)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (club_id, name, email, phone, department, club_role, hashed_pw, member_code, qr_img))
                    member_id = cursor.lastrowid

                    cursor.execute("SELECT name FROM clubs WHERE id = %s", (club_id,))
                    c_name = cursor.fetchone()['name']

                    session['user_id'] = member_id
                    session['name'] = name
                    session['email'] = email
                    session['department'] = department
                    session['role'] = 'club'
                    session['club_role'] = club_role
                    session['club_id'] = club_id
                    session['club_name'] = c_name
                    session['member_code'] = member_code

                    flash(f'Club registration successful as {club_role.capitalize()}!', 'success')
                    return redirect(url_for('club_dashboard'))
        finally:
            db.close()
            
    return render_template('auth/register.html', clubs=clubs)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have successfully signed out.', 'info')
    return redirect(url_for('index'))

# ------------------------------------------------------------------------------
# STUDENT EVENT PASS RESERVATIONS & ACTIONS
# ------------------------------------------------------------------------------

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
                
            if event['status'] != 'upcoming':
                flash('Registration is only open for upcoming active events.', 'danger')
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
                
            ticket_code = f"RGCET-{uuid.uuid4().hex[:6].upper()}"
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

@app.route('/ticket/<int:registration_id>')
def view_ticket(registration_id):
    """View digital Admit-One QR Pass."""
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT r.*, e.title as event_title, e.category as event_category, e.event_date, e.start_time, e.end_time,
                       e.fee as event_fee, v.name as venue_name, v.building as venue_building,
                       c.name as club_name,
                       leader.name as leader_name, faculty.name as faculty_name,
                       s.name as student_name, s.roll_number, s.department, s.year_of_study, s.email as student_email
                FROM registrations r
                JOIN events e ON r.event_id = e.id
                LEFT JOIN venues v ON e.venue_id = v.id
                LEFT JOIN clubs c ON e.club_id = c.id
                LEFT JOIN club_members leader ON leader.club_id = e.club_id AND leader.role = 'leader'
                LEFT JOIN club_members faculty ON faculty.club_id = e.club_id AND faculty.role = 'faculty'
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
                       c.name as club_name, c.faculty_advisor_name,
                       s.name as student_name, s.roll_number, s.department
                FROM registrations r
                JOIN events e ON r.event_id = e.id
                LEFT JOIN clubs c ON e.club_id = c.id
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

@app.route('/registration/<int:registration_id>/unregister', methods=['POST'])
@student_required
def unregister_event(registration_id):
    student_id = session['user_id']
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM registrations WHERE id = %s AND student_id = %s", (registration_id, student_id))
            reg = cursor.fetchone()
            if not reg:
                flash('Registration record not found.', 'danger')
                return redirect(url_for('student_dashboard'))
                
            if reg['status'] == 'attended':
                flash('Cannot cancel a pass that has already been checked in.', 'warning')
                return redirect(url_for('student_dashboard'))
                
            cursor.execute("DELETE FROM registrations WHERE id = %s", (registration_id,))
            flash('Event pass cancelled.', 'info')
    finally:
        db.close()
    return redirect(url_for('student_dashboard'))

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
            flash('Thank you for your rating and feedback!', 'success')
    finally:
        db.close()
        
    return redirect(url_for('event_details', event_id=event_id))

# ------------------------------------------------------------------------------
# STUDENT DASHBOARD & PROFILE
# ------------------------------------------------------------------------------

@app.route('/student/dashboard')
@student_required
def student_dashboard():
    student_id = session['user_id']
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT r.*, e.title as event_title, e.category as event_category, e.event_date, e.start_time,
                       e.fee as event_fee, v.name as venue_name, c.name as club_name
                FROM registrations r
                JOIN events e ON r.event_id = e.id
                LEFT JOIN venues v ON e.venue_id = v.id
                LEFT JOIN clubs c ON e.club_id = c.id
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

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile_settings():
    """Allow every signed-in user type to edit their account details."""
    role = session.get('role')
    user_id = session['user_id']
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            table = 'students' if role == 'student' else 'admins' if role == 'admin' else 'club_members'
            if request.method == 'POST':
                name = request.form.get('name', '').strip()
                email = request.form.get('email', '').strip()
                phone = request.form.get('phone', '').strip()
                department = request.form.get('department', '').strip()
                new_password = request.form.get('new_password', '')
                if not name or not email:
                    flash('Name and email are required.', 'warning')
                    return redirect(url_for('profile_settings'))
                if new_password and len(new_password) < 6:
                    flash('Password must be at least 6 characters.', 'warning')
                    return redirect(url_for('profile_settings'))
                if role == 'student':
                    cursor.execute("UPDATE students SET name = %s, email = %s, phone = %s, department = %s WHERE id = %s", (name, email, phone, department, user_id))
                elif role == 'club':
                    cursor.execute("UPDATE club_members SET name = %s, email = %s, phone = %s, department = %s WHERE id = %s", (name, email, phone, department, user_id))
                else:
                    cursor.execute("UPDATE admins SET name = %s, email = %s WHERE id = %s", (name, email, user_id))
                if new_password:
                    cursor.execute(f"UPDATE {table} SET password_hash = %s WHERE id = %s", (generate_password_hash(new_password), user_id))
                session['name'] = name
                session['email'] = email
                session['department'] = department
                flash('Profile updated successfully.', 'success')
                return redirect(url_for('profile_settings'))
            cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (user_id,))
            user = cursor.fetchone()
    finally:
        db.close()
    return render_template('profile.html', user=user, role=role)

# ------------------------------------------------------------------------------
# CLUB PORTAL (FACULTY, LEADER, COORDINATOR, VOLUNTEER)
# ------------------------------------------------------------------------------

@app.route('/club/dashboard')
@club_required
def club_dashboard():
    club_id = session['club_id']
    member_id = session['user_id']
    club_role = session['club_role']
    
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            # Club stats
            cursor.execute("SELECT COUNT(*) as count FROM events WHERE club_id = %s", (club_id,))
            total_events = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM events WHERE club_id = %s AND status = 'upcoming'", (club_id,))
            active_events = cursor.fetchone()['count']

            cursor.execute("""
                SELECT COUNT(*) as count FROM registrations r
                JOIN events e ON r.event_id = e.id
                WHERE e.club_id = %s AND r.status IN ('registered', 'approved', 'attended')
            """, (club_id,))
            total_registrations = cursor.fetchone()['count']

            cursor.execute("""
                SELECT COUNT(*) as count FROM registrations r
                JOIN events e ON r.event_id = e.id
                WHERE e.club_id = %s AND r.status = 'attended'
            """, (club_id,))
            total_attended = cursor.fetchone()['count']

            # Club members
            cursor.execute("SELECT * FROM club_members WHERE club_id = %s ORDER BY FIELD(role, 'faculty', 'leader', 'coordinator', 'volunteer'), name ASC", (club_id,))
            members = cursor.fetchall()

            # Recent club events
            cursor.execute("""
                SELECT e.*, v.name as venue_name,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status IN ('registered', 'approved', 'attended')) as registered_count
                FROM events e
                LEFT JOIN venues v ON e.venue_id = v.id
                WHERE e.club_id = %s
                ORDER BY e.created_at DESC LIMIT 8
            """, (club_id,))
            events = cursor.fetchall()

            # Pending events waiting for this club's faculty
            pending_faculty_events = []
            if club_role == 'faculty':
                cursor.execute("""
                    SELECT e.*, m.name as creator_name, m.role as creator_role, v.name as venue_name
                    FROM events e
                    JOIN club_members m ON e.created_by_member_id = m.id
                    LEFT JOIN venues v ON e.venue_id = v.id
                    WHERE e.club_id = %s AND e.status = 'pending_faculty'
                    ORDER BY e.created_at DESC
                """, (club_id,))
                pending_faculty_events = cursor.fetchall()

            stats = {
                'total_events': total_events,
                'active_events': active_events,
                'total_registrations': total_registrations,
                'total_attended': total_attended,
                'member_count': len(members)
            }
    finally:
        db.close()
        
    return render_template(
        'club/dashboard.html',
        stats=stats,
        members=members,
        events=events,
        pending_faculty_events=pending_faculty_events
    )

@app.route('/club/events')
@club_required
def club_events():
    club_id = session['club_id']
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, v.name as venue_name,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status IN ('registered', 'approved', 'attended')) as registered_count,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status = 'attended') as attended_count,
                       (SELECT id FROM event_deletion_requests dr WHERE dr.event_id = e.id AND dr.status = 'pending' LIMIT 1) as has_pending_deletion
                FROM events e
                LEFT JOIN venues v ON e.venue_id = v.id
                WHERE e.club_id = %s
                ORDER BY e.event_date DESC
            """, (club_id,))
            events = cursor.fetchall()
    finally:
        db.close()
    return render_template('club/events.html', events=events)

@app.route('/club/events/create', methods=['GET', 'POST'])
@club_leader_or_faculty_required
def club_create_event():
    """
    Leader creates event -> sends to Club Faculty (pending_faculty)
    Faculty creates event -> sends directly to Admin (pending_admin)
    """
    club_id = session['club_id']
    member_id = session['user_id']
    club_role = session['club_role']
    
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
                attendance_incharge_id = request.form.get('attendance_incharge_member_id') or None
                if attendance_incharge_id:
                    attendance_incharge_id = int(attendance_incharge_id)
                    cursor.execute("SELECT id FROM club_members WHERE id = %s AND club_id = %s AND role IN ('coordinator', 'volunteer')", (attendance_incharge_id, club_id))
                    if not cursor.fetchone():
                        flash('Select a coordinator or volunteer from your club as attendance incharge.', 'warning')
                        attendance_incharge_id = None
                
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

                # Approval Flow Determination:
                if club_role == 'leader':
                    initial_status = 'pending_faculty'
                    flash_msg = f'Event proposal "{title}" created! Request submitted to Club Faculty Advisor for review.'
                else: # Faculty
                    initial_status = 'pending_admin'
                    flash_msg = f'Event proposal "{title}" registered! Forwarded to Central Administration for final approval.'

                cursor.execute("""
                    INSERT INTO events (
                        title, category, description, venue_id, event_date,
                        start_time, end_time, capacity, fee, banner_image,
                        payment_qr_image, upi_id, club_id, created_by_member_id, attendance_incharge_member_id, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    title, category, description, venue_id, event_date,
                    start_time, end_time, capacity, fee, banner_filename,
                    payment_qr_filename, upi_id, club_id, member_id, attendance_incharge_id, initial_status
                ))
                
                flash(flash_msg, 'success')
                return redirect(url_for('club_events'))

            cursor.execute("SELECT * FROM venues ORDER BY name ASC")
            venues = cursor.fetchall()
            cursor.execute("SELECT id, name, role FROM club_members WHERE club_id = %s AND role IN ('coordinator', 'volunteer') ORDER BY name", (club_id,))
            attendance_members = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('club/event_form.html', venues=venues, attendance_members=attendance_members)

@app.route('/club/approvals')
@club_faculty_required
def club_approvals():
    """Faculty reviews events created by Club Leader."""
    club_id = session['club_id']
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, m.name as creator_name, m.role as creator_role, v.name as venue_name, v.building as venue_building
                FROM events e
                JOIN club_members m ON e.created_by_member_id = m.id
                LEFT JOIN venues v ON e.venue_id = v.id
                WHERE e.club_id = %s AND e.status = 'pending_faculty'
                ORDER BY e.created_at DESC
            """, (club_id,))
            pending_events = cursor.fetchall()
    finally:
        db.close()
    return render_template('club/approvals.html', pending_events=pending_events)

@app.route('/club/approvals/<int:event_id>/<action>', methods=['POST'])
@club_faculty_required
def club_review_action(event_id, action):
    club_id = session['club_id']
    remarks = request.form.get('remarks', '').strip()
    
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM events WHERE id = %s AND club_id = %s AND status = 'pending_faculty'", (event_id, club_id))
            event = cursor.fetchone()
            if not event:
                flash('Event request not found or already processed.', 'danger')
                return redirect(url_for('club_approvals'))

            if action == 'forward_to_admin':
                now = datetime.now()
                cursor.execute("""
                    UPDATE events SET status = 'pending_admin', faculty_approved_at = %s, faculty_remarks = %s
                    WHERE id = %s
                """, (now, remarks or 'Approved and forwarded to Central Admin by Club Faculty Advisor', event_id))
                flash(f'Event "{event["title"]}" approved! Request forwarded to Central Administration.', 'success')
            elif action == 'reject':
                cursor.execute("""
                    UPDATE events SET status = 'rejected', faculty_remarks = %s
                    WHERE id = %s
                """, (remarks or 'Rejected by Club Faculty Advisor', event_id))
                flash(f'Event "{event["title"]}" was rejected.', 'warning')
    finally:
        db.close()
        
    return redirect(url_for('club_approvals'))

@app.route('/club/events/<int:event_id>/request-deletion', methods=['POST'])
@club_leader_or_faculty_required
def club_request_deletion(event_id):
    """Club cannot directly delete events; they submit a deletion request to Admin."""
    club_id = session['club_id']
    member_id = session['user_id']
    reason = request.form.get('reason', '').strip()
    
    if not reason:
        flash('Please provide a valid reason for event deletion.', 'warning')
        return redirect(url_for('club_events'))
        
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM events WHERE id = %s AND club_id = %s", (event_id, club_id))
            event = cursor.fetchone()
            if not event:
                flash('Event not found or unauthorized.', 'danger')
                return redirect(url_for('club_events'))

            cursor.execute("""
                INSERT INTO event_deletion_requests (event_id, requested_by_member_id, requested_by_role, requested_by_name, reason)
                VALUES (%s, %s, %s, %s, %s)
            """, (event_id, member_id, session['club_role'], session['name'], reason))
            
            flash(f'Deletion request for "{event["title"]}" submitted to Central Administration for approval.', 'info')
    finally:
        db.close()
        
    return redirect(url_for('club_events'))

@app.route('/club/attendance/<int:event_id>')
@club_required
def club_attendance_desk(event_id):
    """QR-based attendance desk for the event."""
    club_id = session['club_id']
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, c.name as club_name, v.name as venue_name
                FROM events e
                LEFT JOIN clubs c ON e.club_id = c.id
                LEFT JOIN venues v ON e.venue_id = v.id
                WHERE e.id = %s
            """, (event_id,))
            event = cursor.fetchone()
            
            if not event:
                flash('Event not found.', 'danger')
                return redirect(url_for('club_events'))

            if event['club_id'] != club_id or event.get('attendance_incharge_member_id') != session['user_id']:
                flash('Only the assigned attendance incharge can open this scanner.', 'danger')
                return redirect(url_for('club_events'))

            cursor.execute("""
                SELECT r.*, s.name as student_name, s.roll_number, s.department, s.year_of_study, s.email, s.phone
                FROM registrations r
                JOIN students s ON r.student_id = s.id
                WHERE r.event_id = %s
                ORDER BY r.status DESC, s.name ASC
            """, (event_id,))
            participants = cursor.fetchall()
            
            attended_count = sum(1 for p in participants if p['status'] == 'attended')
    finally:
        db.close()
        
    return render_template(
        'club/attendance.html',
        event=event,
        participants=participants,
        attended_count=attended_count
    )

@app.route('/api/club/scan-ticket', methods=['POST'])
@club_required
def api_club_scan_ticket():
    """Live QR code scanner verification endpoint for gate check-in."""
    data = request.get_json() or {}
    ticket_code = data.get('ticket_code', '').strip()
    event_id = data.get('event_id')
    
    if not ticket_code:
        return jsonify({'success': False, 'message': 'Ticket code is required.'}), 400
        
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT id FROM events WHERE id = %s AND attendance_incharge_member_id = %s AND club_id = %s", (event_id, session['user_id'], session['club_id']))
            if not cursor.fetchone():
                return jsonify({'success': False, 'message': 'You are not assigned as attendance incharge for this event.'}), 403

            cursor.execute("""
                SELECT r.*, s.name as student_name, s.roll_number, s.department, s.email,
                       e.title as event_title, e.id as actual_event_id
                FROM registrations r
                JOIN students s ON r.student_id = s.id
                JOIN events e ON r.event_id = e.id
                WHERE r.ticket_code = %s
            """, (ticket_code,))
            reg = cursor.fetchone()
            
            if not reg:
                return jsonify({'success': False, 'message': 'Invalid pass! Ticket code not found.'}), 404
                
            if event_id and int(event_id) != reg['actual_event_id']:
                return jsonify({
                    'success': False,
                    'message': f'Ticket belongs to "{reg["event_title"]}", not this gate.'
                }), 400
                
            if reg['status'] == 'attended':
                att_str = reg['attended_at'].strftime('%I:%M %p, %b %d') if reg['attended_at'] else 'Earlier'
                return jsonify({
                    'success': False,
                    'already_attended': True,
                    'message': f'Already Checked In at {att_str}',
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
                    'message': f'Payment Pending: Pass for {reg["student_name"]} has not been verified.'
                }), 400
                
            now = datetime.now()
            cursor.execute("""
                UPDATE registrations SET status = 'attended', attended_at = %s, attended_by_member_id = %s
                WHERE id = %s
            """, (now, session['user_id'], reg['id']))
            
            return jsonify({
                'success': True,
                'message': 'Attendance Verified & Checked In!',
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

@app.route('/club/attendance/export/<int:event_id>')
@club_required
def club_export_attendance(event_id):
    """Download attendance report in Excel (.xlsx) format for Club."""
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, c.name as club_name, v.name as venue_name, v.building as venue_building
                FROM events e
                LEFT JOIN clubs c ON e.club_id = c.id
                LEFT JOIN venues v ON e.venue_id = v.id
                WHERE e.id = %s
            """, (event_id,))
            event = cursor.fetchone()
            if not event:
                flash('Event not found.', 'danger')
                return redirect(url_for('club_events'))
            if event['club_id'] != session['club_id'] or session.get('club_role') not in ('faculty', 'leader'):
                flash('Only the club faculty or leader can export this attendance.', 'danger')
                return redirect(url_for('club_events'))

            cursor.execute("""
                SELECT r.*, s.name as student_name, s.roll_number, s.department, s.year_of_study, s.email, s.phone
                FROM registrations r
                JOIN students s ON r.student_id = s.id
                WHERE r.event_id = %s
                ORDER BY s.name ASC
            """, (event_id,))
            participants = cursor.fetchall()
            
            excel_stream = build_attendance_excel(event, participants)
            safe_title = "".join(c for c in event['title'] if c.isalnum() or c in (' ', '_', '-')).rstrip()
            filename = f"RGCET_Attendance_{safe_title}_{datetime.now().strftime('%Y%m%d')}.xlsx"
            
            return send_file(
                excel_stream,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=filename
            )
    finally:
        db.close()

@app.route('/club/members')
@club_required
def club_members():
    club_id = session['club_id']
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT m.*, c.name as club_name
                FROM club_members m
                JOIN clubs c ON m.club_id = c.id
                WHERE m.club_id = %s
                ORDER BY FIELD(m.role, 'faculty', 'leader', 'coordinator', 'volunteer'), m.name ASC
            """, (club_id,))
            members = cursor.fetchall()
    finally:
        db.close()
    return render_template('club/members.html', members=members)

# ------------------------------------------------------------------------------
# CENTRAL ADMIN PORTAL
# ------------------------------------------------------------------------------

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM events WHERE status = 'upcoming'")
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

            # Pending event approvals from Faculty
            cursor.execute("""
                SELECT e.*, c.name as club_name, v.name as venue_name, m.name as creator_name, m.role as creator_role
                FROM events e
                LEFT JOIN clubs c ON e.club_id = c.id
                LEFT JOIN venues v ON e.venue_id = v.id
                LEFT JOIN club_members m ON e.created_by_member_id = m.id
                WHERE e.status = 'pending_admin'
                ORDER BY e.created_at ASC
            """)
            pending_events = cursor.fetchall()

            # Pending deletion requests from Clubs
            cursor.execute("""
                SELECT dr.*, e.title as event_title, e.event_date, c.name as club_name
                FROM event_deletion_requests dr
                JOIN events e ON dr.event_id = e.id
                LEFT JOIN clubs c ON e.club_id = c.id
                WHERE dr.status = 'pending'
                ORDER BY dr.created_at ASC
            """)
            pending_deletions = cursor.fetchall()
            
            # Recent active events
            cursor.execute("""
                SELECT e.*, v.name as venue_name, c.name as club_name,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status IN ('registered', 'approved', 'attended')) as registered_count
                FROM events e
                LEFT JOIN venues v ON e.venue_id = v.id
                LEFT JOIN clubs c ON e.club_id = c.id
                WHERE e.status = 'upcoming'
                ORDER BY e.event_date ASC LIMIT 6
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
        
    return render_template(
        'admin/dashboard.html',
        stats=stats,
        events=events,
        pending_events=pending_events,
        pending_deletions=pending_deletions
    )

@app.route('/admin/events')
@admin_required
def admin_events():
    """Admin can directly add, edit, or delete any event."""
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, v.name as venue_name, c.name as club_name,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status IN ('registered', 'approved', 'attended')) as total_registered,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status = 'attended') as total_attended,
                       (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.payment_status = 'pending') as pending_payments
                FROM events e
                LEFT JOIN venues v ON e.venue_id = v.id
                LEFT JOIN clubs c ON e.club_id = c.id
                ORDER BY e.event_date DESC
            """)
            events = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('admin/events.html', events=events)

@app.route('/admin/clubs/create', methods=['GET', 'POST'])
@admin_required
def admin_create_club():
    """Allow the only central administrator to add a club."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip().upper()
        category = request.form.get('category', '').strip()
        advisor = request.form.get('faculty_advisor_name', '').strip()
        description = request.form.get('description', '').strip()
        if not name or not code or not category or not advisor:
            flash('Club name, code, category, and advisor are required.', 'warning')
            return render_template('admin/club_form.html')
        db = get_db_connection()
        try:
            with db.cursor() as cursor:
                cursor.execute("INSERT INTO clubs (name, code, category, faculty_advisor_name, description) VALUES (%s, %s, %s, %s, %s)", (name, code, category, advisor, description))
        finally:
            db.close()
        flash(f'Club "{name}" created successfully.', 'success')
        return redirect(url_for('admin_create_club'))
    return render_template('admin/club_form.html')

@app.route('/admin/events/create', methods=['GET', 'POST'])
@admin_required
def admin_create_event():
    """Admin can directly create and publish an event immediately."""
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            if request.method == 'POST':
                title = request.form.get('title', '').strip()
                category = request.form.get('category', '').strip()
                description = request.form.get('description', '').strip()
                venue_id = int(request.form.get('venue_id'))
                club_id = request.form.get('club_id')
                club_id = int(club_id) if club_id else None
                event_date = request.form.get('event_date')
                start_time = request.form.get('start_time')
                end_time = request.form.get('end_time')
                capacity = int(request.form.get('capacity', 50))
                fee = float(request.form.get('fee', 0.00))
                upi_id = request.form.get('upi_id', '').strip()
                
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
                    
                # Admin direct create is published immediately
                cursor.execute("""
                    INSERT INTO events (
                        title, category, description, venue_id, event_date,
                        start_time, end_time, capacity, fee, banner_image,
                        payment_qr_image, upi_id, club_id, status, created_by, admin_approved_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'upcoming', %s, %s)
                """, (
                    title, category, description, venue_id, event_date,
                    start_time, end_time, capacity, fee, banner_filename,
                    payment_qr_filename, upi_id, club_id, session['user_id'], datetime.now()
                ))
                
                flash(f'Event "{title}" published directly to Home Page and Calendar!', 'success')
                return redirect(url_for('admin_events'))
                
            cursor.execute("SELECT * FROM venues ORDER BY name ASC")
            venues = cursor.fetchall()
            cursor.execute("SELECT * FROM clubs ORDER BY name ASC")
            clubs = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('admin/event_form.html', venues=venues, clubs=clubs, event=None)

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
                club_id = request.form.get('club_id')
                club_id = int(club_id) if club_id else None
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
                        title = %s, category = %s, description = %s, venue_id = %s, club_id = %s,
                        event_date = %s, start_time = %s, end_time = %s, capacity = %s,
                        fee = %s, banner_image = %s, payment_qr_image = %s, upi_id = %s, status = %s
                    WHERE id = %s
                """, (
                    title, category, description, venue_id, club_id,
                    event_date, start_time, end_time, capacity,
                    fee, banner_filename, payment_qr_filename, upi_id, status, event_id
                ))
                
                flash(f'Event "{title}" updated successfully!', 'success')
                return redirect(url_for('admin_events'))
                
            cursor.execute("SELECT * FROM venues ORDER BY name ASC")
            venues = cursor.fetchall()
            cursor.execute("SELECT * FROM clubs ORDER BY name ASC")
            clubs = cursor.fetchall()
    finally:
        db.close()
        
    return render_template('admin/event_form.html', venues=venues, clubs=clubs, event=event)

@app.route('/admin/events/<int:event_id>/delete', methods=['POST'])
@admin_required
def admin_delete_event(event_id):
    """Admin has direct authority to delete events."""
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
            flash('Event deleted from system by Central Administrator.', 'info')
    finally:
        db.close()
    return redirect(url_for('admin_events'))

@app.route('/admin/approvals')
@admin_required
def admin_approvals():
    """Review events forwarded by Faculty (status: pending_admin)."""
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, c.name as club_name, c.code as club_code, v.name as venue_name, v.building as venue_building,
                       m.name as creator_name, m.role as creator_role
                FROM events e
                LEFT JOIN clubs c ON e.club_id = c.id
                LEFT JOIN venues v ON e.venue_id = v.id
                LEFT JOIN club_members m ON e.created_by_member_id = m.id
                WHERE e.status = 'pending_admin'
                ORDER BY e.created_at ASC
            """)
            pending_events = cursor.fetchall()
    finally:
        db.close()
    return render_template('admin/approvals.html', pending_events=pending_events)

@app.route('/admin/approvals/<int:event_id>/<action>', methods=['POST'])
@admin_required
def admin_review_action(event_id, action):
    remarks = request.form.get('remarks', '').strip()
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM events WHERE id = %s AND status = 'pending_admin'", (event_id,))
            event = cursor.fetchone()
            if not event:
                flash('Pending event not found or already processed.', 'danger')
                return redirect(url_for('admin_approvals'))

            if action == 'approve':
                now = datetime.now()
                cursor.execute("""
                    UPDATE events SET status = 'upcoming', admin_approved_at = %s, admin_remarks = %s
                    WHERE id = %s
                """, (now, remarks or 'Approved by Central Administration', event_id))
                flash(f'Event "{event["title"]}" approved and published to Public Home Page & Calendar!', 'success')
            elif action == 'reject':
                cursor.execute("""
                    UPDATE events SET status = 'rejected', admin_remarks = %s
                    WHERE id = %s
                """, (remarks or 'Proposal rejected by Central Administration', event_id))
                flash(f'Event "{event["title"]}" proposal was rejected.', 'warning')
    finally:
        db.close()
    return redirect(url_for('admin_approvals'))

@app.route('/admin/deletion-requests')
@admin_required
def admin_deletion_requests():
    """Review event deletion requests submitted by clubs."""
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT dr.*, e.title as event_title, e.event_date, e.category as event_category,
                       c.name as club_name
                FROM event_deletion_requests dr
                JOIN events e ON dr.event_id = e.id
                LEFT JOIN clubs c ON e.club_id = c.id
                ORDER BY dr.created_at DESC
            """)
            requests = cursor.fetchall()
    finally:
        db.close()
    return render_template('admin/deletion_requests.html', deletion_requests=requests)

@app.route('/admin/deletion-requests/<int:req_id>/<action>', methods=['POST'])
@admin_required
def admin_process_deletion_request(req_id, action):
    remarks = request.form.get('admin_remarks', '').strip()
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM event_deletion_requests WHERE id = %s AND status = 'pending'", (req_id,))
            del_req = cursor.fetchone()
            if not del_req:
                flash('Deletion request not found or already reviewed.', 'danger')
                return redirect(url_for('admin_deletion_requests'))

            now = datetime.now()
            if action == 'approve':
                # Approve deletion -> delete or cancel the event
                cursor.execute("UPDATE event_deletion_requests SET status = 'approved', admin_remarks = %s, reviewed_at = %s WHERE id = %s", (remarks or 'Approved', now, req_id))
                cursor.execute("DELETE FROM events WHERE id = %s", (del_req['event_id'],))
                flash('Deletion request approved! Event has been removed from the portal.', 'success')
            elif action == 'reject':
                cursor.execute("UPDATE event_deletion_requests SET status = 'rejected', admin_remarks = %s, reviewed_at = %s WHERE id = %s", (remarks or 'Rejected', now, req_id))
                flash('Deletion request rejected. Event remains active.', 'info')
    finally:
        db.close()
    return redirect(url_for('admin_deletion_requests'))

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

@app.route('/admin/participants')
@admin_required
def admin_participants():
    """
    Participant view & Excel export in Admin page.
    (Note: Attendance QR scanner removed from admin page as requested).
    """
    event_id = request.args.get('event_id')
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            query = """
                SELECT r.*, s.name as student_name, s.email, s.roll_number, s.department, s.year_of_study, s.phone,
                       e.title as event_title, e.event_date, c.name as club_name
                FROM registrations r
                JOIN students s ON r.student_id = s.id
                JOIN events e ON r.event_id = e.id
                LEFT JOIN clubs c ON e.club_id = c.id
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
def admin_export_attendance(event_id):
    """Download attendance report in Excel (.xlsx) format for Admin."""
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, c.name as club_name, v.name as venue_name, v.building as venue_building
                FROM events e
                LEFT JOIN clubs c ON e.club_id = c.id
                LEFT JOIN venues v ON e.venue_id = v.id
                WHERE e.id = %s
            """, (event_id,))
            event = cursor.fetchone()
            if not event:
                flash('Event not found.', 'danger')
                return redirect(url_for('admin_participants'))

            cursor.execute("""
                SELECT r.*, s.name as student_name, s.roll_number, s.department, s.year_of_study, s.email, s.phone
                FROM registrations r
                JOIN students s ON r.student_id = s.id
                WHERE r.event_id = %s
                ORDER BY s.name ASC
            """, (event_id,))
            participants = cursor.fetchall()
            
            excel_stream = build_attendance_excel(event, participants)
            safe_title = "".join(c for c in event['title'] if c.isalnum() or c in (' ', '_', '-')).rstrip()
            filename = f"RGCET_Attendance_{safe_title}_{datetime.now().strftime('%Y%m%d')}.xlsx"
            
            return send_file(
                excel_stream,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=filename
            )
    finally:
        db.close()

@app.route('/admin/announcements', methods=['GET', 'POST'])
@admin_required
def admin_announcements():
    """Admin can directly create, publish, and manage campus notices."""
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
                    flash('Official notice published directly to campus desk!', 'success')
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

@app.route('/admin/venues', methods=['GET', 'POST'])
@admin_required
def admin_venues():
    """Admin only can add/edit/delete venues."""
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

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
