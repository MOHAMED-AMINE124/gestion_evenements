from flask import Blueprint, render_template, request, redirect, url_for, flash, session

admin = Blueprint('admin', __name__)

# ============================================
# ديكور بسيط للتحقق من الدخول
# ============================================

def admin_login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter!', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@admin.route('/admin')
@admin_login_required
def dashboard():
    """لوحة تحكم الإداري"""
    from app import mysql
    from routes.permissions import has_permission
    
    # التحقق من الصلاحية
    if not session.get('is_super_admin') and not has_permission(session['user_id'], 'users.view'):
        flash('Accès refusé! Vous n\'avez pas la permission nécessaire.', 'danger')
        return redirect(url_for('home'))
    
    cur = mysql.connection.cursor()
    
    # إحصائيات عامة
    cur.execute("SELECT COUNT(*) as count FROM users")
    users_count = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) as count FROM events WHERE status = 'active'")
    events_count = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) as count FROM tickets WHERE payment_status = 'paid'")
    tickets_count = cur.fetchone()['count']
    
    cur.execute("SELECT SUM(payment_amount) as total FROM tickets WHERE payment_status = 'paid'")
    revenue = cur.fetchone()['total'] or 0
    
    # آخر الفعاليات
    cur.execute("""
        SELECT e.*, u.full_name as creator_name,
        (SELECT COUNT(*) FROM tickets t WHERE t.event_id = e.id) as tickets_sold
        FROM events e
        JOIN users u ON e.created_by = u.id
        ORDER BY e.created_at DESC
        LIMIT 10
    """)
    events = cur.fetchall()
    
    cur.close()
    
    return render_template('admin/dashboard.html',
        users_count=users_count,
        events_count=events_count,
        tickets_count=tickets_count,
        revenue=revenue,
        events=events
    )


@admin.route('/admin/event/<int:event_id>/cancel', methods=['POST'])
@admin_login_required
def cancel_event(event_id):
    """إلغاء فعالية"""
    from app import mysql
    from routes.permissions import has_permission
    
    if not session.get('is_super_admin') and not has_permission(session['user_id'], 'events.delete'):
        flash('Accès refusé!', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    cur = mysql.connection.cursor()
    cur.execute("UPDATE events SET status = 'cancelled' WHERE id = %s", (event_id,))
    mysql.connection.commit()
    cur.close()
    flash('Événement annulé!', 'success')
    return redirect(url_for('admin.dashboard'))


@admin.route('/admin/event/<int:event_id>/approve', methods=['POST'])
@admin_login_required
def approve_event(event_id):
    """الموافقة على فعالية"""
    from app import mysql
    from routes.permissions import has_permission
    
    if not session.get('is_super_admin') and not has_permission(session['user_id'], 'events.approve'):
        flash('Accès refusé!', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    cur = mysql.connection.cursor()
    cur.execute("UPDATE events SET status = 'active' WHERE id = %s", (event_id,))
    mysql.connection.commit()
    cur.close()
    flash('Événement approuvé!', 'success')
    return redirect(url_for('admin.dashboard'))


@admin.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@admin_login_required
def delete_user(user_id):
    """حذف مستخدم"""
    from app import mysql
    from routes.permissions import has_permission
    
    if not session.get('is_super_admin') and not has_permission(session['user_id'], 'users.delete'):
        flash('Accès refusé!', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    cur = mysql.connection.cursor()
    
    # لا يمكن حذف Super Admin
    cur.execute("SELECT is_super_admin FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    if user and user['is_super_admin']:
        flash('Impossible de supprimer un Super Admin!', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    mysql.connection.commit()
    cur.close()
    flash('Utilisateur supprimé!', 'success')
    return redirect(url_for('admin.dashboard'))