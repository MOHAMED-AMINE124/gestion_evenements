from flask import Flask, render_template, session, redirect, url_for, request, flash
from flask_mysqldb import MySQL
from flask_login import LoginManager, UserMixin
from flask_mail import Mail
from config import Config
import os
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)

# ============================================
# إنشاء مجلد uploads إذا لم يكن موجوداً
# ============================================
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
    print(f"✅ Created upload folder: {app.config['UPLOAD_FOLDER']}")

mysql = MySQL(app)
mail = Mail(app)

login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

class User(UserMixin):
    def __init__(self, id, full_name, email, role):
        self.id = id
        self.full_name = full_name
        self.email = email
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    if user:
        return User(user['id'], user['full_name'], user['email'], user['role'])
    return None

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    cur = mysql.connection.cursor()
    
    # عدد الفعاليات النشطة
    cur.execute("SELECT COUNT(*) as count FROM events WHERE status = 'active'")
    events_count = cur.fetchone()['count']

    # عدد التذاكر المحجوزة للمستخدم
    cur.execute("SELECT COUNT(*) as count FROM tickets WHERE user_id = %s AND payment_status = 'paid'",
                (session['user_id'],))
    tickets_count = cur.fetchone()['count']
    
    # عدد المستخدمين (للإداري)
    cur.execute("SELECT COUNT(*) as count FROM users")
    users_count = cur.fetchone()['count']
    
    # إجمالي الإيرادات
    cur.execute("SELECT SUM(payment_amount) as total FROM tickets WHERE payment_status = 'paid'")
    revenue = cur.fetchone()['total'] or 0

    # عدد الإشعارات غير المقروءة
    cur.execute("SELECT COUNT(*) as count FROM notifications WHERE user_id = %s AND is_read = 0",
                (session['user_id'],))
    notif_count = cur.fetchone()['count']
    session['notif_count'] = notif_count
    
    # آخر 4 فعاليات
    cur.execute("""
        SELECT * FROM events 
        WHERE status = 'active' 
        ORDER BY created_at DESC 
        LIMIT 4
    """)
    recent_events = cur.fetchall()
    
    # ============================================
    # Activité récente
    # ============================================
    recent_activity = []
    
    # جلب آخر التذاكر المحجوزة
    cur.execute("""
        SELECT t.*, u.full_name, e.title 
        FROM tickets t
        JOIN users u ON t.user_id = u.id
        JOIN events e ON t.event_id = e.id
        WHERE t.payment_status = 'paid'
        ORDER BY t.booked_at DESC
        LIMIT 3
    """)
    tickets_activity = cur.fetchall()
    for ticket in tickets_activity:
        recent_activity.append({
            'icon': '🎫',
            'message': f"{ticket['full_name']} a réservé un ticket pour '{ticket['title']}'",
            'time': ticket['booked_at'].strftime('%d/%m/%Y à %H:%M'),
            'link': url_for('tickets.my_tickets')
        })
    
    # جلب آخر الفعاليات المنشأة
    cur.execute("""
        SELECT e.*, u.full_name 
        FROM events e
        JOIN users u ON e.created_by = u.id
        ORDER BY e.created_at DESC
        LIMIT 3
    """)
    events_activity = cur.fetchall()
    for event in events_activity:
        recent_activity.append({
            'icon': '📅',
            'message': f"{event['full_name']} a créé l'événement '{event['title']}'",
            'time': event['created_at'].strftime('%d/%m/%Y à %H:%M'),
            'link': url_for('events.event_detail', event_id=event['id'])
        })
    
    # جلب آخر التقييمات
    try:
        cur.execute("""
            SELECT r.*, u.full_name, e.title 
            FROM reviews r
            JOIN users u ON r.user_id = u.id
            JOIN events e ON r.event_id = e.id
            ORDER BY r.created_at DESC
            LIMIT 3
        """)
        reviews_activity = cur.fetchall()
        for review in reviews_activity:
            recent_activity.append({
                'icon': '⭐',
                'message': f"{review['full_name']} a évalué '{review['title']}' avec {review['rating']} étoiles",
                'time': review['created_at'].strftime('%d/%m/%Y à %H:%M'),
                'link': url_for('events.event_detail', event_id=review['event_id'])
            })
    except:
        pass
    
    cur.close()

    # الوقت الحالي
    now = datetime.now()

    return render_template('home.html', 
                         events_count=events_count,
                         tickets_count=tickets_count,
                         users_count=users_count,
                         revenue=revenue,
                         recent_events=recent_events,
                         recent_activity=recent_activity[:5],
                         now=now)


