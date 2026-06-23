import os

class Config:
    SECRET_KEY = 'school-events-secret-2024'

    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = '0615125078'
    MYSQL_DB = 'school_events'
    MYSQL_CURSORCLASS = 'DictCursor'

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = 'mohamedelhamraoui913@gmail.com'
    MAIL_PASSWORD = 'oyns fvvx hejn ysse'  # 🔴 كود التطبيق الجديد
    MAIL_DEFAULT_SENDER = 'mohamedelhamraoui913@gmail.com'
    MAIL_DEBUG = True