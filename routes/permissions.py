from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from functools import wraps
from app import get_db

permissions_bp = Blueprint('permissions', __name__, url_prefix='/permissions')

# ============================================
# ديكورات التحقق من الصلاحيات
# ============================================

def permission_required(permission_name):
    """ديكور للتحقق من صلاحية المستخدم"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Veuillez vous connecter!', 'danger')
                return redirect(url_for('auth.login'))
            
            # Super Admin لديه كل الصلاحيات
            if session.get('is_super_admin'):
                return f(*args, **kwargs)
            
            # التحقق من الصلاحية للمستخدمين العاديين
            if not has_permission(session['user_id'], permission_name):
                flash('Accès refusé! Vous n\'avez pas la permission nécessaire.', 'danger')
                return redirect(url_for('home'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def has_permission(user_id, permission_name):
    """التحقق مما إذا كان المستخدم لديه صلاحية معينة"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) as count
        FROM users u
        JOIN roles r ON u.role_id = r.id
        JOIN role_permissions rp ON r.id = rp.role_id
        JOIN permissions p ON rp.permission_id = p.id
        WHERE u.id = ? AND p.name = ?
    """, (user_id, permission_name))
    result = cur.fetchone()
    conn.close()
    return result['count'] > 0


def get_user_permissions(user_id):
    """جلب جميع صلاحيات المستخدم"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.name
        FROM users u
        JOIN roles r ON u.role_id = r.id
        JOIN role_permissions rp ON r.id = rp.role_id
        JOIN permissions p ON rp.permission_id = p.id
        WHERE u.id = ?
    """, (user_id,))
    permissions = [row['name'] for row in cur.fetchall()]
    conn.close()
    return permissions


# ============================================
# واجهات إدارة الأدوار والصلاحيات
# ============================================

@permissions_bp.route('/roles')
@permission_required('users.manage_roles')
def list_roles():
    """عرض قائمة الأدوار"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.*, 
               COUNT(DISTINCT rp.permission_id) as permissions_count,
               COUNT(DISTINCT u.id) as users_count
        FROM roles r
        LEFT JOIN role_permissions rp ON r.id = rp.role_id
        LEFT JOIN users u ON r.id = u.role_id
        GROUP BY r.id
        ORDER BY r.id
    """)
    roles = cur.fetchall()
    conn.close()
    return render_template('permissions/roles.html', roles=roles)


@permissions_bp.route('/roles/<int:role_id>')
@permission_required('users.manage_roles')
def view_role(role_id):
    """عرض صلاحيات دور معين"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM roles WHERE id = ?", (role_id,))
    role = cur.fetchone()
    
    if not role:
        flash('Rôle non trouvé!', 'danger')
        return redirect(url_for('permissions.list_roles'))
    
    cur.execute("""
        SELECT p.*, 
               CASE WHEN rp.role_id IS NOT NULL THEN 1 ELSE 0 END as has_permission
        FROM permissions p
        LEFT JOIN role_permissions rp ON p.id = rp.permission_id AND rp.role_id = ?
        ORDER BY p.name
    """, (role_id,))
    permissions = cur.fetchall()
    
    # تجميع الصلاحيات حسب الفئة
    grouped_permissions = {}
    for perm in permissions:
        category = perm['name'].split('.')[0] if '.' in perm['name'] else 'other'
        if category not in grouped_permissions:
            grouped_permissions[category] = []
        grouped_permissions[category].append(perm)
    
    conn.close()
    return render_template('permissions/view_role.html', 
                         role=role, 
                         grouped_permissions=grouped_permissions)


@permissions_bp.route('/roles/<int:role_id>/toggle', methods=['POST'])
@permission_required('users.manage_roles')
def toggle_permission(role_id):
    """تفعيل/تعطيل صلاحية لدور معين"""
    permission_id = request.form.get('permission_id')
    
    if not permission_id:
        flash('Permission non spécifiée!', 'danger')
        return redirect(url_for('permissions.view_role', role_id=role_id))
    
    conn = get_db()
    cur = conn.cursor()
    
    # التحقق من وجود الصلاحية
    cur.execute("SELECT * FROM role_permissions WHERE role_id = ? AND permission_id = ?", 
                (role_id, permission_id))
    exists = cur.fetchone()
    
    if exists:
        cur.execute("DELETE FROM role_permissions WHERE role_id = ? AND permission_id = ?", 
                    (role_id, permission_id))
        flash('Permission retirée!', 'success')
    else:
        cur.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", 
                    (role_id, permission_id))
        flash('Permission ajoutée!', 'success')
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('permissions.view_role', role_id=role_id))


