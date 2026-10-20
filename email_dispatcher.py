import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formatdate, make_msgid
from datetime import datetime
import database as db

def generate_notice_html(notice, student_name="Student", polished_html=None, attachment_name=None):
    """
    Renders a clean, direct, official HTML email notification for Raiganj University notices.
    Avoids heavy dark styling, gradients, and bloated CSS to maximize deliverability and avoid spam classification.
    """
    title = notice.get('title', 'Official University Notice')
    link = notice.get('link', 'https://raiganjuniversity.ac.in/')
    published_on = notice.get('published_on', datetime.now().strftime('%b %d, %Y'))
    category = notice.get('category', 'General Notice')
    notice_id = notice.get('id', 'N/A')

    attachment_banner = ""
    if attachment_name:
        attachment_banner = f"""
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-left: 4px solid #16a34a; padding: 10px 14px; margin: 16px 0; color: #166534; font-size: 13px;">
          <strong>Official Document Attached:</strong> {attachment_name} (Downloadable directly from this email)
        </div>
        """

    summary_section = ""
    if polished_html:
        summary_section = f"""
        <div style="margin: 20px 0; padding: 16px; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px;">
          <h4 style="margin: 0 0 10px 0; font-size: 14px; color: #003366; border-bottom: 1px solid #cbd5e1; padding-bottom: 6px; text-transform: uppercase; letter-spacing: 0.4px;">
            Official Notice Summary &amp; Directives
          </h4>
          <div style="font-size: 14px; color: #334155; line-height: 1.65;">
            {polished_html}
          </div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
</head>
<body style="margin: 0; padding: 15px; font-family: Arial, Helvetica, sans-serif; background-color: #ffffff; color: #222222; -webkit-font-smoothing: antialiased;">
  <div style="max-width: 650px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
    
    <!-- Official Header -->
    <div style="border-bottom: 2px solid #003366; padding-bottom: 10px; margin-bottom: 18px;">
      <h2 style="margin: 0; color: #003366; font-size: 20px; letter-spacing: 0.5px;">RAIGANJ UNIVERSITY</h2>
      <div style="font-size: 13px; color: #64748b; margin-top: 4px;">
        Official Notice Alert &bull; <strong>{category}</strong>
      </div>
    </div>

    <p style="font-size: 14px; margin: 0 0 14px 0; color: #334155;">Dear {student_name},</p>
    <p style="font-size: 14px; margin: 0 0 16px 0; color: #334155;">An official announcement has been published on the Raiganj University portal:</p>

    <!-- Notice Card -->
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #003366; padding: 14px 16px; margin: 16px 0;">
      <h3 style="margin: 0 0 8px 0; font-size: 16px; color: #0f172a; line-height: 1.4;">{title}</h3>
      <div style="font-size: 13px; color: #64748b;">
        <strong>Notice ID:</strong> #{notice_id} &nbsp;|&nbsp;
        <strong>Published:</strong> {published_on} &nbsp;|&nbsp;
        <strong>Category:</strong> {category}
      </div>
    </div>

    {attachment_banner}

    {summary_section}

    <!-- Official Portal Link -->
    <div style="margin: 22px 0; padding: 12px 14px; background-color: #f1f5f9; border-radius: 6px; font-size: 13px;">
      <strong>Official University Link:</strong><br>
      <a href="{link}" style="color: #0284c7; word-break: break-all;" target="_blank">{link}</a>
    </div>

    <!-- Footer -->
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 12px 0;">
    <p style="font-size: 12px; color: #64748b; margin: 0; line-height: 1.5;">
      This is an official automated alert from the <strong>Raiganj University Notice Dispatcher</strong>.<br>
      Raiganj University &bull; P.O. Raiganj, Dist. Uttar Dinajpur, West Bengal - 733134
    </p>
  </div>
</body>
</html>"""

_smtp_availability_cache = None
_smtp_last_checked_time = 0

