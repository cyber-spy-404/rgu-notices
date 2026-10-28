import os
import atexit
import threading
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, Response
import database as db
import scraper
import scheduler_engine
import importlib
import local_smtp_server
import security
import email_dispatcher

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.secret_key = os.getenv('FLASK_SECRET_KEY') or os.getenv('SECRET_KEY') or security.get_cipher()._signing_key

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    if request.path.startswith('/api/smtp'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
    return response

# Initialize Database
db.init_db()

# Start background services (safe for both local and cloud/WSGI environments)
try:
    smtp_cfg = db.get_smtp_config()
    local_port = int(smtp_cfg.get('local_port', 2525))
    local_host = smtp_cfg.get('local_host', '127.0.0.1')
    local_smtp_server.start_local_smtp_server(host=local_host, port=local_port)
except Exception as e:
    print(f"[!] Notice: Local SMTP server not bound ({e}). Use external SMTP.")

try:
    scheduler_engine.start_scheduler()
except Exception as e:
    print(f"[!] Notice: In-process scheduler skipped ({e}). Use cron/scheduled tasks.")

# Graceful cleanup
try:
    atexit.register(local_smtp_server.stop_local_smtp_server)
except Exception:
    pass

# ----------------- Automatic Pending Mail Dispatch Worker ----------------- #
_pending_dispatch_lock = threading.Lock()
_last_smtp_restriction_log_time = 0
_last_smtp_restriction_count = -1

def trigger_pending_mail_dispatch_async(source="WEB_ACCESS"):
    """
    Checks the database for any unmailed notices (email_status != 'sent')
    and automatically delivers them in a non-blocking background thread
    whenever someone accesses the webapp (visits, pings, or restarts).
    Note: Does NOT perform a live scrape, as scraping is scheduled strictly twice daily (7 AM & 7 PM IST).
    """
    def _worker():
        if not _pending_dispatch_lock.acquire(blocking=False):
            return  # Already actively dispatching in another background worker
        try:
            unmailed = db.get_unmailed_notices(limit=50)
            if not unmailed:
                return

            import email_dispatcher
            can_connect, reason = email_dispatcher.check_smtp_availability()
            if not can_connect and ('101' in reason or 'unreachable' in reason.lower() or 'blocked' in reason.lower() or 'denied' in reason.lower() or 'error code' in reason.lower()):
                global _last_smtp_restriction_log_time, _last_smtp_restriction_count
                now_ts = time.time()
                unmailed_len = len(unmailed)
                # Only log when unmailed count changes or every 30 minutes to keep audit logs clean
                if (now_ts - _last_smtp_restriction_log_time > 1800) or (unmailed_len != _last_smtp_restriction_count):
                    _last_smtp_restriction_log_time = now_ts
                    _last_smtp_restriction_count = unmailed_len
                    db.log_event('INFO', 'DISPATCH', f"[{source}] Outbound SMTP port is restricted on cloud host ({reason}). Safely preserving {unmailed_len} notice(s) in queue for GitHub Actions dispatcher.")
                return

            db.log_event('INFO', 'DISPATCH', f"[{source}] Detected {len(unmailed)} unmailed notice(s) in database. Starting instant delivery to students / Google Group...")
            import gemini_polisher
            sent_count = 0
            for notice in unmailed:
                try:
                    # Check if notice is polished, if not polish now
                    if not notice.get('polished_markdown') and not notice.get('has_gemini_polish'):
                        gemini_polisher.process_notice_complete(notice)

                    res = email_dispatcher.dispatch_notice_to_students(notice)
                    if res.get('success'):
                        db.mark_notice_emailed(notice['id'], 'sent')
                        sent_count += 1
                    elif res.get('is_cloud_blocked'):
                        # Outbound SMTP restricted on Render free tier; keep in pending queue for GitHub Actions
                        pass
                    else:
                        db.mark_notice_emailed(notice['id'], 'failed')
                    time.sleep(1.5)  # respectful SMTP pacing between emails
                except Exception as de:
                    db.log_event('ERROR', 'DISPATCH', f"Auto-dispatch error on notice #{notice.get('id')}: {de}")
                    db.mark_notice_emailed(notice['id'], 'failed')
            if sent_count > 0:
                db.log_event('SUCCESS', 'DISPATCH', f"[{source}] Automatic delivery complete: {sent_count}/{len(unmailed)} unmailed notice(s) delivered to Google Group.")
        except Exception as e:
            db.log_event('ERROR', 'DISPATCH', f"Background unmailed worker exception: {e}")
        finally:
            _pending_dispatch_lock.release()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

def start_unmailed_notices_poller():
    """
    Continuous background loop that runs every 2 minutes (120 seconds).
    Always checks for any scraped but unmailed notices (email_status != 'sent')
    and delivers them automatically to students / Google Group.
    """
    def _loop():
        time.sleep(8)  # Brief initial sleep so server binds cleanly
        while True:
            try:
                unmailed = db.get_unmailed_notices(limit=50)
                if unmailed:
                    trigger_pending_mail_dispatch_async("2MIN_POLLER")
            except Exception as pe:
                db.log_event('WARNING', 'QUEUE', f"2-minute unmailed poller loop note: {pe}")
            time.sleep(120)  # Always scan and retry every 2 minutes

    thread = threading.Thread(target=_loop, daemon=True, name="UnmailedNoticesPoller2Min")
    thread.start()

def sync_and_deliver_on_startup():
    """
    On application boot: checks database and delivers any unmailed notices.
    """
    try:
        time.sleep(2)  # Brief pause to allow gunicorn / web workers to bind
        trigger_pending_mail_dispatch_async("STARTUP_SYNC")
    except Exception as e:
        db.log_event('WARNING', 'STARTUP', f"Startup unmailed notice sync note: {e}")

# Automatically check for unmailed notices and deliver on web server boot
try:
    threading.Thread(target=sync_and_deliver_on_startup, daemon=True).start()
    start_unmailed_notices_poller()
except Exception as _e:
    pass

# ----------------- Web UI Routes ----------------- #

@app.route('/')
def index():
    trigger_pending_mail_dispatch_async("WEB_VISIT")
    return render_template('index.html')

@app.route('/email-preview/<int:msg_id>')
def email_preview(msg_id):
    inbox = db.get_inbox_emails(limit=200)
    for m in inbox:
        if m['id'] == msg_id:
            html = m['body_html'] or f"<pre style='font-family: monospace; white-space: pre-wrap; padding: 20px;'>{m['body_text']}</pre>"
            return html
    return "<h3>Email not found</h3>", 404

# ----------------- System Status API ----------------- #

@app.route('/api/status', methods=['GET'])
def api_status():
    import os
    stats = db.get_stats()
    sched_status = scheduler_engine.get_scheduler_status()
    smtp_status = local_smtp_server.get_smtp_status()
    smtp_cfg = db.get_smtp_config()
    group_email = os.getenv('GOOGLE_GROUP_EMAIL') or smtp_cfg.get('google_group_email', '')

    import zoneinfo
    kolkata_tz = zoneinfo.ZoneInfo('Asia/Kolkata')
    return jsonify({
        'status': 'ok',
        'server_time': datetime.now(kolkata_tz).strftime('%Y-%m-%d %H:%M:%S'),
        'stats': stats,
        'scheduler': sched_status,
        'smtp_server': smtp_status,
        'smtp_mode': smtp_cfg.get('mode', 'googlegroup'),
        'sender_email': smtp_cfg.get('sender_email'),
        'google_group_email': group_email
    })

# ----------------- Student Management API ----------------- #

@app.route('/api/students', methods=['GET'])
def api_get_students():
    search = request.args.get('search', '').strip()
    active_only = request.args.get('active_only', 'false').lower() == 'true'
    students = db.get_students(search=search, active_only=active_only)
    return jsonify({'students': students, 'count': len(students)})

@app.route('/api/students', methods=['POST'])
def api_add_student():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    department = data.get('department', 'General').strip()
    roll_no = data.get('roll_no', '').strip()

    if not email or '@' not in email:
        return jsonify({'success': False, 'error': 'A valid student email is required.'}), 400

    if not name:
        name = email.split('@')[0].capitalize()

    result = db.add_student(name, email, department, roll_no)
    if result.get('success'):
        return jsonify(result), 201
    return jsonify(result), 400

@app.route('/api/students/bulk', methods=['POST'])
def api_bulk_students():
    data = request.get_json() or {}
    raw_text = data.get('raw_data', '')
    students_list = []

    # Parse lines: supports CSV (name, email, dept, roll) or just emails
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    for line in lines:
        parts = [p.strip() for p in line.split(',') if p.strip()]
        if len(parts) >= 2:
            name = parts[0]
            email = parts[1]
            dept = parts[2] if len(parts) > 2 else 'General'
            roll = parts[3] if len(parts) > 3 else ''
            students_list.append({'name': name, 'email': email, 'department': dept, 'roll_no': roll})
        elif len(parts) == 1 and '@' in parts[0]:
            email = parts[0]
            name = email.split('@')[0].capitalize()
            students_list.append({'name': name, 'email': email, 'department': 'General', 'roll_no': ''})

    result = db.bulk_add_students(students_list)
    return jsonify(result)

@app.route('/api/students/<int:student_id>', methods=['DELETE'])
def api_delete_student(student_id):
    success = db.delete_student(student_id)
    return jsonify({'success': success})

@app.route('/api/students/<int:student_id>/status', methods=['PATCH'])
def api_toggle_student_status(student_id):
    data = request.get_json() or {}
    is_active = data.get('is_active', 1)
    db.toggle_student_status(student_id, is_active)
    return jsonify({'success': True, 'is_active': is_active})

@app.route('/api/students/seed-sample', methods=['POST'])
def api_seed_students():
    samples = [
        {'name': 'Souvik Mukherjee', 'email': 'souvik.rgu@example.com', 'department': 'Computer Science', 'roll_no': 'CS-2026-042'},
        {'name': 'Ananya Roy', 'email': 'ananya.roy@example.com', 'department': 'Mathematics', 'roll_no': 'MATH-2026-015'},
        {'name': 'Rohan Sen', 'email': 'rohan.sen@example.com', 'department': 'English Literature', 'roll_no': 'ENG-2026-088'},
        {'name': 'Priyanka Das', 'email': 'priyanka.das@example.com', 'department': 'Physics', 'roll_no': 'PHY-2026-023'},
        {'name': 'Debojyoti Paul', 'email': 'debojyoti.paul@example.com', 'department': 'Commerce', 'roll_no': 'COM-2026-110'}
    ]
    res = db.bulk_add_students(samples)
    return jsonify(res)

# ----------------- Notices & Scraper API ----------------- #

@app.route('/api/notices', methods=['GET'])
def api_get_notices():
    search = request.args.get('search', '').strip()
    limit = int(request.args.get('limit', 100))
    notices = db.get_notices(limit=limit, search=search)
    return jsonify({'notices': notices, 'count': len(notices)})

@app.route('/api/notices/scan-now', methods=['POST'])
def api_scan_now():
    """
    Manually triggers notice check immediately.
    """
    res = scraper.run_notice_check()
    return jsonify(res)

@app.route('/api/notices/dispatch-pending', methods=['POST'])
def api_dispatch_pending():
    """
    Manually triggers immediate delivery of all pending/unmailed notices in queue.
    """
    unmailed = db.get_unmailed_notices(limit=50)
    if not unmailed:
        return jsonify({
            'success': True,
            'message': 'No pending notices in delivery queue. All notices up to date!',
            'sent_count': 0,
            'total': 0
        })

    import email_dispatcher
    sent_count = 0
    total = len(unmailed)
    db.log_event('INFO', 'DISPATCH', f'Manual dispatch triggered for {total} pending notice(s)...')

    for notice in unmailed:
        try:
            res = email_dispatcher.dispatch_notice_to_students(notice)
            if res.get('success'):
                db.mark_notice_emailed(notice['id'], 'sent')
                sent_count += 1
            elif res.get('is_cloud_blocked'):
                pass
            else:
                db.mark_notice_emailed(notice['id'], 'failed')
            time.sleep(1)
        except Exception as e:
            db.log_event('ERROR', 'DISPATCH', f"Dispatch error for notice #{notice.get('id')}: {e}")
            db.mark_notice_emailed(notice['id'], 'failed')

    db.log_event('SUCCESS', 'DISPATCH', f'Manual pending dispatch complete: {sent_count}/{total} notices sent.')
    return jsonify({
        'success': True,
        'message': f'Delivered {sent_count}/{total} pending notice(s) to students / Google Group.',
        'sent_count': sent_count,
        'total': total
    })

@app.route('/api/notices/<notice_id>/mark-pending', methods=['POST'])
def api_mark_notice_pending(notice_id):
    """Marks a specific notice as pending dispatch so it will be delivered."""
    notice = db.get_notice_by_id(notice_id)
    if not notice:
        return jsonify({'success': False, 'message': 'Notice not found'}), 404
    db.mark_notice_emailed(notice_id, 'pending')
    # Trigger background worker to deliver it
    trigger_pending_mail_dispatch_async(f"NOTICE_{notice_id}_QUEUED")
    return jsonify({'success': True, 'message': f'Notice #{notice_id} queued for delivery!'})

def check_sync_auth():
    """
    Validates sync token if configured in environment (SYNC_TOKEN or CRON_SECRET).
    Supports 'X-Sync-Token', 'X-Cron-Key', 'Authorization: Bearer <token>', or '?token=' / '?key=' query param.
    Uses timing-safe constant-time string comparison.
    """
    import hmac
    expected_token = (os.getenv('SYNC_TOKEN') or os.getenv('CRON_SECRET') or '').strip()
    if not expected_token:
        # Permit sync if no token configured
        return True

    provided = (
        request.headers.get('X-Sync-Token') or 
        request.headers.get('X-Cron-Key') or 
        request.args.get('token') or 
        request.args.get('key') or 
        (request.headers.get('Authorization', '').startswith('Bearer ') and request.headers.get('Authorization', '')[7:].strip()) or
        ''
    ).strip()

    if not provided:
        return False

    try:
        return hmac.compare_digest(provided, expected_token)
    except Exception:
        return False

@app.route('/api/cron/trigger', methods=['GET', 'POST'])
def api_cron_trigger():
    """
    Webhook trigger endpoint for external cron services (cron-job.org, UptimeRobot, etc.)
    or GitHub Actions.
    Validates optional SYNC_TOKEN / CRON_SECRET if configured.
    """
    if not check_sync_auth():
        return jsonify({'success': False, 'error': 'Unauthorized: Invalid cron key or sync token'}), 401

    db.log_event('INFO', 'WEBHOOK', 'External precision cron webhook triggered notice scan.')
    res = scraper.run_notice_check()

    # Also dispatch any pending unmailed notices
    unmailed = db.get_unmailed_notices(limit=50)
    dispatched_count = 0
    if unmailed:
        importlib.reload(email_dispatcher)
        for notice in unmailed:
            m_res = email_dispatcher.dispatch_notice_to_students(notice)
            db.mark_notice_emailed(notice['id'], 'sent' if m_res.get('success') else 'failed')
            if m_res.get('success'):
                dispatched_count += 1

    return jsonify({
        'success': True,
        'result': res,
        'unmailed_dispatched': dispatched_count,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/health', methods=['GET', 'HEAD'])
@app.route('/health', methods=['GET', 'HEAD'])
@app.route('/ping', methods=['GET', 'HEAD'])
def api_health():
    """
    Ultra-lightweight keep-alive ping endpoint to wake sleeping cloud containers (e.g. Render/Railway).
    Supports GET and HEAD methods. Returns minimal plain-text (2 bytes 'OK') to prevent cron-job.org
    'output too large' limits.
    Immediately checks and delivers any pending unmailed notices whenever pinged.
    """
    try:
        trigger_pending_mail_dispatch_async("HEALTH_PING")
    except Exception:
        pass

    if request.method == 'HEAD':
        return Response('', status=200, mimetype='text/plain')

    if 'application/json' in request.headers.get('Accept', ''):
        return jsonify({'status': 'ok'}), 200

    return Response('OK', status=200, mimetype='text/plain')

# ----------------- Cloud / GitHub Actions Sync API ----------------- #

@app.route('/api/sync/status', methods=['GET'])
def api_sync_status():
    """
    Returns seen notice IDs and unmailed notices to GitHub Actions runner.
    """
    if not check_sync_auth():
        return jsonify({'success': False, 'error': 'Unauthorized: Invalid SYNC_TOKEN'}), 401

    seen_ids = db.get_all_notice_ids()
    unmailed = db.get_unmailed_notices(limit=100)
    db.log_event('INFO', 'SYNC', f'Sync status queried: {len(seen_ids)} tracked IDs, {len(unmailed)} unmailed notices.')
    return jsonify({
        'success': True,
        'seen_ids': seen_ids,
        'unmailed_notices': unmailed,
        'unmailed_count': len(unmailed),
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/sync/push-notices', methods=['POST'])
def api_sync_push_notices():
    """
    Receives newly discovered notices and their Gemini polish from GitHub Actions.
    Upserts into the web app database so the dashboard updates instantly.
    """
    if not check_sync_auth():
        return jsonify({'success': False, 'error': 'Unauthorized: Invalid SYNC_TOKEN'}), 401

    data = request.get_json() or {}
    notices = data.get('notices', [])
    if not isinstance(notices, list):
        return jsonify({'success': False, 'error': 'Invalid payload format: notices must be an array'}), 400

    saved_count = 0
    for n in notices:
        if db.upsert_notice(n):
            saved_count += 1

    db.log_event('SUCCESS', 'SYNC', f'GitHub Actions pushed {saved_count} new/updated notices with Gemini breakdowns to database.')
    return jsonify({
        'success': True,
        'saved_count': saved_count,
        'message': f'Synced {saved_count} notice(s) to web app database.'
    })

@app.route('/api/sync/mark-sent', methods=['POST'])
def api_sync_mark_sent():
    """
    Marks notices as emailed and records dispatch events after GitHub Actions completes sending emails.
    """
    if not check_sync_auth():
        return jsonify({'success': False, 'error': 'Unauthorized: Invalid SYNC_TOKEN'}), 401

    data = request.get_json() or {}
    sent_notices = data.get('sent_notices', [])
    if not isinstance(sent_notices, list):
        return jsonify({'success': False, 'error': 'Invalid payload: sent_notices must be an array'}), 400

    updated_count = 0
    for item in sent_notices:
        notice_id = str(item.get('id', '')).strip()
        if not notice_id:
            continue
        status = item.get('status', 'sent')
        title = item.get('title', f'Notice #{notice_id}')
        recipient = item.get('recipient', 'Google Group')
        error = item.get('error', '')
        sent_count = int(item.get('sent_count', 1 if status == 'sent' else 0))

        db.mark_notice_emailed(notice_id, status=status)
        if status == 'sent':
            db.add_dispatch_record(notice_id, title, sent_count, 'SUCCESS', f'Delivered via GitHub Actions: {recipient}')
            db.log_event('SUCCESS', 'DISPATCH', f'Notice #{notice_id} marked as sent via GitHub Actions to {recipient}.')
        else:
            db.add_dispatch_record(notice_id, title, 0, 'FAILED', f'GitHub Actions dispatch failure: {error}')
            db.log_event('WARNING', 'DISPATCH', f'Notice #{notice_id} dispatch failed in GitHub Actions: {error}')
        updated_count += 1

    return jsonify({
        'success': True,
        'updated_count': updated_count,
        'message': f'Updated status for {updated_count} notice(s).'
    })

@app.route('/api/notices/<notice_id>/resend', methods=['POST'])
def api_resend_notice(notice_id):
    notice = db.get_notice_by_id(notice_id)
    if not notice:
        return jsonify({'success': False, 'error': 'Notice not found in database'}), 404
    
    importlib.reload(email_dispatcher)
    res = email_dispatcher.dispatch_notice_to_students(notice)
    db.mark_notice_emailed(notice_id, 'sent' if res.get('success') else 'failed')
    return jsonify(res)

@app.route('/api/notices/recent-md', methods=['GET'])
def api_recent_md():
    """
    Returns the most recent notice that has .md and/or Gemini AI content.
    If none processed yet, processes the latest notice on the fly.
    """
    import gemini_polisher
    notice = db.get_recent_ai_notice()
    if not notice:
        notices = db.get_notices(limit=1)
        notice = notices[0] if notices else None

    if not notice:
        return jsonify({'success': False, 'message': 'No notices found'})

    if not notice.get('raw_markdown') or not notice.get('polished_markdown'):
        gemini_polisher.process_notice_complete(notice)
        notice = db.get_notice_by_id(notice['id'])

    att_path = notice.get('attachment_path', '')
    att_name = os.path.basename(att_path) if att_path and os.path.exists(att_path) else None

    return jsonify({
        'success': True,
        'notice': notice,
        'attachment_name': att_name,
        'attachment_url': f"/notices-files/{att_name}" if att_name else None
    })

@app.route('/api/notices/<notice_id>/ai-content', methods=['GET'])
def api_notice_ai_content(notice_id):
    """
    Returns the markdown and Gemini AI content for a specific notice.
    Generates on the fly if not already generated.
    """
    import gemini_polisher
    notice = db.get_notice_by_id(notice_id)
    if not notice:
        return jsonify({'success': False, 'message': 'Notice not found in database'}), 404

    if not notice.get('raw_markdown') or not notice.get('polished_markdown'):
        gemini_polisher.process_notice_complete(notice)
        notice = db.get_notice_by_id(notice_id)

    att_path = notice.get('attachment_path', '')
    att_name = os.path.basename(att_path) if att_path and os.path.exists(att_path) else None

    return jsonify({
        'success': True,
        'notice': notice,
        'attachment_name': att_name,
        'attachment_url': f"/notices-files/{att_name}" if att_name else None
    })

@app.route('/api/notices/<notice_id>/generate-polish', methods=['POST'])
def api_generate_polish(notice_id):
    """
    Forces fresh extraction and Gemini AI polishing for a specific notice.
    """
    import gemini_polisher
    notice = db.get_notice_by_id(notice_id)
    if not notice:
        return jsonify({'success': False, 'message': 'Notice not found'}), 404

    gemini_polisher.process_notice_complete(notice, force_ai=True)
    updated = db.get_notice_by_id(notice_id)
    att_path = updated.get('attachment_path', '')
    att_name = os.path.basename(att_path) if att_path and os.path.exists(att_path) else None

    return jsonify({
        'success': True,
        'notice': updated,
        'attachment_name': att_name,
        'attachment_url': f"/notices-files/{att_name}" if att_name else None
    })

@app.route('/notices-files/<path:filename>')
def serve_notice_file(filename):
    import gemini_polisher
    from flask import send_from_directory
    return send_from_directory(gemini_polisher.NOTICES_FILES_DIR, filename)

@app.route('/notices-md/<path:filename>')
def serve_notice_md(filename):
    import gemini_polisher
    from flask import send_from_directory
    return send_from_directory(gemini_polisher.NOTICES_MD_DIR, filename)

# ----------------- SMTP Server & Settings API ----------------- #

@app.route('/api/smtp/config', methods=['GET'])
def api_get_smtp_config():
    cfg = db.get_smtp_config()
    
    raw_pass = cfg.get('custom_password', '')
    raw_gemini = cfg.get('gemini_api_key', '')
    
    has_custom_password = bool(raw_pass)
    has_gemini_key = bool(raw_gemini)
    
    cfg['has_custom_password'] = has_custom_password
    cfg['has_gemini_key'] = has_gemini_key
    cfg['custom_password_masked'] = '••••••••••••••••' if has_custom_password else ''
    cfg['gemini_api_key_masked'] = security.mask_credential(raw_gemini, 4, 4) if has_gemini_key else ''

    # CRITICAL SECURITY RULE: Never expose raw credentials in JSON response
    cfg.pop('custom_password', None)
    cfg.pop('gemini_api_key', None)
    
    return jsonify(cfg)

@app.route('/api/smtp/config', methods=['POST'])
def api_save_smtp_config():
    data = request.get_json() or {}
    existing = db.get_smtp_config()
    
    # Retain existing password if user sends masked or blank
    if data.get('custom_password') in ['••••••••', '••••••••••••••••'] or not data.get('custom_password'):
        data['custom_password'] = existing.get('custom_password', '')
    
    # Retain existing gemini key if user sends masked or blank
    if '••••' in str(data.get('gemini_api_key', '')) or not data.get('gemini_api_key'):
        data['gemini_api_key'] = existing.get('gemini_api_key', '')
    
    data['mode'] = data.get('mode', 'googlegroup')
    data['custom_host'] = data.get('custom_host') or 'smtp.gmail.com'
    data['custom_port'] = int(data.get('custom_port') or 587)
    data['custom_use_tls'] = 1
    data['custom_use_ssl'] = 0
    if not data.get('custom_username'):
        data['custom_username'] = data.get('sender_email', '')

    db.save_smtp_config(data)

    return jsonify({'success': True, 'message': 'Google Group & dispatch settings saved successfully'})

@app.route('/api/smtp/test', methods=['POST'])
def api_test_smtp():
    data = request.get_json() or {}
    test_recipient = data.get('test_recipient', '').strip()
    importlib.reload(email_dispatcher)
    result = email_dispatcher.test_smtp_connection(test_recipient if test_recipient else None)
    return jsonify(result)

@app.route('/api/smtp/server/toggle', methods=['POST'])
def api_toggle_smtp_server():
    data = request.get_json() or {}
    action = data.get('action', 'start')
    cfg = db.get_smtp_config()
    
    if action == 'start':
        ok, msg = local_smtp_server.start_local_smtp_server(
            host=cfg.get('local_host', '127.0.0.1'),
            port=int(cfg.get('local_port', 2525))
        )
        return jsonify({'success': ok, 'message': msg})
    else:
        ok, msg = local_smtp_server.stop_local_smtp_server()
        return jsonify({'success': ok, 'message': msg})

@app.route('/api/smtp/inbox', methods=['GET'])
def api_get_inbox():
    limit = int(request.args.get('limit', 50))
    emails = db.get_inbox_emails(limit=limit)
    return jsonify({'emails': emails, 'count': len(emails)})

@app.route('/api/smtp/inbox', methods=['DELETE'])
def api_clear_inbox():
    db.clear_inbox()
    return jsonify({'success': True})

# ----------------- Logs & Dispatches API ----------------- #

@app.route('/api/logs', methods=['GET'])
def api_get_logs():
    limit = int(request.args.get('limit', 100))
    level = request.args.get('level', None)
    category = request.args.get('category', None)
    logs = db.get_logs(limit=limit, level=level, category=category)
    return jsonify({'logs': logs, 'count': len(logs)})

@app.route('/api/logs', methods=['DELETE'])
def api_clear_logs():
    db.clear_logs()
    return jsonify({'success': True})

@app.route('/api/dispatches', methods=['GET'])
def api_get_dispatches():
    limit = int(request.args.get('limit', 50))
    records = db.get_dispatch_history(limit=limit)
    return jsonify({'dispatches': records, 'count': len(records)})

# ----------------- Favicon & Error Handlers ----------------- #

@app.route('/favicon.ico')
def favicon():
    import os
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.root_path, 'static', 'images'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.errorhandler(404)
def page_not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Endpoint not found', 'path': request.path}), 404
    return render_template('404.html'), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Raiganj University SMTP Automation Dashboard running at http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)