@permissions_bp.route('/users/manage')
@permission_required('users.manage_roles')
def manage_users():
    """إدارة صلاحيات المستخدمين"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT u.*, r.name as role_name, 
               CASE WHEN u.is_super_admin THEN 'Super Admin' ELSE '' END as admin_label
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id
        ORDER BY u.id
    """)
    users = cur.fetchall()
    
    cur.execute("SELECT * FROM roles ORDER BY id")
    roles = cur.fetchall()
    
    conn.close()
    
    return render_template('permissions/manage_users.html', 
                         users=users, 
                         roles=roles)


@permissions_bp.route('/users/<int:user_id>/role', methods=['POST'])
@permission_required('users.manage_roles')
def assign_role(user_id):
    """تغيير دور المستخدم"""
    role_id = request.form.get('role_id')
    
    if not role_id:
        flash('Veuillez sélectionner un rôle!', 'danger')
        return redirect(url_for('permissions.manage_users'))
    
    conn = get_db()
    cur = conn.cursor()
    
    # لا يمكن تغيير دور Super Admin
    cur.execute("SELECT is_super_admin FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    
    if user and user['is_super_admin']:
        flash('Impossible de modifier un Super Admin!', 'danger')
        return redirect(url_for('permissions.manage_users'))
    
    cur.execute("UPDATE users SET role_id = ? WHERE id = ?", (role_id, user_id))
    conn.commit()
    conn.close()
    
    flash('Rôle mis à jour avec succès!', 'success')
    return redirect(url_for('permissions.manage_users'))


@permissions_bp.route('/users/<int:user_id>/make-admin', methods=['POST'])
@permission_required('users.manage_roles')
def make_admin(user_id):
    """ترقية مستخدم إلى Admin"""
    conn = get_db()
    cur = conn.cursor()
    
    # التحقق من أن المستخدم الحالي هو Super Admin
    if not session.get('is_super_admin'):
        flash('Seul un Super Admin peut créer des Admins!', 'danger')
        return redirect(url_for('permissions.manage_users'))
    
    # لا يمكن تغيير Super Admin
    cur.execute("SELECT is_super_admin FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    
    if user and user['is_super_admin']:
        flash('Cet utilisateur est déjà Super Admin!', 'danger')
        return redirect(url_for('permissions.manage_users'))
    
    # جلب دور Admin
    cur.execute("SELECT id FROM roles WHERE name = 'admin'")
    admin_role = cur.fetchone()
    
    if admin_role:
        cur.execute("UPDATE users SET role_id = ? WHERE id = ?", (admin_role['id'], user_id))
        conn.commit()
        flash('Utilisateur promu Admin avec succès!', 'success')
    else:
        flash('Rôle Admin non trouvé!', 'danger')
    
    conn.close()
    return redirect(url_for('permissions.manage_users'))


@permissions_bp.route('/users/<int:user_id>/remove-admin', methods=['POST'])
@permission_required('users.manage_roles')
def remove_admin(user_id):
    """إزالة صلاحية Admin من مستخدم"""
    conn = get_db()
    cur = conn.cursor()
    
    # لا يمكن تغيير Super Admin
    cur.execute("SELECT is_super_admin FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    
    if user and user['is_super_admin']:
        flash('Impossible de modifier un Super Admin!', 'danger')
        return redirect(url_for('permissions.manage_users'))
    
    # جلب دور User
    cur.execute("SELECT id FROM roles WHERE name = 'user'")
    user_role = cur.fetchone()
    
    if user_role:
        cur.execute("UPDATE users SET role_id = ? WHERE id = ?", (user_role['id'], user_id))
        conn.commit()
        flash('Admin retiré avec succès!', 'success')
    
    conn.close()
    return redirect(url_for('permissions.manage_users'))


@permissions_bp.route('/my-permissions')
def my_permissions():
    """عرض صلاحيات المستخدم الحالي"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    permissions = get_user_permissions(session['user_id'])
    return render_template('permissions/my_permissions.html', permissions=permissions)