def check_smtp_availability(force_recheck=False):
    """
    Fast pre-flight check to test if outbound SMTP port 587 or 465 is reachable from this host.
    Caches the result for 120 seconds to prevent hammering firewall-blocked ports on cloud containers.
    Returns (is_available, message_or_error).
    """
    global _smtp_availability_cache, _smtp_last_checked_time
    import time
    import socket
    now = time.time()
    if not force_recheck and _smtp_availability_cache is not None and (now - _smtp_last_checked_time < 120):
        return _smtp_availability_cache

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.5)
        # Quick probe to smtp.gmail.com port 587
        res = s.connect_ex(('smtp.gmail.com', 587))
        s.close()
        if res == 0:
            _smtp_availability_cache = (True, "OK")
        else:
            _smtp_availability_cache = (False, f"Socket error code {res}")
    except Exception as e:
        _smtp_availability_cache = (False, str(e))

    _smtp_last_checked_time = now
    return _smtp_availability_cache

def get_smtp_connection():
    """
    Establishes SMTP client connection according to environment variables (for GitHub Actions / Cloud)
    or SQLite database configuration.
    Includes pure IPv4 resolution and dual-protocol fallback (Port 587 STARTTLS -> Port 465 SSL)
    to eliminate [Errno 101] Network is unreachable on Render and cloud containers.
    """
    import os
    import socket
    cfg = db.get_smtp_config()

    # Environment variables take priority (ideal for GitHub Actions secrets)
    env_user = os.getenv('SMTP_USER') or os.getenv('SMTP_USERNAME')
    env_pass = os.getenv('SMTP_PASS') or os.getenv('SMTP_PASSWORD')
    env_host = os.getenv('SMTP_HOST')
    env_port = os.getenv('SMTP_PORT')
    env_sender = os.getenv('SENDER_EMAIL')

    user = (env_user or cfg.get('sender_email') or cfg.get('custom_username', '')).strip()
    pwd = (env_pass or cfg.get('custom_password', '')).strip()
    host = env_host or cfg.get('custom_host') or 'smtp.gmail.com'
    mode = cfg.get('mode', 'googlegroup')

    if mode == 'local' and not env_user:
        local_host = cfg.get('local_host', '127.0.0.1')
        local_port = int(cfg.get('local_port', 2525))
        server = smtplib.SMTP(local_host, local_port, timeout=12)
        return server, cfg

    # Resolve pure IPv4 address to avoid IPv6 [Errno 101] Network is unreachable on Render/cloud
    ipv4_host = None
    try:
        ipv4_host = socket.gethostbyname(host)
    except Exception:
        ipv4_host = None

    cfg_effective = dict(cfg)
    if env_user:
        cfg_effective['sender_email'] = env_sender or env_user
        cfg_effective['google_group_email'] = os.getenv('GOOGLE_GROUP_EMAIL') or cfg.get('google_group_email', '')

    # Deliverability / Anti-Spam protection:
    # Ensure sender_email matches the authenticated SMTP user if sending via Gmail or custom relay,
    # so SPF, DKIM, and DMARC alignment passes without triggering phishing/spoofing spam filters.
    if user and '@' in user:
        current_sender = (cfg_effective.get('sender_email') or '').strip()
        if not current_sender or 'raiganjuniversity.ac.in' in current_sender or current_sender == user:
            cfg_effective['sender_email'] = user

    configured_port = int(env_port or cfg.get('custom_port') or 587)

    # Sequence of connection strategies:
    # 1. Pure IPv4 on configured port (usually 587 STARTTLS)
    # 2. Pure IPv4 on Port 465 SMTPS (SSL)
    # 3. Hostname on configured port (587)
    # 4. Hostname on Port 465 (SSL)
    strategies = []
    if ipv4_host:
        strategies.append(('ipv4_tls', ipv4_host, configured_port))
        strategies.append(('ipv4_ssl', ipv4_host, 465))
    strategies.append(('host_tls', host, configured_port))
    strategies.append(('host_ssl', host, 465))

    last_exc = None
    for method, target, port in strategies:
        server = None
        try:
            if 'ssl' in method:
                server = smtplib.SMTP_SSL(target, port, timeout=15)
            else:
                server = smtplib.SMTP(timeout=15)
                server.connect(target, port)
                server._host = host  # Preserve original hostname for SNI/TLS cert validation
                server.starttls()

            if user and pwd:
                server.login(user, pwd)

            return server, cfg_effective
        except Exception as conn_err:
            last_exc = conn_err
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
            server = None
            continue

    raise Exception(f"SMTP Connection failure: {last_exc}")

