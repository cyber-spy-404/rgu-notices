import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from datetime import datetime
import database as db

def generate_notice_html(notice, student_name="Student", polished_html=None):
    """
    Renders an elegant, modern, responsive HTML email template for Raiganj University notices,
    with embedded Gemini AI polished breakdown.
    """
    title = notice.get('title', 'Official University Notice')
    link = notice.get('link', 'https://raiganjuniversity.ac.in/')
    published_on = notice.get('published_on', datetime.now().strftime('%b %d, %Y'))
    category = notice.get('category', 'General Notice')
    notice_id = notice.get('id', 'N/A')

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
      <div class="uni-emblem">🏛️</div>
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
            'mode': 'custom',
            'sender_email': env_sender or env_user.strip(),
            'sender_name': os.getenv('SENDER_NAME', 'Raiganj University Notice Board')
        }
        return server, cfg_override

    mode = cfg.get('mode', 'local')

    if mode == 'local':
        host = cfg.get('local_host', '127.0.0.1')
        port = int(cfg.get('local_port', 2525))
        server = smtplib.SMTP(host, port, timeout=12)
        return server, cfg
    else:
        host = cfg.get('custom_host', 'smtp.gmail.com')
        port = int(cfg.get('custom_port', 587))
        use_ssl = bool(cfg.get('custom_use_ssl', 0))
        use_tls = bool(cfg.get('custom_use_tls', 1))

        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if use_tls:
                server.starttls()

        user = cfg.get('custom_username', '').strip()
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
    Dispatches a new notice. If GOOGLE_GROUP_EMAIL is configured, dispatches 1 email
    to the Google Group (which automatically distributes to all 1000+ students).
    Otherwise, dispatches to active students in the database.
    """
    import os
    group_email = os.getenv('GOOGLE_GROUP_EMAIL') or os.getenv('GROUP_EMAIL')
    students = db.get_students(active_only=True) if not group_email else []

    if not group_email and not students:
        msg = f'No active student recipients enrolled and no GOOGLE_GROUP_EMAIL set. Notice #{notice.get("id")} logged but not mailed.'
        db.log_event('WARNING', 'DISPATCH', msg)
        db.add_dispatch_record(notice.get('id'), notice.get('title'), 0, 'SKIPPED', 'No recipients')
        return {'success': False, 'message': msg, 'sent_count': 0}

    subject = f"[RGU Notice #{notice.get('id')}] {notice.get('title')}"
    sent_count = 0
    fail_count = 0
    errors = []

    # Step 1: Grab notice content and save as clean .md file
    # Step 2: Give to Gemini to polish properly
    # Step 3: Convert to styled HTML for email
    import gemini_polisher
    try:
        raw_md, md_path = gemini_polisher.grab_and_convert_to_md(notice)
        db.log_event('INFO', 'DISPATCH', f"Saved notice #{notice.get('id')} to Markdown: {md_path}")
        polished_md = gemini_polisher.polish_with_gemini(raw_md, notice)
        polished_html = gemini_polisher.convert_md_to_html(polished_md)
    except Exception as prep_err:
        db.log_event('WARNING', 'AI', f"AI processing error ({prep_err}), proceeding with default layout.")
        polished_html = None
        polished_md = notice.get('title')

    server = None
    try:
        server, cfg = get_smtp_connection()
        sender_email = cfg.get('sender_email', 'notices@raiganjuniversity.ac.in')
        sender_name = cfg.get('sender_name', 'Raiganj University Notice Board')

        if group_email:
            # High-efficiency Google Group broadcast (1 email reaches 1000+ students)
            db.log_event('INFO', 'DISPATCH', f'Broadcasting Notice #{notice.get("id")} to Google Group: {group_email}')
            html = generate_notice_html(notice, student_name="Student", polished_html=polished_html)
            text_content = f"New Notice from Raiganj University: {notice.get('title')}\nReference: #{notice.get('id')}\nOfficial Link: {notice.get('link')}\n\n{polished_md}"
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f'{sender_name} <{sender_email}>'
            msg['To'] = f"RGU Department Students <{group_email}>"
            msg['Date'] = formatdate(localtime=True)
            msg['Message-ID'] = make_msgid(domain='raiganjuniversity.ac.in')

            msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
            msg.attach(MIMEText(html, 'html', 'utf-8'))

            server.sendmail(sender_email, [group_email], msg.as_string())
            sent_count = 1
            db.log_event('SUCCESS', 'DISPATCH', f'Notice #{notice.get("id")} successfully broadcasted to Google Group {group_email}!')
            db.add_dispatch_record(notice.get('id'), notice.get('title'), 1, 'SUCCESS', f'Google Group: {group_email}')
            return {'success': True, 'sent_count': 1, 'is_group': True}

        # Otherwise send to individual enrolled students
        db.log_event('INFO', 'DISPATCH', f'Starting email dispatch of Notice #{notice.get("id")} to {len(students)} active student(s)...')
        for s in students:
            try:
                html = generate_notice_html(notice, student_name=s.get('name', 'Student'), polished_html=polished_html)
                text_content = f"New Notice from Raiganj University: {notice.get('title')}\nReference: #{notice.get('id')}\nOfficial Link: {notice.get('link')}\n\n{polished_md}"
                
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = f'{sender_name} <{sender_email}>'
                msg['To'] = f"{s.get('name', 'Student')} <{s['email']}>"
                msg['Date'] = formatdate(localtime=True)
                msg['Message-ID'] = make_msgid(domain='raiganjuniversity.ac.in')

                msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
                msg.attach(MIMEText(html, 'html', 'utf-8'))

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
    Tests SMTP connection and optionally sends a verification test email.
    """
    try:
        server, cfg = get_smtp_connection()
        mode = cfg.get('mode', 'local')
        host_info = f"{cfg.get('local_host', '127.0.0.1')}:{cfg.get('local_port', 1025)}" if mode == 'local' else f"{cfg.get('custom_host')}:{cfg.get('custom_port')}"
        
        server.noop()

        if test_email:
            sample_notice = {
                'id': 'TEST-999',
                'title': 'Raiganj University SMTP Test Alert: Connection Verified',
                'link': 'https://raiganjuniversity.ac.in/',
                'published_on': datetime.now().strftime('%b %d, %Y %I:%M %p'),
                'category': 'System Verification'
            }
            html = generate_notice_html(sample_notice, student_name='Administrator')
            sender_email = cfg.get('sender_email', 'notices@raiganjuniversity.ac.in')
            sender_name = cfg.get('sender_name', 'Raiganj University Notice Board')

            msg = MIMEMultipart('alternative')
            msg['Subject'] = '[TEST] Raiganj University SMTP Connection Test'
            msg['From'] = f'{sender_name} <{sender_email}>'
            msg['To'] = test_email
            msg['Date'] = formatdate(localtime=True)
            msg.attach(MIMEText('This is a test notification confirming your Raiganj University SMTP Dispatcher is working.', 'plain'))
            msg.attach(MIMEText(html, 'html'))

            server.sendmail(sender_email, [test_email], msg.as_string())
            server.quit()
            
            db.log_event('SUCCESS', 'SMTP', f'SMTP test successful. Email sent to {test_email} via {host_info} ({mode} mode)')
            return {'success': True, 'message': f'SMTP connection verified and test email sent to {test_email} ({mode} mode via {host_info})'}
        
        server.quit()
        db.log_event('SUCCESS', 'SMTP', f'SMTP connection verified successfully ({mode} mode on {host_info})')
        return {'success': True, 'message': f'Connection established successfully to {host_info} ({mode} mode)'}
    except Exception as e:
        err = str(e)
        db.log_event('ERROR', 'SMTP', f'SMTP Connection Test failed: {err}')
        return {'success': False, 'message': f'SMTP Error: {err}'}
