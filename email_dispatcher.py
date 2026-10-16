import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formatdate, make_msgid
from datetime import datetime
import database as db

def generate_notice_html(notice, student_name="Student", polished_html=None, attachment_name=None):
    """
    Renders an elegant, modern, responsive HTML email template for Raiganj University notices,
    with embedded Gemini AI polished breakdown and attachment indicator.
    """
    title = notice.get('title', 'Official University Notice')
    link = notice.get('link', 'https://raiganjuniversity.ac.in/')
    published_on = notice.get('published_on', datetime.now().strftime('%b %d, %Y'))
    category = notice.get('category', 'General Notice')
    notice_id = notice.get('id', 'N/A')

    attachment_banner = ""
    if attachment_name:
        attachment_banner = f"""
        <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 8px; padding: 12px 18px; margin: 18px 0; color: #a7f3d0; font-size: 13.5px; display: flex; align-items: center; gap: 10px;">
          <span>📎 <strong>Official Document Attached:</strong> {attachment_name} (Downloadable directly from this email)</span>
        </div>
        """

    polished_section = ""
    if polished_html:
        polished_section = f"""
        <div style="background: #172033; border: 1px solid rgba(99, 102, 241, 0.35); border-radius: 12px; padding: 22px; margin: 24px 0; line-height: 1.65; color: #cbd5e1; box-shadow: 0 4px 16px rgba(0,0,0,0.2);">
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 16px; color: #a5b4fc; font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: 0.6px; border-bottom: 1px solid #334155; padding-bottom: 10px;">
            <span>✨ AI Polished Student Breakdown</span>
          </div>
          <div class="polished-content" style="font-size: 14px;">
            {polished_html}
          </div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
      background-color: #0b1120;
      color: #e2e8f0;
      -webkit-font-smoothing: antialiased;
    }}
    .email-container {{
      max-width: 640px;
      margin: 25px auto;
      background: #111827;
      border: 1px solid #1f2937;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 20px 40px rgba(0,0,0,0.4);
    }}
    .header-banner {{
      background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%);
      padding: 32px 28px;
      text-align: center;
      border-bottom: 2px solid #6366f1;
    }}
    .uni-emblem {{
      display: inline-block;
      width: 54px;
      height: 54px;
      line-height: 54px;
      background: rgba(255, 255, 255, 0.12);
      border: 2px solid rgba(255, 255, 255, 0.25);
      border-radius: 50%;
      font-size: 26px;
      margin-bottom: 12px;
    }}
    .uni-title {{
      margin: 0;
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: #ffffff;
      text-transform: uppercase;
    }}
    .uni-subtitle {{
      margin: 6px 0 0 0;
      font-size: 13px;
      color: #c7d2fe;
      letter-spacing: 0.8px;
    }}
    .content-body {{
      padding: 32px 28px;
    }}
    .greeting {{
      font-size: 15px;
      color: #94a3b8;
      margin-top: 0;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.3px;
      margin-right: 6px;
    }}
    .badge-category {{
      background: rgba(99, 102, 241, 0.2);
      color: #a5b4fc;
      border: 1px solid rgba(99, 102, 241, 0.4);
    }}
    .badge-id {{
      background: rgba(16, 185, 129, 0.2);
      color: #6ee7b7;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }}
    .notice-card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 22px;
      margin: 20px 0;
    }}
    .notice-title {{
      margin: 0 0 14px 0;
      font-size: 18px;
      line-height: 1.45;
      color: #f8fafc;
      font-weight: 600;
    }}
    .meta-row {{
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      color: #94a3b8;
      border-top: 1px solid #334155;
      padding-top: 12px;
      margin-top: 14px;
    }}
    .btn-container {{
      text-align: center;
      margin: 26px 0 10px 0;
    }}
    .btn-action {{
      display: inline-block;
      background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
      color: #ffffff !important;
      text-decoration: none;
      padding: 14px 32px;
      font-size: 15px;
      font-weight: 600;
      border-radius: 8px;
      box-shadow: 0 4px 14px rgba(79, 70, 229, 0.4);
    }}
    .footer {{
      background: #0f172a;
      padding: 24px;
      text-align: center;
      border-top: 1px solid #1f2937;
      font-size: 12px;
      color: #64748b;
      line-height: 1.6;
    }}
    .footer a {{
      color: #818cf8;
      text-decoration: none;
    }}
    .polished-content h3 {{
      color: #93c5fd;
      font-size: 15px;
      margin-top: 16px;
      margin-bottom: 8px;
    }}
    .polished-content ul, .polished-content ol {{
      padding-left: 20px;
      margin: 8px 0;
    }}
    .polished-content li {{
      margin-bottom: 4px;
    }}
  </style>
</head>
<body>
  <div class="email-container">
    <div class="header-banner">
      <div style="margin-bottom: 12px;">
        <img src="https://rgu-notices.onrender.com/static/images/logo.png" alt="Raiganj University Logo" width="56" height="56" style="border-radius: 10px; background: #ffffff; padding: 3px; display: inline-block; box-shadow: 0 4px 12px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.3);">
      </div>
      <h1 class="uni-title">Raiganj University</h1>
      <p class="uni-subtitle">রায়গঞ্জ বিশ্ববিদ্যালয় &bull; Official Notice Alert</p>
    </div>
    <div class="content-body">
      <p class="greeting">Dear {student_name},</p>
      <p style="color: #cbd5e1; line-height: 1.5;">A new official announcement has been published on the Raiganj University portal:</p>
      
      <div class="notice-card">
        <div>
          <span class="badge badge-category">{category}</span>
          <span class="badge badge-id">Notice #{notice_id}</span>
        </div>
        <h2 class="notice-title" style="margin-top: 12px;">{title}</h2>
        <div class="meta-row">
          <span>📅 Published: <strong>{published_on}</strong></span>
          <span>🏛️ Source: <strong>Raiganj University</strong></span>
        </div>
      </div>

      {attachment_banner}

      {polished_section}

      <div class="btn-container">
        <a href="{link}" class="btn-action" target="_blank">📄 View Official Notice &amp; Download PDF</a>
      </div>
      <p style="text-align: center; font-size: 12px; color: #64748b; margin-top: 12px;">
        Link: <a href="{link}" style="color: #818cf8; word-break: break-all;">{link}</a>
      </p>
    </div>
    <div class="footer">
      <p>This automated alert is delivered by the <strong>Raiganj University Notice Dispatcher</strong>.<br>
      Automated daily checks run at 00:00 midnight for newly added announcements.</p>
      <p><a href="https://raiganjuniversity.ac.in/">Official University Website</a> &bull; P.O. Raiganj, Dist. Uttar Dinajpur, West Bengal - 733134</p>
    </div>
  </div>
</body>
</html>"""