def apply_email_deliverability_headers(msg_obj, sender_name, sender_email, to_header, subject):
    """
    Applies strict anti-spam & deliverability headers conforming to modern RFC and Gmail/Yahoo policies:
    - Message-ID domain matching sender's authenticated domain to pass SPF/DKIM/DMARC alignment.
    - Reply-To header pointing to monitored sender address.
    - Auto-Submitted & X-Auto-Response-Suppress headers to identify official transactional notices.
    """
    msg_obj['Subject'] = subject
    msg_obj['From'] = f'{sender_name} <{sender_email}>'
    msg_obj['To'] = to_header
    msg_obj['Date'] = formatdate(localtime=True)
    msg_obj['Reply-To'] = sender_email
    msg_obj['Auto-Submitted'] = 'auto-generated'
    msg_obj['X-Auto-Response-Suppress'] = 'All'
    msg_obj['Precedence'] = 'bulk'

    sender_domain = sender_email.split('@')[-1].strip() if '@' in sender_email else None
    msg_obj['Message-ID'] = make_msgid(domain=sender_domain)

def send_single_email(recipient_email, recipient_name, subject, html_content, text_content=None):
    """
    Sends one email via the configured SMTP server.
    """
    server = None
    try:
        server, cfg = get_smtp_connection()
        sender_email = cfg.get('sender_email', 'notices@raiganjuniversity.ac.in')
        sender_name = cfg.get('sender_name', 'Raiganj University Notice Board')

        msg = MIMEMultipart('alternative')
        apply_email_deliverability_headers(msg, sender_name, sender_email, f'{recipient_name} <{recipient_email}>', subject)

        if not text_content:
            text_content = f"New Notice from Raiganj University: {subject}\nPlease visit https://raiganjuniversity.ac.in/ to read."

        msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        server.sendmail(sender_email, [recipient_email], msg.as_string())
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass

