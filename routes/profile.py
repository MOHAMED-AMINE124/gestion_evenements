from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

profile = Blueprint('profile', __name__)

@profile.route('/profile')
def my_profile():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    from app import mysql
    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()

    if not user:
        flash('Utilisateur non trouvé!', 'danger')
        return redirect(url_for('auth.login'))

    cur.execute("""
        SELECT COUNT(*) as count FROM tickets 
        WHERE user_id = %s AND payment_status = 'paid'
    """, (session['user_id'],))
    tickets_count = cur.fetchone()['count']

    cur.execute("""
        SELECT COUNT(*) as count FROM events 
        WHERE created_by = %s AND status = 'active'
    """, (session['user_id'],))
    events_count = cur.fetchone()['count']
    
    cur.execute("""
        SELECT t.*, e.title, e.event_date, e.location
        FROM tickets t
        JOIN events e ON t.event_id = e.id
        WHERE t.user_id = %s AND t.payment_status = 'paid'
        ORDER BY t.booked_at DESC
        LIMIT 5
    """, (session['user_id'],))
    recent_tickets = cur.fetchall()

    cur.close()

    return render_template('profile/profile.html',
                         user=user,
                         tickets_count=tickets_count,
                         events_count=events_count,
                         recent_tickets=recent_tickets)


@profile.route('/profile/edit', methods=['POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()

    if not full_name or len(full_name) < 3:
        flash('Le nom doit contenir au moins 3 caractères!', 'danger')
        return redirect(url_for('profile.my_profile'))

    if not email or '@' not in email:
        flash('Email invalide!', 'danger')
        return redirect(url_for('profile.my_profile'))

    from app import mysql, app
    cur = mysql.connection.cursor()

    cur.execute("SELECT id FROM users WHERE email = %s AND id != %s",
                (email, session['user_id']))
    existing = cur.fetchone()

    if existing:
        flash('Cet email est déjà utilisé!', 'danger')
        return redirect(url_for('profile.my_profile'))

    # ✅ معالجة الصورة
    profile_pic = None
    if 'profile_pic' in request.files:
        file = request.files['profile_pic']
        if file and file.filename != '':
            # التأكد من أن الملف صورة
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
            if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                filename = secure_filename(file.filename)
                # إضافة timestamp لتجنب تكرار الأسماء
                import time
                filename = str(int(time.time())) + '_' + filename
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(upload_path)
                profile_pic = filename
                print(f"✅ Image sauvegardée: {upload_path}")  # للتحقق
            else:
                flash('Format d\'image non supporté! (PNG, JPG, JPEG, GIF, WEBP)', 'danger')
                return redirect(url_for('profile.my_profile'))

    if profile_pic:
        cur.execute("""
            UPDATE users SET full_name=%s, email=%s, profile_pic=%s WHERE id=%s
        """, (full_name, email, profile_pic, session['user_id']))
    else:
        cur.execute("""
            UPDATE users SET full_name=%s, email=%s WHERE id=%s
        """, (full_name, email, session['user_id']))

    mysql.connection.commit()
    session['user_name'] = full_name
    cur.close()

    flash('Profil mis à jour avec succès!', 'success')
    return redirect(url_for('profile.my_profile'))


@profile.route('/profile/password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    old_password = request.form.get('old_password', '')
    new_password = request.form.get('new_password', '')

    if not old_password or not new_password:
        flash('Veuillez remplir tous les champs!', 'danger')
        return redirect(url_for('profile.my_profile'))

    if len(new_password) < 3:
        flash('Le nouveau mot de passe doit contenir au moins 3 caractères!', 'danger')
        return redirect(url_for('profile.my_profile'))

    from app import mysql
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()

    if not user:
        flash('Utilisateur non trouvé!', 'danger')
        return redirect(url_for('profile.my_profile'))

    if not check_password_hash(user['password'], old_password):
        flash('Ancien mot de passe incorrect!', 'danger')
        return redirect(url_for('profile.my_profile'))

    hashed = generate_password_hash(new_password)
    cur.execute("UPDATE users SET password=%s WHERE id=%s",
                (hashed, session['user_id']))
    mysql.connection.commit()
    cur.close()

    flash('Mot de passe modifié avec succès!', 'success')
    return redirect(url_for('profile.my_profile'))


# ============================================
# 🆕 ROUTE DASHBOARD
# ============================================
@profile.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    from app import mysql
    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT COUNT(*) as count FROM tickets 
        WHERE user_id = %s AND payment_status = 'paid'
    """, (session['user_id'],))
    tickets_count = cur.fetchone()['count']

    cur.execute("""
        SELECT COUNT(*) as count FROM events 
        WHERE created_by = %s AND status = 'active'
    """, (session['user_id'],))
    events_count = cur.fetchone()['count']

    try:
        cur.execute("""
            SELECT COUNT(*) as count FROM reviews 
            WHERE user_id = %s
        """, (session['user_id'],))
        reviews_count = cur.fetchone()['count']
    except:
        reviews_count = 0

    cur.execute("""
        SELECT SUM(payment_amount) as total FROM tickets 
        WHERE user_id = %s AND payment_status = 'paid'
    """, (session['user_id'],))
    total_spent = cur.fetchone()['total'] or 0

    cur.execute("""
        SELECT t.*, e.title, e.event_date
        FROM tickets t
        JOIN events e ON t.event_id = e.id
        WHERE t.user_id = %s AND t.payment_status = 'paid'
        ORDER BY t.booked_at DESC
        LIMIT 5
    """, (session['user_id'],))
    recent_tickets = cur.fetchall()

    cur.close()

    return render_template('user/dashboard.html',
                         tickets_count=tickets_count,
                         events_count=events_count,
                         reviews_count=reviews_count,
                         total_spent=total_spent,
                         recent_tickets=recent_tickets)