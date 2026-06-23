from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Message
import re
import random

auth = Blueprint('auth', __name__)

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        role = request.form['role']

        if len(full_name) < 3:
            flash('Le nom doit contenir au moins 3 caractères!', 'danger')
            return redirect(url_for('auth.register'))

        if not is_valid_email(email):
            flash('Adresse email invalide!', 'danger')
            return redirect(url_for('auth.register'))

        if len(password) < 3:
            flash('Le mot de passe doit contenir au moins 3 caractères!', 'danger')
            return redirect(url_for('auth.register'))

        from app import mysql
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cur.fetchone()

        if existing_user:
            flash('Cet email est déjà utilisé!', 'danger')
            cur.close()
            return redirect(url_for('auth.register'))

        code = str(random.randint(100000, 999999))
        hashed_password = generate_password_hash(password)

        cur.execute("""
            INSERT INTO users (full_name, email, password, role, is_verified, verification_code) 
            VALUES (%s, %s, %s, %s, FALSE, %s)
        """, (full_name, email, hashed_password, role, code))
        mysql.connection.commit()
        cur.close()

        try:
            from app import mail
            msg = Message(
                subject='Code de vérification - École Events',
                recipients=[email]
            )
            msg.html = f"<h1>Code: {code}</h1>"
            mail.send(msg)
            flash('Code envoyé à ' + email, 'success')
        except Exception as e:
            flash('Erreur email: ' + str(e), 'danger')

        session['verify_email'] = email
        return redirect(url_for('auth.verify'))

    return render_template('auth/register.html')


@auth.route('/verify', methods=['GET', 'POST'])
def verify():
    email = session.get('verify_email')
    if not email:
        return redirect(url_for('auth.register'))

    if request.method == 'POST':
        code = request.form['code'].strip()

        from app import mysql
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s AND verification_code = %s", (email, code))
        user = cur.fetchone()

        if user:
            cur.execute("UPDATE users SET is_verified = TRUE, verification_code = NULL WHERE email = %s", (email,))
            mysql.connection.commit()
            cur.close()
            session.pop('verify_email', None)
            flash('Compte vérifié! Connectez-vous maintenant.', 'success')
            return redirect(url_for('auth.login'))
        else:
            cur.close()
            flash('Code incorrect!', 'danger')

    return render_template('auth/verify.html', email=email)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']

        if not is_valid_email(email):
            flash('Adresse email invalide!', 'danger')
            return redirect(url_for('auth.login'))

        from app import mysql
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()

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
            session['user_role'] = user['role']
            flash('Bienvenue ' + user['full_name'] + '!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Email ou mot de passe incorrect!', 'danger')

    return render_template('auth/login.html')


@auth.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip()

        from app import mysql
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()

        if user:
            code = str(random.randint(100000, 999999))
            cur.execute("UPDATE users SET verification_code = %s WHERE email = %s", (code, email))
            mysql.connection.commit()

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
                cur.close()
                return redirect(url_for('auth.reset_password'))
            except Exception as e:
                flash('Erreur email: ' + str(e), 'danger')
        else:
            flash('Email introuvable!', 'danger')

        cur.close()

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

        from app import mysql
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s AND verification_code = %s", (email, code))
        user = cur.fetchone()

        if user:
            hashed = generate_password_hash(new_password)
            cur.execute("UPDATE users SET password = %s, verification_code = NULL WHERE email = %s",
                       (hashed, email))
            mysql.connection.commit()
            cur.close()
            session.pop('reset_email', None)
            flash('Mot de passe modifié! Connectez-vous.', 'success')
            return redirect(url_for('auth.login'))
        else:
            cur.close()
            flash('Code incorrect!', 'danger')

    return render_template('auth/reset_password.html', email=email)
@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password_token(token):
    # هذا سيتم إضافته لاحقاً مع نظام JWT
    flash('Cette fonctionnalité sera disponible prochainement!', 'info')
    return redirect(url_for('auth.login'))