def dispatch_notice_to_students(notice):
    """
    Dispatches a new notice. If GOOGLE_GROUP_EMAIL is configured (in env or database), dispatches 1 email
    to the Google Group (which automatically distributes to all 1000+ students).
    Otherwise, dispatches to active students in the database.
    """
    import os
    cfg = db.get_smtp_config()
    group_email = os.getenv('GOOGLE_GROUP_EMAIL') or os.getenv('GROUP_EMAIL') or cfg.get('google_group_email', '').strip()
    students = db.get_students(active_only=True) if not group_email else []

    if not group_email and not students:
        msg = f'No active student recipients enrolled and no Google Group configured. Notice #{notice.get("id")} logged but not mailed.'
        db.log_event('WARNING', 'DISPATCH', msg)
        db.add_dispatch_record(notice.get('id'), notice.get('title'), 0, 'SKIPPED', 'No recipients')
        return {'success': False, 'message': msg, 'sent_count': 0}

    # Normalize link if generic root URL
    notice_id = str(notice.get('id', ''))
    link = notice.get('link', '')
    if not link or link.strip().rstrip('/') in ['https://raiganjuniversity.ac.in', 'http://raiganjuniversity.ac.in']:
        notice['link'] = f"https://raiganjuniversity.ac.in/Website/ViewNotice/{notice_id}"

    # If title is placeholder 'Notice #X', attempt to fetch real title from DB
    title = notice.get('title', '')
    if not title or str(title).startswith('Notice #'):
        db_notice = db.get_notice_by_id(notice_id)
        if db_notice and db_notice.get('title') and not str(db_notice.get('title')).startswith('Notice #'):
            notice['title'] = db_notice['title']
            notice['category'] = db_notice.get('category', notice.get('category', 'General'))
            notice['published_on'] = db_notice.get('published_on', notice.get('published_on', ''))

    subject = f"[RGU Notice #{notice.get('id')}] {notice.get('title')}"
    sent_count = 0
    fail_count = 0
    errors = []

    # Fast pre-flight SMTP check: if running on Render free tier where outbound port 587/465 is blocked,
    # keep notice in pending queue without spamming errors or wasting AI quota.
    can_connect, reason = check_smtp_availability()
    if not can_connect and ('101' in reason or 'unreachable' in reason.lower() or 'blocked' in reason.lower() or 'denied' in reason.lower() or 'error code' in reason.lower()):
        db.add_dispatch_record(notice.get('id'), notice.get('title'), 0, 'DEFERRED', f'Outbound SMTP restricted on hosting ({reason})')
        db.log_event('INFO', 'DISPATCH', f'Notice #{notice.get("id")} safely preserved in queue (outbound SMTP restricted on Render free tier, will be delivered via GitHub Actions runner).')
        return {
            'success': False,
            'sent_count': 0,
            'fail_count': 0,
            'is_cloud_blocked': True,
            'errors': [f"Cloud SMTP restricted: {reason}"]
        }

    # Step 1: Grab notice file (PDF, DOCX, Image) and convert to .md
    # Step 2: Give to Gemini Multimodal AI to polish properly
    # Step 3: Convert to styled HTML and attach file
    import gemini_polisher
    saved_filepath = None
    attachment_name = None
    try:
        proc = gemini_polisher.process_notice_complete(notice)
        raw_md = proc.get('raw_md')
        polished_md = proc.get('polished_md')
        polished_html = proc.get('polished_html')
        saved_filepath = proc.get('saved_filepath')
        attachment_name = proc.get('attachment_name')
        db.log_event('INFO', 'DISPATCH', f"Prepared notice #{notice.get('id')} with AI/MD (Attachment: {attachment_name or 'None'})")
    except Exception as prep_err:
        db.log_event('WARNING', 'AI', f"Notice #{notice.get('id')} prep error ({prep_err}), using direct notice portal link fallback.")
        polished_md = gemini_polisher.generate_structured_fallback_md(notice)
        polished_html = gemini_polisher.convert_md_to_html(polished_md)
        if not saved_filepath and os.path.exists(gemini_polisher.NOTICES_FILES_DIR):
            for fname in os.listdir(gemini_polisher.NOTICES_FILES_DIR):
                if fname.startswith(f"{notice.get('id')}."):
                    saved_filepath = os.path.join(gemini_polisher.NOTICES_FILES_DIR, fname)
                    attachment_name = fname
                    break

    def attach_document(msg_obj):
        if saved_filepath and os.path.exists(saved_filepath):
            try:
                size_mb = os.path.getsize(saved_filepath) / (1024 * 1024)
                if size_mb < 15:  # within standard email attachment limits
                    with open(saved_filepath, 'rb') as f:
                        part = MIMEApplication(f.read(), Name=attachment_name)
                        part['Content-Disposition'] = f'attachment; filename="{attachment_name}"'
                        msg_obj.attach(part)
            except Exception as att_err:
                db.log_event('WARNING', 'DISPATCH', f"Attachment warning ({att_err})")

    server = None
    try:
        server, cfg = get_smtp_connection()
        sender_email = cfg.get('sender_email', 'notices@raiganjuniversity.ac.in')
        sender_name = cfg.get('sender_name', 'Raiganj University Notice Board')

        if group_email:
            # High-efficiency Google Group broadcast (1 email reaches 1000+ students)
            db.log_event('INFO', 'DISPATCH', f'Broadcasting Notice #{notice.get("id")} to Google Group: {group_email}')
            html = generate_notice_html(notice, student_name="Student", polished_html=polished_html, attachment_name=attachment_name)
            text_content = f"New Notice from Raiganj University: {notice.get('title')}\nReference: #{notice.get('id')}\nOfficial Link: {notice.get('link')}\n\n{polished_md}"
            
            msg = MIMEMultipart('mixed')
            apply_email_deliverability_headers(msg, sender_name, sender_email, f"RGU Department Students <{group_email}>", subject)

            alt_part = MIMEMultipart('alternative')
            alt_part.attach(MIMEText(text_content, 'plain', 'utf-8'))
            alt_part.attach(MIMEText(html, 'html', 'utf-8'))
            msg.attach(alt_part)

            # Attach actual PDF / document
            attach_document(msg)

            server.sendmail(sender_email, [group_email], msg.as_string())
            sent_count = 1
            db.log_event('SUCCESS', 'DISPATCH', f'Notice #{notice.get("id")} successfully broadcasted to Google Group {group_email} (with attachment: {attachment_name or "None"})!')
            db.add_dispatch_record(notice.get('id'), notice.get('title'), 1, 'SUCCESS', f'Google Group: {group_email}')
            return {'success': True, 'sent_count': 1, 'is_group': True}

        # Otherwise send to individual enrolled students
        db.log_event('INFO', 'DISPATCH', f'Starting email dispatch of Notice #{notice.get("id")} to {len(students)} active student(s)...')
        for s in students:
            try:
                html = generate_notice_html(notice, student_name=s.get('name', 'Student'), polished_html=polished_html, attachment_name=attachment_name)
                text_content = f"New Notice from Raiganj University: {notice.get('title')}\nReference: #{notice.get('id')}\nOfficial Link: {notice.get('link')}\n\n{polished_md}"
                
                msg = MIMEMultipart('mixed')
                apply_email_deliverability_headers(msg, sender_name, sender_email, f"{s.get('name', 'Student')} <{s['email']}>", subject)

                alt_part = MIMEMultipart('alternative')
                alt_part.attach(MIMEText(text_content, 'plain', 'utf-8'))
                alt_part.attach(MIMEText(html, 'html', 'utf-8'))
                msg.attach(alt_part)

                # Attach actual PDF / document
                attach_document(msg)

                server.sendmail(sender_email, [s['email']], msg.as_string())
                sent_count += 1
            except Exception as item_err:
                fail_count += 1
                errors.append(f"{s['email']}: {str(item_err)}")
    except Exception as conn_err:
        fail_count += (len(students) if students else 1)
        err_msg = str(conn_err)
        errors.append(f"SMTP Connection failure: {err_msg}")
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass

    is_cloud_blocked = any('101' in e or 'unreachable' in e.lower() for e in errors)
    status = 'SUCCESS' if fail_count == 0 else ('PARTIAL' if sent_count > 0 else ('DEFERRED' if is_cloud_blocked else 'FAILED'))
    err_summary = '; '.join(errors[:5]) if errors else ''
    
    db.add_dispatch_record(notice.get('id'), notice.get('title'), sent_count, status, err_summary)
    
    if sent_count > 0:
        db.log_event('SUCCESS', 'DISPATCH', f'Notice #{notice.get("id")} successfully emailed to {sent_count} student(s)! (Failed: {fail_count})')
    elif is_cloud_blocked:
        db.log_event('INFO', 'DISPATCH', f'Notice #{notice.get("id")} preserved in queue (outbound SMTP restricted on Render free tier, will be delivered via GitHub Actions runner).')
    else:
        db.log_event('ERROR', 'DISPATCH', f'Failed to deliver Notice #{notice.get("id")}: {err_summary}')

    return {
        'success': sent_count > 0,
        'sent_count': sent_count,
        'fail_count': fail_count,
        'is_cloud_blocked': is_cloud_blocked,
        'errors': errors
    }