@app.route('/about')
def about():
    return render_template('about.html')


# ============================================
# 🆕 ROUTE CONTACT
# ============================================
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        
        if not name or not email or not subject or not message:
            flash('Veuillez remplir tous les champs!', 'danger')
            return redirect(url_for('contact'))
        
        try:
            from flask_mail import Message
            from app import mail, app
            
            # إرسال إيميل إلى الإدارة
            msg = Message(
                subject=f'📩 Contact - {subject}',
                recipients=['mohamedelhamraoui913@gmail.com'],  # 🔴 غيرها لإيميلك
                sender=app.config['MAIL_DEFAULT_SENDER']
            )
            msg.html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f5f5f5; border: 2px solid #d4af37; border-radius: 10px;">
                <h2 style="color: #d4af37;">📩 Nouveau message de contact</h2>
                <div style="background: white; padding: 20px; border-radius: 10px; margin: 10px 0;">
                    <p><strong>👤 Nom:</strong> {name}</p>
                    <p><strong>📧 Email:</strong> {email}</p>
                    <p><strong>📝 Sujet:</strong> {subject}</p>
                    <p><strong>💬 Message:</strong></p>
                    <p style="background: #fafafa; padding: 15px; border-radius: 8px; border-left: 3px solid #d4af37;">{message}</p>
                </div>
                <p style="color: #666; font-size: 0.8rem; text-align: center;">Envoyé depuis École Events</p>
            </div>
            """
            mail.send(msg)
            
            # إرسال إيميل تأكيد للمستخدم
            msg_user = Message(
                subject='📧 Votre message a été reçu - École Events',
                recipients=[email],
                sender=app.config['MAIL_DEFAULT_SENDER']
            )
            msg_user.html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #0a0a0a; color: white; border: 2px solid #d4af37; border-radius: 10px;">
                <div style="text-align: center; padding: 20px 0;">
                    <h1 style="color: #d4af37;">🎫 École Events</h1>
                    <h2 style="color: white;">✅ Message reçu</h2>
                </div>
                <div style="background: #161616; padding: 20px; border-radius: 10px; margin: 10px 0;">
                    <p>Bonjour <strong>{name}</strong>,</p>
                    <p>Nous avons bien reçu votre message. Nous vous répondrons dans les plus brefs délais.</p>
                    <p style="color: rgba(255,255,255,0.4); font-size: 0.9rem; padding: 10px; background: rgba(255,255,255,0.05); border-radius: 8px;">
                        <strong>📝 Sujet:</strong> {subject}
                    </p>
                </div>
                <div style="text-align: center; color: rgba(255,255,255,0.3); font-size: 0.8rem; padding-top: 20px; border-top: 1px solid rgba(212,175,55,0.2);">
                    École Events • Tous droits réservés
                </div>
            </div>
            """
            mail.send(msg_user)
            
            flash('✅ Votre message a été envoyé avec succès! Vous recevrez une confirmation par email.', 'success')
        except Exception as e:
            flash(f'❌ Erreur lors de l\'envoi: {str(e)}', 'danger')
            print(f"❌ Erreur d'envoi d'email: {str(e)}")
        
        return redirect(url_for('contact'))
    
    return render_template('contact.html')


# ============================================
# 🆕 Gestion des erreurs (404 et 500)
# ============================================
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


from routes.auth import auth
from routes.events import events
from routes.tickets import tickets
from routes.notifications import notifications
from routes.admin import admin
from routes.profile import profile
from routes.reviews import reviews

app.register_blueprint(auth)
app.register_blueprint(events)
app.register_blueprint(tickets)
app.register_blueprint(notifications)
app.register_blueprint(admin)
app.register_blueprint(profile)
app.register_blueprint(reviews)

if __name__ == '__main__':
    app.run(debug=True)