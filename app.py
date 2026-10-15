import os
import atexit
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, Response
import database as db
import scraper
import scheduler_engine
import local_smtp_server
from email_dispatcher import test_smtp_connection, dispatch_notice_to_students

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

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

# ----------------- Web UI Routes ----------------- #

@app.route('/')
def index():
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

    return jsonify({
        'status': 'ok',
        'server_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
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

@app.route('/api/notices/<notice_id>/resend', methods=['POST'])
def api_resend_notice(notice_id):
    notice = db.get_notice_by_id(notice_id)
    if not notice:
        return jsonify({'success': False, 'error': 'Notice not found in database'}), 404
    
    res = dispatch_notice_to_students(notice)
    db.mark_notice_emailed(notice_id, 'sent' if res.get('success') else 'failed')
    return jsonify(res)

# ----------------- SMTP Server & Settings API ----------------- #

@app.route('/api/smtp/config', methods=['GET'])
def api_get_smtp_config():
    cfg = db.get_smtp_config()
    # Mask password for security
    if cfg.get('custom_password'):
        cfg['custom_password_masked'] = '••••••••••••••••'
    if cfg.get('gemini_api_key'):
        key = cfg.get('gemini_api_key')
        cfg['gemini_api_key_masked'] = key[:4] + '••••••••' + key[-4:] if len(key) > 8 else '••••••••'
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
    result = test_smtp_connection(test_recipient if test_recipient else None)
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Raiganj University SMTP Automation Dashboard running at http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