def test_smtp_connection(test_email=None):
    """
    Tests SMTP connection and sends a sample Raiganj University alert email
    to verify Google Group or direct delivery.
    """
    try:
        import os
        server, cfg = get_smtp_connection()
        group_email = os.getenv('GOOGLE_GROUP_EMAIL') or cfg.get('google_group_email', '').strip()
        sender_email = (cfg.get('sender_email') or cfg.get('custom_username', '')).strip()
        sender_name = cfg.get('sender_name', 'Raiganj University Notice Board')

        target = test_email or group_email or sender_email
        if not target:
            return {
                'success': False,
                'message': 'Please enter a test email address or configure your Google Group email first.'
            }

        server.noop()

        sample_notice = {
            'id': 'TEST-999',
            'title': 'Raiganj University Notice Dispatcher: Google Group Connection Verified',
            'link': 'https://raiganjuniversity.ac.in/',
            'published_on': datetime.now().strftime('%b %d, %Y %I:%M %p'),
            'category': 'System Verification'
        }
        html = generate_notice_html(sample_notice, student_name='Administrator')

        msg = MIMEMultipart('alternative')
        target_to = f"Google Group <{target}>" if '@googlegroups.com' in target else target
        apply_email_deliverability_headers(msg, sender_name, sender_email, target_to, '[TEST] Raiganj University Notice Dispatcher: Test Alert')

        msg.attach(MIMEText('This is a test notification confirming your Google Group notice broadcast system is fully active.', 'plain'))
        msg.attach(MIMEText(html, 'html'))

        server.sendmail(sender_email, [target], msg.as_string())
        server.quit()
        
        db.log_event('SUCCESS', 'SMTP', f'Test email delivered to {target}')
        return {'success': True, 'message': f'Connection verified and test alert delivered to {target}!'}
    except Exception as e:
        err = str(e)
        db.log_event('ERROR', 'SMTP', f'Connection Test failed: {err}')
        return {'success': False, 'message': f'SMTP Error: {err}'}
