from flask import Blueprint, render_template, session, redirect, url_for

notifications = Blueprint('notifications', __name__)

@notifications.route('/notifications')
def list_notifications():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    from app import mysql
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT n.*, e.title as event_title
        FROM notifications n
        LEFT JOIN events e ON n.event_id = e.id
        WHERE n.user_id = %s
        ORDER BY n.created_at DESC
    """, (session['user_id'],))
    notifs = cur.fetchall()

    cur.execute("UPDATE notifications SET is_read = 1 WHERE user_id = %s", (session['user_id'],))
    mysql.connection.commit()
    cur.close()

    return render_template('notifications/list.html', notifications=notifs)


def send_notification(user_id, event_id, message):
    from app import mysql
    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO notifications (user_id, event_id, message)
        VALUES (%s, %s, %s)
    """, (user_id, event_id, message))
    mysql.connection.commit()
    cur.close()


def notify_event_update(event_id, message):
    from app import mysql
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT DISTINCT user_id FROM tickets 
        WHERE event_id = %s AND payment_status != 'cancelled'
    """, (event_id,))
    users = cur.fetchall()
    cur.close()

    for user in users:
        send_notification(user['user_id'], event_id, message)