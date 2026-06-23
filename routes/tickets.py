from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import qrcode
import uuid
import os
from datetime import datetime

tickets = Blueprint('tickets', __name__)

@tickets.route('/events/<int:event_id>/reserve', methods=['POST'])
def reserve(event_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    seat_number = request.form.get('seat_number')

    if not seat_number:
        flash('Veuillez sélectionner une place!', 'danger')
        return redirect(url_for('events.event_detail', event_id=event_id))

    from app import mysql
    cur = mysql.connection.cursor()

    # التحقق من توفر المقعد
    cur.execute("SELECT * FROM seats WHERE event_id = %s AND seat_number = %s AND status = 'available'",
                (event_id, seat_number))
    seat = cur.fetchone()

    if not seat:
        flash('Cette place est déjà réservée!', 'danger')
        return redirect(url_for('events.event_detail', event_id=event_id))
    
    # التحقق من وجود الفعالية
    cur.execute("SELECT event_date, price, title FROM events WHERE id = %s", (event_id,))
    event = cur.fetchone()
    
    if not event:
        flash('Événement non trouvé!', 'danger')
        return redirect(url_for('events.list_events'))
    
    # التحقق من أن الفعالية لم تبدأ
    if event['event_date'] < datetime.now():
        flash('Impossible de réserver pour un événement passé!', 'danger')
        return redirect(url_for('events.event_detail', event_id=event_id))
 
    # إنشاء QR Code
    qr_code = str(uuid.uuid4())

    from app import app
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # التأكد من وجود مجلد uploads
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    qr_path = os.path.join(app.config['UPLOAD_FOLDER'], f'qr_{qr_code}.png')
    qr_img.save(qr_path)

    # تحديث حالة المقعد
    cur.execute("UPDATE seats SET status = 'reserved', user_id = %s WHERE event_id = %s AND seat_number = %s",
                (session['user_id'], event_id, seat_number))

    # إنشاء التذكرة (حالة الدفع pending)
    cur.execute("""
        INSERT INTO tickets (user_id, event_id, seat_number, qr_code, payment_status, payment_amount)
        VALUES (%s, %s, %s, %s, 'pending', %s)
    """, (session['user_id'], event_id, seat_number, qr_code, event['price']))
    
    # تحديث عدد المقاعد المتاحة
    cur.execute("UPDATE events SET available_seats = available_seats - 1 WHERE id = %s", (event_id,))

    mysql.connection.commit()
    cur.close()

    # ============================================
    # 🔴 إرسال إشعار بالبريد الإلكتروني
    # ============================================
    try:
        from flask_mail import Message
        from app import mail
        
        user_email = session.get('user_email')
        user_name = session.get('user_name')
        
        if user_email:
            msg = Message(
                subject='✅ Confirmation de réservation - École Events',
                recipients=[user_email]
            )
            msg.html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #0a0a0a; color: white; border: 2px solid #d4af37; border-radius: 10px;">
                <div style="text-align: center; padding: 20px 0;">
                    <h1 style="color: #d4af37;">🎫 École Events</h1>
                    <h2 style="color: white;">Confirmation de réservation</h2>
                </div>
                <div style="background: #161616; padding: 20px; border-radius: 10px; margin: 10px 0;">
                    <p><strong>👤 Client:</strong> {user_name}</p>
                    <p><strong>📅 Événement:</strong> {event['title']}</p>
                    <p><strong>🪑 Place:</strong> #{seat_number}</p>
                    <p><strong>📆 Date:</strong> {event['event_date'].strftime('%d/%m/%Y à %H:%M')}</p>
                    <p><strong>💰 Prix:</strong> {event['price']} MAD</p>
                    <p><strong>📊 Statut:</strong> <span style="color: #ffc107;">En attente de paiement</span></p>
                </div>
                <div style="text-align: center; padding: 20px 0;">
                    <a href="{url_for('tickets.my_tickets', _external=True)}" 
                       style="background: #d4af37; color: #0a0a0a; padding: 12px 30px; border-radius: 8px; text-decoration: none; font-weight: 700;">
                        Voir mes tickets
                    </a>
                </div>
                <div style="text-align: center; color: rgba(255,255,255,0.3); font-size: 0.8rem; padding-top: 20px; border-top: 1px solid rgba(212,175,55,0.2);">
                    École Events • Tous droits réservés
                </div>
            </div>
            """
            mail.send(msg)
            print(f"✅ Email envoyé à {user_email}")
    except Exception as e:
        print(f"❌ Erreur d'envoi d'email: {str(e)}")

    flash('Place réservée! Veuillez finaliser le paiement.', 'warning')
    return redirect(url_for('tickets.my_tickets'))


@tickets.route('/tickets')
def my_tickets():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    from app import mysql
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT t.*, e.title, e.event_date, e.location, e.image
        FROM tickets t
        JOIN events e ON t.event_id = e.id
        WHERE t.user_id = %s AND t.payment_status != 'cancelled'
        ORDER BY t.booked_at DESC
    """, (session['user_id'],))
    my_tickets = cur.fetchall()
    cur.close()

    return render_template('tickets/my_tickets.html', tickets=my_tickets)


