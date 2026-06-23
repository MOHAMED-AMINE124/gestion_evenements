from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
import os
from datetime import datetime

events = Blueprint('events', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@events.route('/events')
def list_events():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    search = request.args.get('search', '')
    filter_status = request.args.get('status', 'active')
    
    from app import mysql
    cur = mysql.connection.cursor()
    
    query = """
        SELECT e.*, u.full_name as creator_name 
        FROM events e 
        JOIN users u ON e.created_by = u.id 
        WHERE 1=1
    """
    params = []
    
    if search:
        query += " AND (e.title LIKE %s OR e.description LIKE %s)"
        search_param = f"%{search}%"
        params.extend([search_param, search_param])
    
    if filter_status:
        query += " AND e.status = %s"
        params.append(filter_status)
    
    query += " ORDER BY e.event_date ASC"
    
    cur.execute(query, params)
    events_list = cur.fetchall()
    cur.close()
    
    now = datetime.now()
    
    return render_template('events/list.html', 
                         events=events_list, 
                         search=search,
                         filter_status=filter_status,
                         now=now)


@events.route('/events/create', methods=['GET', 'POST'])
def create_event():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        event_date = request.form.get('event_date', '')
        location = request.form.get('location', '').strip()
        total_seats = request.form.get('total_seats', 0)
        price = request.form.get('price', 0)

        if not title or len(title) < 3:
            flash('Le titre doit contenir au moins 3 caractères!', 'danger')
            return redirect(url_for('events.create_event'))

        if not event_date:
            flash('Veuillez sélectionner une date!', 'danger')
            return redirect(url_for('events.create_event'))

        try:
            total_seats = int(total_seats)
            if total_seats < 1:
                flash('Le nombre de places doit être au moins 1!', 'danger')
                return redirect(url_for('events.create_event'))
        except:
            flash('Nombre de places invalide!', 'danger')
            return redirect(url_for('events.create_event'))

        try:
            price = float(price)
            if price < 0:
                price = 0
        except:
            price = 0
        
        image_filename = 'default_event.jpg'
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                from app import app
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(upload_path)
                image_filename = filename
        
        from app import mysql
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO events (title, description, event_date, location, total_seats, available_seats, price, image, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (title, description, event_date, location, total_seats, total_seats, price, image_filename, session['user_id']))
        
        event_id = cur.lastrowid
        
        for i in range(1, int(total_seats) + 1):
            cur.execute("INSERT INTO seats (event_id, seat_number, status) VALUES (%s, %s, 'available')",
                       (event_id, i))
        
        mysql.connection.commit()
        cur.close()
        
        flash('Événement créé avec succès!', 'success')
        return redirect(url_for('events.list_events'))
    
    return render_template('events/create.html')


@events.route('/events/<int:event_id>')
def event_detail(event_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    from app import mysql
    cur = mysql.connection.cursor()
    
    cur.execute("""
        SELECT e.*, u.full_name as creator_name 
        FROM events e 
        JOIN users u ON e.created_by = u.id 
        WHERE e.id = %s
    """, (event_id,))
    event = cur.fetchone()
    
    if not event:
        flash('Événement non trouvé!', 'danger')
        return redirect(url_for('events.list_events'))
    
    cur.execute("SELECT * FROM seats WHERE event_id = %s ORDER BY seat_number", (event_id,))
    seats = cur.fetchall()
    
    # جلب التقييمات
    try:
        cur.execute("""
            SELECT r.*, u.full_name
            FROM reviews r
            JOIN users u ON r.user_id = u.id
            WHERE r.event_id = %s
            ORDER BY r.created_at DESC
        """, (event_id,))
        reviews = cur.fetchall()
    except:
        reviews = []
    
    cur.close()
    
    now = datetime.now()
    
    return render_template('events/detail.html', 
                         event=event, 
                         seats=seats, 
                         reviews=reviews,
                         now=now)


@events.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
def edit_event(event_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    from app import mysql
    cur = mysql.connection.cursor()
    
    cur.execute("SELECT * FROM events WHERE id = %s", (event_id,))
    event = cur.fetchone()
    
    if not event:
        flash('Événement non trouvé!', 'danger')
        return redirect(url_for('events.list_events'))
    
    if session['user_id'] != event['created_by'] and session.get('user_role') != 'admin':
        flash('Vous n\'êtes pas autorisé à modifier cet événement!', 'danger')
        return redirect(url_for('events.event_detail', event_id=event_id))
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        event_date = request.form.get('event_date', '')
        location = request.form.get('location', '').strip()
        price = request.form.get('price', 0)

        if not title or len(title) < 3:
            flash('Le titre doit contenir au moins 3 caractères!', 'danger')
            return redirect(url_for('events.edit_event', event_id=event_id))

        if not event_date:
            flash('Veuillez sélectionner une date!', 'danger')
            return redirect(url_for('events.edit_event', event_id=event_id))

        try:
            price = float(price)
            if price < 0:
                price = 0
        except:
            price = 0
        
        image_filename = event['image']
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                from app import app
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(upload_path)
                image_filename = filename
        
        cur.execute("""
            UPDATE events 
            SET title=%s, description=%s, event_date=%s, location=%s, price=%s, image=%s
            WHERE id=%s
        """, (title, description, event_date, location, price, image_filename, event_id))
        
        mysql.connection.commit()
        cur.close()
        
        from routes.notifications import notify_event_update
        notify_event_update(event_id, f"L'événement '{title}' a été modifié!")
        
        flash('Événement modifié avec succès!', 'success')
        return redirect(url_for('events.event_detail', event_id=event_id))
    
    cur.close()
    return render_template('events/edit.html', event=event)


@events.route('/events/<int:event_id>/delete', methods=['POST'])
def delete_event(event_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    from app import mysql
    cur = mysql.connection.cursor()
    
    cur.execute("SELECT created_by FROM events WHERE id = %s", (event_id,))
    event = cur.fetchone()
    
    if not event:
        flash('Événement non trouvé!', 'danger')
        return redirect(url_for('events.list_events'))
    
    if session['user_id'] != event['created_by'] and session.get('user_role') != 'admin':
        flash('Vous n\'êtes pas autorisé à supprimer cet événement!', 'danger')
        return redirect(url_for('events.event_detail', event_id=event_id))
    
    try:
        # حذف التذاكر المرتبطة
        cur.execute("DELETE FROM tickets WHERE event_id = %s", (event_id,))
        
        # حذف المقاعد المرتبطة
        cur.execute("DELETE FROM seats WHERE event_id = %s", (event_id,))
        
        # حذف الإشعارات المرتبطة
        cur.execute("DELETE FROM notifications WHERE event_id = %s", (event_id,))
        
        # حذف التقييمات المرتبطة (إذا كان الجدول موجود)
        try:
            cur.execute("DELETE FROM reviews WHERE event_id = %s", (event_id,))
        except:
            pass
        
        # حذف الفعالية
        cur.execute("DELETE FROM events WHERE id = %s", (event_id,))
        
        mysql.connection.commit()
        flash('Événement supprimé avec succès!', 'success')
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Erreur lors de la suppression: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('events.list_events'))