def get_smtp_connection():
    """
    Establishes SMTP client connection according to environment variables (for GitHub Actions / Cloud)
    or SQLite database configuration.
    """
    import os
    cfg = db.get_smtp_config()

    # Environment variables take priority (ideal for GitHub Actions secrets)
    env_user = os.getenv('SMTP_USER') or os.getenv('SMTP_USERNAME')
    env_pass = os.getenv('SMTP_PASS') or os.getenv('SMTP_PASSWORD')
    env_host = os.getenv('SMTP_HOST')
    env_port = os.getenv('SMTP_PORT')
    env_sender = os.getenv('SENDER_EMAIL')

    if env_user and env_pass:
        host = env_host or 'smtp.gmail.com'
        port = int(env_port or 587)
        server = smtplib.SMTP(host, port, timeout=20)
        server.starttls()
        server.login(env_user.strip(), env_pass.strip())
        cfg_override = {
            'mode': 'googlegroup',
            'sender_email': env_sender or env_user.strip(),
            'sender_name': os.getenv('SENDER_NAME', 'Raiganj University Notice Board'),
            'google_group_email': os.getenv('GOOGLE_GROUP_EMAIL') or cfg.get('google_group_email', '')
        }
        return server, cfg_override

    mode = cfg.get('mode', 'googlegroup')

    if mode == 'local':
        host = cfg.get('local_host', '127.0.0.1')
        port = int(cfg.get('local_port', 2525))
        server = smtplib.SMTP(host, port, timeout=12)
        return server, cfg
    else:
        # googlegroup or custom
        host = cfg.get('custom_host') or 'smtp.gmail.com'
        port = int(cfg.get('custom_port') or 587)
        use_ssl = bool(cfg.get('custom_use_ssl', 0))
        use_tls = bool(cfg.get('custom_use_tls', 1))

        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if use_tls:
                server.starttls()

        user = (cfg.get('sender_email') or cfg.get('custom_username', '')).strip()
        pwd = cfg.get('custom_password', '').strip()
        if user and pwd:
            server.login(user, pwd)

        return server, cfg

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
        msg['Subject'] = subject
        msg['From'] = f'{sender_name} <{sender_email}>'
        msg['To'] = f'{recipient_name} <{recipient_email}>'
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain='raiganjuniversity.ac.in')

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
        db.log_event('WARNING', 'AI', f"AI processing error ({prep_err}), proceeding with default layout.")
        polished_html = None
        polished_md = notice.get('title')

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
            msg['Subject'] = subject
            msg['From'] = f'{sender_name} <{sender_email}>'
            msg['To'] = f"RGU Department Students <{group_email}>"
            msg['Date'] = formatdate(localtime=True)
            msg['Message-ID'] = make_msgid(domain='raiganjuniversity.ac.in')

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
                msg['Subject'] = subject
                msg['From'] = f'{sender_name} <{sender_email}>'
                msg['To'] = f"{s.get('name', 'Student')} <{s['email']}>"
                msg['Date'] = formatdate(localtime=True)
                msg['Message-ID'] = make_msgid(domain='raiganjuniversity.ac.in')

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
        fail_count += len(students)
        errors.append(f"SMTP Connection failure: {str(conn_err)}")
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass

    status = 'SUCCESS' if fail_count == 0 else ('PARTIAL' if sent_count > 0 else 'FAILED')
    err_summary = '; '.join(errors[:5]) if errors else ''
    
    db.add_dispatch_record(notice.get('id'), notice.get('title'), sent_count, status, err_summary)
    
    if sent_count > 0:
        db.log_event('SUCCESS', 'DISPATCH', f'Notice #{notice.get("id")} successfully emailed to {sent_count} student(s)! (Failed: {fail_count})')
    else:
        db.log_event('ERROR', 'DISPATCH', f'Failed to deliver Notice #{notice.get("id")}: {err_summary}')

    return {
        'success': sent_count > 0,
        'sent_count': sent_count,
        'fail_count': fail_count,
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
        msg['Subject'] = '[TEST] Raiganj University Notice Dispatcher: Test Alert'
        msg['From'] = f'{sender_name} <{sender_email}>'
        msg['To'] = f"Google Group <{target}>" if '@googlegroups.com' in target else target
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain='raiganjuniversity.ac.in')

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