@tickets.route('/tickets/<int:ticket_id>/pay', methods=['GET', 'POST'])
def pay_ticket(ticket_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    from app import mysql
    cur = mysql.connection.cursor()
    
    cur.execute("""
        SELECT t.*, e.title, e.price, e.event_date
        FROM tickets t
        JOIN events e ON t.event_id = e.id
        WHERE t.id = %s AND t.user_id = %s
    """, (ticket_id, session['user_id']))
    ticket = cur.fetchone()
    cur.close()
    
    if not ticket:
        flash('Ticket non trouvé!', 'danger')
        return redirect(url_for('tickets.my_tickets'))
    
    if ticket['payment_status'] == 'paid':
        flash('Ce ticket est déjà payé!', 'info')
        return redirect(url_for('tickets.my_tickets'))
    
    if ticket['event_date'] < datetime.now():
        flash('Impossible de payer pour un événement passé!', 'danger')
        return redirect(url_for('tickets.my_tickets'))
    
    if request.method == 'POST':
        cur = mysql.connection.cursor()
        cur.execute("""
            UPDATE tickets 
            SET payment_status = 'paid' 
            WHERE id = %s
        """, (ticket_id,))
        mysql.connection.commit()
        cur.close()
        
        # ============================================
        # 🔴 إرسال إشعار عند الدفع
        # ============================================
        try:
            from flask_mail import Message
            from app import mail
            
            user_email = session.get('user_email')
            user_name = session.get('user_name')
            
            if user_email:
                msg = Message(
                    subject='✅ Paiement confirmé - École Events',
                    recipients=[user_email]
                )
                msg.html = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #0a0a0a; color: white; border: 2px solid #d4af37; border-radius: 10px;">
                    <div style="text-align: center; padding: 20px 0;">
                        <h1 style="color: #d4af37;">🎫 École Events</h1>
                        <h2 style="color: white;">✅ Paiement confirmé</h2>
                    </div>
                    <div style="background: #161616; padding: 20px; border-radius: 10px; margin: 10px 0;">
                        <p><strong>👤 Client:</strong> {user_name}</p>
                        <p><strong>📅 Événement:</strong> {ticket['title']}</p>
                        <p><strong>🪑 Place:</strong> #{ticket['seat_number']}</p>
                        <p><strong>📆 Date:</strong> {ticket['event_date'].strftime('%d/%m/%Y à %H:%M')}</p>
                        <p><strong>💰 Payé:</strong> {ticket['price']} MAD</p>
                        <p><strong>📊 Statut:</strong> <span style="color: #2ed573;">✅ Payé</span></p>
                    </div>
                    <div style="text-align: center; padding: 20px 0;">
                        <a href="{url_for('tickets.download_pdf', ticket_id=ticket_id, _external=True)}" 
                           style="background: #d4af37; color: #0a0a0a; padding: 12px 30px; border-radius: 8px; text-decoration: none; font-weight: 700;">
                            📄 Télécharger votre ticket
                        </a>
                    </div>
                    <div style="text-align: center; color: rgba(255,255,255,0.3); font-size: 0.8rem; padding-top: 20px; border-top: 1px solid rgba(212,175,55,0.2);">
                        École Events • Tous droits réservés
                    </div>
                </div>
                """
                mail.send(msg)
                print(f"✅ Email de confirmation envoyé à {user_email}")
        except Exception as e:
            print(f"❌ Erreur d'envoi d'email: {str(e)}")
        
        flash('✅ Paiement effectué avec succès!', 'success')
        return redirect(url_for('tickets.my_tickets'))
    
    return render_template('tickets/pay.html', ticket=ticket)


@tickets.route('/tickets/<int:ticket_id>/cancel', methods=['POST'])
def cancel_ticket(ticket_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    from app import mysql
    cur = mysql.connection.cursor()
    
    cur.execute("""
        SELECT t.*, e.id as event_id, e.event_date, e.title
        FROM tickets t
        JOIN events e ON t.event_id = e.id
        WHERE t.id = %s AND t.user_id = %s AND t.payment_status != 'cancelled'
    """, (ticket_id, session['user_id']))
    ticket = cur.fetchone()
    
    if not ticket:
        flash('Ticket non trouvé ou déjà annulé!', 'danger')
        return redirect(url_for('tickets.my_tickets'))
    
    if ticket['event_date'] < datetime.now():
        flash('Impossible d\'annuler un ticket pour un événement passé!', 'danger')
        return redirect(url_for('tickets.my_tickets'))
    
    cur.execute("UPDATE tickets SET payment_status = 'cancelled' WHERE id = %s", (ticket_id,))
    
    cur.execute("""
        UPDATE seats 
        SET status = 'available', user_id = NULL 
        WHERE event_id = %s AND seat_number = %s
    """, (ticket['event_id'], ticket['seat_number']))
    
    cur.execute("""
        UPDATE events 
        SET available_seats = available_seats + 1 
        WHERE id = %s
    """, (ticket['event_id'],))
    
    mysql.connection.commit()
    cur.close()
    
    # ============================================
    # 🔴 إرسال إشعار عند الإلغاء
    # ============================================
    try:
        from flask_mail import Message
        from app import mail
        
        user_email = session.get('user_email')
        user_name = session.get('user_name')
        
        if user_email:
            msg = Message(
                subject='❌ Annulation de réservation - École Events',
                recipients=[user_email]
            )
            msg.html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #0a0a0a; color: white; border: 2px solid #ff6b6b; border-radius: 10px;">
                <div style="text-align: center; padding: 20px 0;">
                    <h1 style="color: #ff6b6b;">🎫 École Events</h1>
                    <h2 style="color: white;">❌ Annulation de réservation</h2>
                </div>
                <div style="background: #161616; padding: 20px; border-radius: 10px; margin: 10px 0;">
                    <p><strong>👤 Client:</strong> {user_name}</p>
                    <p><strong>📅 Événement:</strong> {ticket['title']}</p>
                    <p><strong>🪑 Place:</strong> #{ticket['seat_number']}</p>
                    <p><strong>📆 Date:</strong> {ticket['event_date'].strftime('%d/%m/%Y à %H:%M')}</p>
                    <p><strong>📊 Statut:</strong> <span style="color: #ff6b6b;">❌ Annulé</span></p>
                </div>
                <div style="text-align: center; color: rgba(255,255,255,0.3); font-size: 0.8rem; padding-top: 20px; border-top: 1px solid rgba(255,107,107,0.2);">
                    École Events • Tous droits réservés
                </div>
            </div>
            """
            mail.send(msg)
            print(f"✅ Email d'annulation envoyé à {user_email}")
    except Exception as e:
        print(f"❌ Erreur d'envoi d'email: {str(e)}")
    
    flash('Ticket annulé avec succès!', 'success')
    return redirect(url_for('tickets.my_tickets'))


@tickets.route('/tickets/<int:ticket_id>/pdf')
def download_pdf(ticket_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    from app import mysql
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT t.*, e.title, e.event_date, e.location
        FROM tickets t
        JOIN events e ON t.event_id = e.id
        WHERE t.id = %s AND t.user_id = %s AND t.payment_status = 'paid'
    """, (ticket_id, session['user_id']))
    ticket = cur.fetchone()
    cur.close()
    
    if not ticket:
        flash('Ticket non trouvé ou non payé!', 'danger')
        return redirect(url_for('tickets.my_tickets'))
    
    return render_template('tickets/ticket_pdf.html', ticket=ticket)


@tickets.route('/tickets/<int:ticket_id>/download')
def download_ticket(ticket_id):
    return download_pdf(ticket_id)