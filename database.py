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
        Config.TICKETS_FOLDER
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

def init_db():
    """Create database and tables if they don't already exist."""
    ensure_upload_dirs()
    
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

    db = get_db_connection()
    try:
        with db.cursor() as cursor:
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

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(150) NOT NULL UNIQUE,
                role VARCHAR(50) NOT NULL DEFAULT 'Organizer',
                password_hash VARCHAR(255) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

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
                status ENUM('upcoming', 'ongoing', 'completed', 'cancelled') NOT NULL DEFAULT 'upcoming',
                created_by INT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (venue_id) REFERENCES venues(id) ON DELETE SET NULL,
                FOREIGN KEY (created_by) REFERENCES admins(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

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
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
                UNIQUE KEY unique_student_event (student_id, event_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                message TEXT NOT NULL,
                event_id INT NULL,
                target_audience ENUM('all', 'registered_students', 'admins') NOT NULL DEFAULT 'all',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

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
        
        # Check and seed sample data if tables are empty
        seed_default_data_if_needed(db)
        print("Database schema successfully initialized!")
    finally:
        db.close()

def seed_default_data_if_needed(db):
    """Seed demo accounts, venues, and events if database is newly initialized."""
    with db.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM admins")
        if cursor.fetchone()['count'] > 0:
            return  
        
        print("Seeding demo students, faculty, venues, and campus events...")
        
        #Admins
        cursor.execute("""
            INSERT INTO admins (name, email, role, password_hash) VALUES
            ('Dr. Parthiban K (Faculty Coordinator)', 'admin@college.edu', 'Faculty Coordinator', %s),
            ('Aravind Swamy (Student Council Lead)', 'organizer@college.edu', 'Club Lead', %s)
        """, (generate_password_hash('admin123'), generate_password_hash('organizer123')))
        
        #Students
        cursor.execute("""
            INSERT INTO students (name, email, roll_number, department, year_of_study, phone, password_hash) VALUES
            ('Alex Johnson', 'alex@student.edu', '23CS101', 'Computer Science & Engineering', '3rd Year', '+91 98765 43210', %s)
        """)
        
        #Venues
        cursor.execute("""
            INSERT INTO venues (name, building, capacity, location_details) VALUES
            ('Sir Visvesvaraya Grand Auditorium', 'Main Academic Block', 500, 'Ground Floor, Central Wing'),
            ('Turing Advanced Computing Lab', 'CS Department Complex', 120, '3rd Floor, Tech Park Wing B'),
            ('Ramanujan Open Air Amphitheatre', 'Cultural Complex', 800, 'Adjacent to Student Center'),
            ('APJ Abdul Kalam Seminar Hall', 'PG Block', 200, '2nd Floor, Room 204')
        """)
        
        #Events
        today = date.today()
        cursor.execute("""
            INSERT INTO events (title, category, description, venue_id, event_date, start_time, end_time, capacity, fee, banner_image, upi_id, status, created_by) VALUES
            ('HackFest 2026: 24-Hour AI & Web3 Hackathon', 'Hackathon',
             'The annual flagship campus hackathon! Build disruptive products in AI agents, web applications, IoT, and Web3. Mentorship from industry leads, food, swag kits, and Rs. 50,000 cash prizes included.',
             2, %s, '09:00:00', '21:00:00', 80, 0.00, 'hackathon_2026.jpg', 'organizer@upi', 'upcoming', 1),
             
            ('Euphoria 2026: Inter-College Cultural Fest', 'Cultural',
             'A vibrant 2-day extravaganza featuring street dancing, acoustic jams, drama, fashion walks, and live concert night. Free entry with college student pass.',
             3, %s, '16:00:00', '22:00:00', 500, 0.00, 'euphoria_fest.jpg', 'organizer@upi', 'upcoming', 1),
             
            ('Generative AI & LLM Engineering Masterclass', 'Workshop',
             'Hands-on workshop covering Prompt Engineering, RAG architectures, local LLM deployment, and fine-tuning with Python. Certificate provided upon completion.',
             2, %s, '10:00:00', '16:00:00', 60, 150.00, 'ai_summit.jpg', 'organizer@okhdfcbank', 'upcoming', 1),
             
            ('RoboWars: Arena Combat Championship', 'Robotics',
             'Custom RC battlebots fight inside the high-impact poly-carbonate arena. Weight categories: 15kg and 30kg. Witness thrilling mechanical clashes!',
             1, %s, '11:00:00', '18:00:00', 150, 100.00, 'robowars.jpg', 'robotics@paytm', 'upcoming', 2),
             
            ('Campus Esports Championship: Valorant & BGMI', 'Gaming',
             'High-stakes 5v5 Valorant and 4-man Squad BGMI tournament with live caster stage, dynamic leaderboard, and gaming peripherals for champions.',
             4, %s, '13:00:00', '19:00:00', 100, 200.00, 'esports_cup.jpg', 'esports@oksbi', 'upcoming', 2)
        """, (
            today + timedelta(days=5),
            today + timedelta(days=12),
            today + timedelta(days=8),
            today + timedelta(days=15),
            today + timedelta(days=20)
        ))
        
        Announcements
        cursor.execute("""
            INSERT INTO notifications (title, message, target_audience) VALUES
            ('📌 Welcome to Campus Event Planner', 'The official student portal for all academic, technical, cultural, and sports events is now live. Reserve your passes today!', 'all'),
            ('🚀 HackFest 2026 Team Registrations Open', 'Teams of up to 4 members can register. Bring your laptops, chargers, and college IDs for gate check-in.', 'all')
        """)
        
        print("Demo seed data created successfully!")

if __name__ == '__main__':
    init_db()
