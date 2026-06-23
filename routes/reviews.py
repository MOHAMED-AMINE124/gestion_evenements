from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime

reviews = Blueprint('reviews', __name__)

@reviews.route('/events/<int:event_id>/review', methods=['POST'])
def add_review(event_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    rating = request.form.get('rating')
    comment = request.form.get('comment', '').strip()
    
    if not rating or not rating.isdigit():
        flash('Veuillez sélectionner une note!', 'danger')
        return redirect(url_for('events.event_detail', event_id=event_id))
    
    rating = int(rating)
    if rating < 1 or rating > 5:
        flash('La note doit être entre 1 et 5!', 'danger')
        return redirect(url_for('events.event_detail', event_id=event_id))
    
    from app import mysql
    cur = mysql.connection.cursor()
    
    # التأكد من أن المستخدم حجز تذكرة في هذه الفعالية
    cur.execute("""
        SELECT id FROM tickets 
        WHERE user_id = %s AND event_id = %s AND payment_status = 'paid'
    """, (session['user_id'], event_id))
    ticket = cur.fetchone()
    
    if not ticket:
        flash('Vous devez avoir réservé un ticket pour cette événement!', 'danger')
        return redirect(url_for('events.event_detail', event_id=event_id))
    
    # التأكد من أن المستخدم لم يقيّم من قبل
    cur.execute("SELECT id FROM reviews WHERE user_id = %s AND event_id = %s", 
                (session['user_id'], event_id))
    existing = cur.fetchone()
    
    if existing:
        # تحديث التقييم الموجود
        cur.execute("""
            UPDATE reviews 
            SET rating = %s, comment = %s 
            WHERE user_id = %s AND event_id = %s
        """, (rating, comment, session['user_id'], event_id))
    else:
        # إضافة تقييم جديد
        cur.execute("""
            INSERT INTO reviews (user_id, event_id, rating, comment)
            VALUES (%s, %s, %s, %s)
        """, (session['user_id'], event_id, rating, comment))
    
    # تحديث متوسط التقييمات في جدول events
    cur.execute("""
        SELECT AVG(rating) as avg_rating, COUNT(*) as total 
        FROM reviews 
        WHERE event_id = %s
    """, (event_id,))
    stats = cur.fetchone()
    
    cur.execute("""
        UPDATE events 
        SET average_rating = %s, total_reviews = %s 
        WHERE id = %s
    """, (stats['avg_rating'] or 0, stats['total'] or 0, event_id))
    
    mysql.connection.commit()
    cur.close()
    
    flash('Merci pour votre évaluation!', 'success')
    return redirect(url_for('events.event_detail', event_id=event_id))


@reviews.route('/events/<int:event_id>/reviews')
def get_reviews(event_id):
    from app import mysql
    cur = mysql.connection.cursor()
    
    cur.execute("""
        SELECT r.*, u.full_name, u.profile_pic
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.event_id = %s
        ORDER BY r.created_at DESC
    """, (event_id,))
    reviews_list = cur.fetchall()
    cur.close()
    
    return render_template('events/reviews.html', reviews=reviews_list)


@reviews.route('/reviews/<int:review_id>/delete', methods=['POST'])
def delete_review(review_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    from app import mysql
    cur = mysql.connection.cursor()
    
    # التأكد من أن المستخدم هو صاحب التقييم أو Admin
    cur.execute("""
        SELECT r.*, e.created_by as event_creator
        FROM reviews r
        JOIN events e ON r.event_id = e.id
        WHERE r.id = %s
    """, (review_id,))
    review = cur.fetchone()
    
    if not review:
        flash('Évaluation non trouvée!', 'danger')
        return redirect(url_for('events.list_events'))
    
    if session['user_id'] != review['user_id'] and session.get('user_role') != 'admin':
        flash('Vous n\'êtes pas autorisé à supprimer cette évaluation!', 'danger')
        return redirect(url_for('events.event_detail', event_id=review['event_id']))
    
    event_id = review['event_id']
    
    # حذف التقييم
    cur.execute("DELETE FROM reviews WHERE id = %s", (review_id,))
    
    # تحديث متوسط التقييمات
    cur.execute("""
        SELECT AVG(rating) as avg_rating, COUNT(*) as total 
        FROM reviews 
        WHERE event_id = %s
    """, (event_id,))
    stats = cur.fetchone()
    
    cur.execute("""
        UPDATE events 
        SET average_rating = %s, total_reviews = %s 
        WHERE id = %s
    """, (stats['avg_rating'] or 0, stats['total'] or 0, event_id))
    
    mysql.connection.commit()
    cur.close()
    
    flash('Évaluation supprimée avec succès!', 'success')
    return redirect(url_for('events.event_detail', event_id=event_id))