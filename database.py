import pymysql
import pymysql.cursors
import os
import qrcode
from werkzeug.security import generate_password_hash
from datetime import datetime, date, time, timedelta
from config import Config

def ensure_upload_dirs():
    """Ensure all upload directories exist."""
    dirs = [
        Config.UPLOAD_FOLDER,
        Config.BANNERS_FOLDER,
        Config.PAYMENT_QRS_FOLDER,
        Config.RECEIPTS_FOLDER,
        Config.TICKETS_FOLDER,
        os.path.join(Config.UPLOAD_FOLDER, 'members')
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

def get_db_connection():
    """Get an active connection to MySQL."""
    return pymysql.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        port=Config.MYSQL_PORT,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

def generate_member_qr(member_code):
    """Generate high-contrast QR code for Club Member Badge."""
    ensure_upload_dirs()
    filename = f"mem_{member_code}.png"
    folder = os.path.join(Config.UPLOAD_FOLDER, 'members')
    filepath = os.path.join(folder, filename)
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(member_code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1E3A8A", back_color="white")
    img.save(filepath)
    return filename

def init_db():
    """Create database and tables if they don't already exist."""
    ensure_upload_dirs()
    
    # 1. Ensure Database Exists
    conn = pymysql.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        port=Config.MYSQL_PORT,
        autocommit=True
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{Config.MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    finally:
        conn.close()

    # 2. Ensure Tables and Schema
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            # Students
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(150) NOT NULL UNIQUE,
                roll_number VARCHAR(50) NOT NULL UNIQUE,
                department VARCHAR(100) NOT NULL,
                year_of_study VARCHAR(20) NOT NULL,
                phone VARCHAR(20) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Central Admins
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(150) NOT NULL UNIQUE,
                role VARCHAR(50) NOT NULL DEFAULT 'Administrator',
                password_hash VARCHAR(255) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Clubs
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS clubs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(150) NOT NULL,
                code VARCHAR(50) NOT NULL UNIQUE,
                category VARCHAR(50) NOT NULL,
                faculty_advisor_name VARCHAR(100) NOT NULL,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Club Members (Faculty, Leader, Coordinator, Volunteer)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS club_members (
                id INT AUTO_INCREMENT PRIMARY KEY,
                club_id INT NOT NULL,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(150) NOT NULL UNIQUE,
                phone VARCHAR(20) NOT NULL,
                department VARCHAR(100) NOT NULL,
                role ENUM('faculty', 'leader', 'coordinator', 'volunteer') NOT NULL DEFAULT 'volunteer',
                password_hash VARCHAR(255) NOT NULL,
                member_code VARCHAR(64) NOT NULL UNIQUE,
                qr_code_image VARCHAR(255) NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Venues
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS venues (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                building VARCHAR(100) NOT NULL,
                capacity INT NOT NULL DEFAULT 100,
                location_details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Events
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                category VARCHAR(50) NOT NULL,
                description TEXT NOT NULL,
                venue_id INT NULL,
                event_date DATE NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                capacity INT NOT NULL DEFAULT 50,
                fee DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
                banner_image VARCHAR(255) NULL,
                payment_qr_image VARCHAR(255) NULL,
                upi_id VARCHAR(100) NULL,
                club_id INT NULL,
                created_by_member_id INT NULL,
                created_by INT NULL,
                status ENUM('pending_faculty', 'pending_admin', 'upcoming', 'ongoing', 'completed', 'rejected', 'cancelled') NOT NULL DEFAULT 'upcoming',
                faculty_approved_at DATETIME NULL,
                faculty_remarks TEXT NULL,
                admin_approved_at DATETIME NULL,
                admin_remarks TEXT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (venue_id) REFERENCES venues(id) ON DELETE SET NULL,
                FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE SET NULL,
                FOREIGN KEY (created_by_member_id) REFERENCES club_members(id) ON DELETE SET NULL,
                FOREIGN KEY (created_by) REFERENCES admins(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Event Deletion Requests
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS event_deletion_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                event_id INT NOT NULL,
                requested_by_member_id INT NOT NULL,
                requested_by_role VARCHAR(50) NOT NULL,
                requested_by_name VARCHAR(100) NOT NULL,
                reason TEXT NOT NULL,
                status ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending',
                admin_remarks TEXT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                reviewed_at DATETIME NULL,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
                FOREIGN KEY (requested_by_member_id) REFERENCES club_members(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Registrations
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS registrations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                event_id INT NOT NULL,
                ticket_code VARCHAR(64) NOT NULL UNIQUE,
                payment_status ENUM('free', 'pending', 'verified', 'rejected') NOT NULL DEFAULT 'free',
                payment_ref_no VARCHAR(100) NULL,
                payment_screenshot VARCHAR(255) NULL,
                status ENUM('registered', 'approved', 'rejected', 'attended', 'cancelled') NOT NULL DEFAULT 'registered',
                qr_code_image VARCHAR(255) NULL,
                registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                attended_at DATETIME NULL,
                attended_by_member_id INT NULL,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
                FOREIGN KEY (attended_by_member_id) REFERENCES club_members(id) ON DELETE SET NULL,
                UNIQUE KEY unique_student_event (student_id, event_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Notifications
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                message TEXT NOT NULL,
                event_id INT NULL,
                target_audience ENUM('all', 'registered_students', 'admins', 'clubs') NOT NULL DEFAULT 'all',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Feedback
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                event_id INT NOT NULL,
                rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
                comments TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
                UNIQUE KEY unique_student_feedback (student_id, event_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Migrate schema if columns are missing from existing older tables
            migrate_schema_columns(cursor)
            ensure_one_admin(cursor)

        seed_default_data_if_needed(db)
        print("Database schema successfully initialized!")
    finally:
        db.close()

def migrate_schema_columns(cursor):
    """Safely add new columns to existing events and registrations tables if needed."""
    try:
        cursor.execute("SHOW COLUMNS FROM events LIKE 'club_id'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE events ADD COLUMN club_id INT NULL AFTER upi_id")
            cursor.execute("ALTER TABLE events ADD FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE SET NULL")
    except Exception as e:
        print(f"Migration note (club_id): {e}")

    try:
        cursor.execute("SHOW COLUMNS FROM events LIKE 'created_by_member_id'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE events ADD COLUMN created_by_member_id INT NULL AFTER club_id")
            cursor.execute("ALTER TABLE events ADD FOREIGN KEY (created_by_member_id) REFERENCES club_members(id) ON DELETE SET NULL")
    except Exception as e:
        print(f"Migration note (created_by_member_id): {e}")

    try:
        cursor.execute("SHOW COLUMNS FROM events LIKE 'faculty_approved_at'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE events ADD COLUMN faculty_approved_at DATETIME NULL")
            cursor.execute("ALTER TABLE events ADD COLUMN faculty_remarks TEXT NULL")
            cursor.execute("ALTER TABLE events ADD COLUMN admin_approved_at DATETIME NULL")
            cursor.execute("ALTER TABLE events ADD COLUMN admin_remarks TEXT NULL")
    except Exception as e:
        print(f"Migration note (approval columns): {e}")

    try:
        cursor.execute("""
            ALTER TABLE events MODIFY COLUMN status 
            ENUM('pending_faculty', 'pending_admin', 'upcoming', 'ongoing', 'completed', 'rejected', 'cancelled') 
            NOT NULL DEFAULT 'upcoming'
        """)
    except Exception as e:
        print(f"Migration note (events status enum): {e}")

    try:
        cursor.execute("SHOW COLUMNS FROM registrations LIKE 'attended_by_member_id'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE registrations ADD COLUMN attended_by_member_id INT NULL")
            cursor.execute("ALTER TABLE registrations ADD FOREIGN KEY (attended_by_member_id) REFERENCES club_members(id) ON DELETE SET NULL")
    except Exception as e:
        print(f"Migration note (attended_by_member_id): {e}")

    try:
        cursor.execute("SHOW COLUMNS FROM club_members LIKE 'role'")
        role_column = cursor.fetchone()
        if role_column and 'ex_leader' not in role_column['Type']:
            cursor.execute("ALTER TABLE club_members MODIFY COLUMN role ENUM('faculty', 'leader', 'ex_leader', 'coordinator', 'volunteer') NOT NULL DEFAULT 'volunteer'")
    except Exception as e:
        print(f"Migration note (club member roles): {e}")

    try:
        cursor.execute("SHOW COLUMNS FROM events LIKE 'attendance_incharge_member_id'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE events ADD COLUMN attendance_incharge_member_id INT NULL AFTER created_by_member_id")
            cursor.execute("ALTER TABLE events ADD FOREIGN KEY (attendance_incharge_member_id) REFERENCES club_members(id) ON DELETE SET NULL")
    except Exception as e:
        print(f"Migration note (attendance incharge): {e}")

def ensure_one_admin(cursor):
    """Keep one centrally configured administrator and never create demo credentials."""
    cursor.execute("SELECT id FROM admins ORDER BY id ASC")
    admins = cursor.fetchall()
    admin_email = os.environ.get('ADMIN_EMAIL', '').strip()
    admin_password = os.environ.get('ADMIN_PASSWORD', '')
    admin_name = os.environ.get('ADMIN_NAME', 'Central Admin').strip()

    if not admins:
        if admin_email and admin_password:
            cursor.execute("INSERT INTO admins (name, email, role, password_hash) VALUES (%s, %s, 'Administrator', %s)", (admin_name, admin_email, generate_password_hash(admin_password)))
        return

    keep_id = admins[0]['id']
    cursor.execute("DELETE FROM admins WHERE id <> %s", (keep_id,))
    if admin_email and admin_password:
        cursor.execute("UPDATE admins SET name = %s, email = %s, role = 'Administrator', password_hash = %s WHERE id = %s", (admin_name, admin_email, generate_password_hash(admin_password), keep_id))
    else:
        cursor.execute("UPDATE admins SET name = 'Central Admin', role = 'Administrator' WHERE id = %s", (keep_id,))

def seed_default_data_if_needed(db):
    """Seed initial clubs, venues, and campus events."""
    with db.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM clubs")
        has_clubs = cursor.fetchone()['count'] > 0
        if has_clubs:
            return

        print("Seeding initial RGCET clubs, venues, and events...")

        # 1. Clubs
        cursor.execute("""
            INSERT INTO clubs (name, code, category, faculty_advisor_name, description) VALUES
            ('Bytes Coding & Open Source Club', 'RGCET-BYTES', 'Technical', 'Dr. K. Parthiban',
             'The official computer science & software engineering club of RGCET. Organizes annual hackathons, competitive programming sprints, open source bootcamps, and web/AI workshops.'),
            ('RoboTech & Automation Society', 'RGCET-ROBO', 'Robotics & IoT', 'Prof. S. Senthil',
             'Pioneering combat robotics, drone building, embedded systems, and IoT automation projects across engineering branches.'),
            ('Rhythms Cultural & Fine Arts Club', 'RGCET-RHYTHM', 'Cultural & Arts', 'Dr. M. Deepa',
             'The heart of campus creativity! Hosting inter-collegiate music fests, choreo nights, theater, photography, and art installations.'),
            ('IEEE RGCET Student Branch', 'RGCET-IEEE', 'Academic & Research', 'Dr. R. Rajesh',
             'Connecting student researchers and innovators with global IEEE standards, paper presentations, seminars, and tech conferences.'),
            ('Apex Sports & Athletics Club', 'RGCET-SPORTS', 'Sports & Fitness', 'Coach D. Anbazhagan',
             'Promoting athletic spirit, cricket tournaments, volleyball championships, track & field meets, and campus fitness drives.')
        """)

        # 2. Venues
        cursor.execute("SELECT name FROM venues")
        existing_venues = {v['name'] for v in cursor.fetchall()}
        default_venues = [
            ('Dr. APJ Abdul Kalam Grand Auditorium', 'Main Academic Complex', 800, 'Ground Floor, Central Block A, RGCET Campus'),
            ('Turing Advanced AI & Computing Lab', 'Dept of CSE & IT', 120, '3rd Floor, Tech Park Wing B'),
            ('RGCET Open Air Amphitheatre', 'Student Activities Hub', 1200, 'Adjacent to College Cafeteria & Ground'),
            ('Sir C.V. Raman Seminar Hall', 'Admin & PG Block', 250, '1st Floor, Room 108'),
            ('RGCET Indoor Sports Pavilion', 'Sports Complex', 500, 'East Campus Ground')
        ]
        for v_name, v_bld, v_cap, v_loc in default_venues:
            if v_name not in existing_venues:
                cursor.execute("""
                    INSERT INTO venues (name, building, capacity, location_details) VALUES (%s, %s, %s, %s)
                """, (v_name, v_bld, v_cap, v_loc))

        # 6. Events with Multi-Tier Statuses
        today = date.today()
        cursor.execute("""
            INSERT INTO events (title, category, description, venue_id, event_date, start_time, end_time, capacity, fee, banner_image, upi_id, club_id, created_by_member_id, status) VALUES
            ('HackRGCET 2026: 24-Hour AI & Web3 National Hackathon', 'Hackathon',
             'The flagship annual hackathon of Rajiv Gandhi College of Engineering and Technology! Build disruptive software and hardware in Agentic AI, Decentralized Web, and IoT. Mentorship from top tech leads, food, swags, and Rs. 75,000 in prizes.',
             2, %s, '09:00:00', '21:00:00', 100, 0.00, 'hackathon_2026.jpg', 'rgcet@upi', 1, NULL, 'upcoming'),
             
            ('Innovatia 2026: National Level Technical Symposium', 'Symposium',
             'RGCET annual tech festival featuring Paper Presentations, Code Debugging, Circuit Cracking, Web Design Challenges, and Project Expos across all engineering streams.',
             1, %s, '09:30:00', '17:00:00', 350, 150.00, 'symposium_2026.jpg', 'innovatia@okhdfcbank', 4, NULL, 'upcoming'),

            ('Dhruva 2026: Inter-College Cultural Extravaganza', 'Cultural Fest',
             'Two energetic days of battle of the bands, classical & western dance face-offs, drama, fashion walks, and a grand live DJ evening. Free entry with RGCET student pass.',
             3, %s, '16:00:00', '22:30:00', 800, 0.00, 'euphoria_fest.jpg', 'cultural@upi', 3, NULL, 'upcoming'),

            ('Generative AI & LLM Engineering Masterclass', 'Workshop',
             'Hands-on masterclass covering Prompt Engineering, RAG architectures with LangChain, local LLM deployment with Ollama, and fine-tuning with Python. Verified certificate awarded.',
             2, %s, '10:00:00', '16:00:00', 60, 100.00, 'ai_summit.jpg', 'bytes@paytm', 1, NULL, 'upcoming'),

            ('RoboWars 2026: Arena Combat Championship', 'Robotics',
             'Custom RC battlebots fight inside the heavy polycarbonate arena! Weight classes: 15kg & 30kg. Witness thrilling high-torque mechanical battles.',
             1, %s, '11:00:00', '18:00:00', 200, 150.00, 'robowars.jpg', 'robotics@upi', 2, NULL, 'upcoming'),

            ('Cloud Native DevOps & Kubernetes Workshop', 'Workshop',
             'Comprehensive hands-on training on Docker containerization, Kubernetes orchestration, CI/CD pipelines, and cloud deployment with AWS.',
             4, %s, '09:30:00', '15:30:00', 75, 50.00, 'devops.jpg', 'bytes@upi', 1, NULL, 'pending_admin'),

            ('Campus Esports Championship: Valorant & BGMI', 'Gaming',
             'Inter-departmental collegiate championship featuring 5v5 Valorant and 4-squad BGMI showdown with live casters and gaming mechanical keyboards for winners.',
             4, %s, '13:00:00', '19:00:00', 100, 100.00, 'esports_cup.jpg', 'esports@upi', 1, NULL, 'pending_faculty')
        """, (
            today + timedelta(days=4),
            today + timedelta(days=9),
            today + timedelta(days=14),
            today + timedelta(days=7),
            today + timedelta(days=18),
            today + timedelta(days=22),
            today + timedelta(days=11)
        ))

        # 7. Announcements
        cursor.execute("""
            INSERT INTO notifications (title, message, target_audience) VALUES
            ('📌 Welcome to Rajiv Gandhi College of Engineering & Technology Event Hub!', 
             'Official portal for all RGCET technical symposiums, hackathons, workshops, cultural fests, and athletic meets. Claim your verified digital entry pass!', 'all'),
            ('🚀 HackRGCET 2026 Registration Open', 
             'Teams of 2-4 members from CSE, IT, AI&DS, ECE, EEE, and Mech can register on the portal now. Bring student ID cards for gate check-in.', 'all'),
            ('📢 Club Proposals Notice',
             'All Club Leaders and Faculty Advisors are requested to submit event approval proposals at least 7 days in advance for venue allocation.', 'all')
        """)

        print("RGCET seed data created successfully!")

if __name__ == '__main__':
    init_db()
