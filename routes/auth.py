from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Message
import re
import random
from app import get_db

auth = Blueprint('auth', __name__)

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


@auth.route('/register', methods=['GET', 'POST'])
def register():
    # ✅ التسجيل مفتوح للكل
    if request.method == 'POST':
        full_name = request.form['full_name'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        role_id = request.form.get('role_id')
        
        # التحقق من المدخلات
        if len(full_name) < 3:
            flash('Le nom doit contenir au moins 3 caractères!', 'danger')
            return redirect(url_for('auth.register'))
        
        if not is_valid_email(email):
            flash('Adresse email invalide!', 'danger')
            return redirect(url_for('auth.register'))
        
        if len(password) < 3:
            flash('Le mot de passe doit contenir au moins 3 caractères!', 'danger')
            return redirect(url_for('auth.register'))
        
        conn = get_db()
        cur = conn.cursor()
        
        # التحقق من وجود المستخدم
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        existing_user = cur.fetchone()
        
        if existing_user:
            flash('Cet email est déjà utilisé!', 'danger')
            conn.close()
            return redirect(url_for('auth.register'))
        
        # إنشاء المستخدم
        hashed_password = generate_password_hash(password)
        
        # إذا كان المستخدم الحالي مسجل دخول وهو Super Admin، يمكنه تعيين أي دور
        # وإلا يعطى دور user تلقائياً
        if session.get('is_super_admin') and role_id:
            pass
        elif session.get('user_id'):
            cur.execute("SELECT id FROM roles WHERE name IN ('user', 'moderator', 'manager')")
            allowed_roles = [row['id'] for row in cur.fetchall()]
            if role_id and int(role_id) in allowed_roles:
                pass
            else:
                role_id = None
        else:
            role_id = None
            cur.execute("SELECT id FROM roles WHERE name = 'user'")
            user_role = cur.fetchone()
            if user_role:
                role_id = user_role['id']
        
        # إنشاء كود التحقق
        code = str(random.randint(100000, 999999))
        
        cur.execute("""
            INSERT INTO users (full_name, email, password, role_id, is_verified, verification_code, created_by) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (full_name, email, hashed_password, role_id, 0, code, session.get('user_id') if session.get('user_id') else None))
        
        conn.commit()
        conn.close()
        
        # إرسال كود التحقق
        try:
            from app import mail
            msg = Message(
                subject='Code de vérification - École Events',
                recipients=[email]
            )
            msg.html = f"""
            <h1>🎫 École Events</h1>
            <h2>Votre code de vérification</h2>
            <p style="font-size: 2rem; font-weight: bold; color: #d4af37;">{code}</p>
            <p>Ce code expire dans 10 minutes.</p>
            """
            mail.send(msg)
            flash('Code envoyé à ' + email, 'success')
        except Exception as e:
            flash('Erreur email: ' + str(e), 'danger')
        
        session['verify_email'] = email
        return redirect(url_for('auth.verify'))
    
    # جلب الأدوار المتاحة
    conn = get_db()
    cur = conn.cursor()
    
    if session.get('is_super_admin'):
        cur.execute("SELECT * FROM roles ORDER BY id")
    elif session.get('user_id'):
        cur.execute("SELECT * FROM roles WHERE name IN ('user', 'moderator', 'manager') ORDER BY id")
    else:
        cur.execute("SELECT * FROM roles WHERE name = 'user'")
    
    roles = cur.fetchall()
    conn.close()
    
    return render_template('auth/register.html', roles=roles)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']
        
        if not is_valid_email(email):
            flash('Adresse email invalide!', 'danger')
            return redirect(url_for('auth.login'))
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.*, r.name as role_name
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            WHERE u.email = ?
        """, (email,))
        user = cur.fetchone()
        conn.close()
        
        if not user:
            flash('Email ou mot de passe incorrect!', 'danger')
            return redirect(url_for('auth.login'))
        
        if not user['is_verified']:
            session['verify_email'] = email
            flash('Veuillez vérifier votre email!', 'danger')
            return redirect(url_for('auth.verify'))
        
        if check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['user_role'] = user['role_name'] or 'user'
            session['is_super_admin'] = bool(user['is_super_admin'])
            session['role_id'] = user['role_id']
            
            # جلب الصلاحيات
            try:
                from routes.permissions import get_user_permissions
                session['permissions'] = get_user_permissions(user['id'])
            except:
                session['permissions'] = []
            
            flash('Bienvenue ' + user['full_name'] + '!', 'success')
            
            # توجيه حسب الدور
            if user['is_super_admin']:
                return redirect(url_for('admin.dashboard'))
            elif user['role_name'] in ['admin', 'manager']:
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('home'))
        else:
            flash('Email ou mot de passe incorrect!', 'danger')
    
    return render_template('auth/login.html')


@auth.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


# ============================================
# دوال forgot_password, reset_password, verify
# ============================================

@auth.route('/verify', methods=['GET', 'POST'])
def verify():
    email = session.get('verify_email')
    if not email:
        return redirect(url_for('auth.register'))
    
    if request.method == 'POST':
        code = request.form['code'].strip()
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ? AND verification_code = ?", (email, code))
        user = cur.fetchone()
        
        if user:
            cur.execute("UPDATE users SET is_verified = 1, verification_code = NULL WHERE email = ?", (email,))
            conn.commit()
            conn.close()
            session.pop('verify_email', None)
            flash('Compte vérifié! Connectez-vous maintenant.', 'success')
            return redirect(url_for('auth.login'))
        else:
            conn.close()
            flash('Code incorrect!', 'danger')
    
    return render_template('auth/verify.html', email=email)


@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip()
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cur.fetchone()
        
        if user:
            code = str(random.randint(100000, 999999))
            cur.execute("UPDATE users SET verification_code = ? WHERE email = ?", (code, email))
            conn.commit()
            
            try:
                from app import mail
                msg = Message(
                    subject='Réinitialisation - École Events',
                    recipients=[email]
                )
                msg.html = f"<h1>Code: {code}</h1>"
                mail.send(msg)
                flash('Code envoyé à ' + email, 'success')
                session['reset_email'] = email
                conn.close()
                return redirect(url_for('auth.reset_password'))
            except Exception as e:
                flash('Erreur email: ' + str(e), 'danger')
        else:
            flash('Email introuvable!', 'danger')
        
        conn.close()
    
    return render_template('auth/forgot_password.html')


@auth.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = session.get('reset_email')
    if not email:
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        code = request.form['code'].strip()
        new_password = request.form['new_password']
        
        if len(new_password) < 3:
            flash('Le mot de passe doit contenir au moins 3 caractères!', 'danger')
            return redirect(url_for('auth.reset_password'))
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ? AND verification_code = ?", (email, code))
        user = cur.fetchone()
        
        if user:
            hashed = generate_password_hash(new_password)
            cur.execute("UPDATE users SET password = ?, verification_code = NULL WHERE email = ?",
                       (hashed, email))
            conn.commit()
            conn.close()
            session.pop('reset_email', None)
            flash('Mot de passe modifié! Connectez-vous.', 'success')
            return redirect(url_for('auth.login'))
        else:
            conn.close()
            flash('Code incorrect!', 'danger')
    
    return render_template('auth/reset_password.html', email=email)