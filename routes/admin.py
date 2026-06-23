from flask import Blueprint, render_template, request, redirect, url_for, flash, session

admin = Blueprint('admin', __name__)

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if session.get('user_role') != 'admin':
            flash('Accès refusé!', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated

@admin.route('/admin')
@admin_required
def dashboard():
    from app import mysql
    cur = mysql.connection.cursor()

    cur.execute("SELECT COUNT(*) as count FROM users")
    users_count = cur.fetchone()['count']

    cur.execute("SELECT COUNT(*) as count FROM events WHERE status = 'active'")
    events_count = cur.fetchone()['count']

    cur.execute("SELECT COUNT(*) as count FROM tickets WHERE payment_status = 'paid'")
    tickets_count = cur.fetchone()['count']

    cur.execute("SELECT SUM(payment_amount) as total FROM tickets WHERE payment_status = 'paid'")
    revenue = cur.fetchone()['total'] or 0

    cur.execute("""
        SELECT e.*, u.full_name as creator_name,
        (SELECT COUNT(*) FROM tickets t WHERE t.event_id = e.id) as tickets_sold
        FROM events e
        JOIN users u ON e.created_by = u.id
        ORDER BY e.created_at DESC
    """)
    events = cur.fetchall()

    cur.execute("""
        SELECT u.*, 
        (SELECT COUNT(*) FROM tickets t WHERE t.user_id = u.id) as tickets_count
        FROM users u
        ORDER BY u.created_at DESC
    """)
    users = cur.fetchall()

    cur.close()

    return render_template('admin/dashboard.html',
        users_count=users_count,
        events_count=events_count,
        tickets_count=tickets_count,
        revenue=revenue,
        events=events,
        users=users
    )


@admin.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    from app import mysql
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    mysql.connection.commit()
    cur.close()
    flash('Utilisateur supprimé!', 'success')
    return redirect(url_for('admin.dashboard'))


@admin.route('/admin/event/<int:event_id>/cancel', methods=['POST'])
@admin_required
def cancel_event(event_id):
    from app import mysql
    cur = mysql.connection.cursor()
    cur.execute("UPDATE events SET status = 'cancelled' WHERE id = %s", (event_id,))
    mysql.connection.commit()
    cur.close()
    flash('Événement annulé!', 'success')
    return redirect(url_for('admin.dashboard'))