import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'rgcet-campus-notebook-desk-secret-key-2026'
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'localhost'
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'root'
    MYSQL_PASSWORD = os.environ.get("pASS") or os.environ.get("MYSQL_PASSWORD") or 'parthiban'
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'college_event_planner'
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT') or 3306)
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    
    BANNERS_FOLDER = os.path.join(UPLOAD_FOLDER, 'banners')
    PAYMENT_QRS_FOLDER = os.path.join(UPLOAD_FOLDER, 'payment_qrs')
    RECEIPTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'receipts')
    TICKETS_FOLDER = os.path.join(UPLOAD_FOLDER, 'tickets')
    
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
