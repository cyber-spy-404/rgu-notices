import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'rgu_smtp.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    # Students table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        department TEXT DEFAULT 'General',
        roll_no TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Notices table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notices (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        link TEXT NOT NULL,
        published_on TEXT,
        category TEXT DEFAULT 'General',
        is_new INTEGER DEFAULT 1,
        discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        emailed_at TIMESTAMP,
        email_status TEXT DEFAULT 'pending'
    )
    ''')

    # SMTP configuration table (singleton row id=1)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS smtp_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        mode TEXT DEFAULT 'local',
        local_host TEXT DEFAULT '127.0.0.1',
        local_port INTEGER DEFAULT 2525,
        custom_host TEXT DEFAULT 'smtp.gmail.com',
        custom_port INTEGER DEFAULT 587,
        custom_use_tls INTEGER DEFAULT 1,
        custom_use_ssl INTEGER DEFAULT 0,
        custom_username TEXT DEFAULT '',
        custom_password TEXT DEFAULT '',
        sender_email TEXT DEFAULT 'notices@raiganjuniversity.ac.in',
        sender_name TEXT DEFAULT 'Raiganj University Notice Board',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Insert default smtp config if not exists
    cursor.execute('''
    INSERT OR IGNORE INTO smtp_config (id, mode, local_host, local_port, custom_host, custom_port, custom_use_tls, custom_use_ssl, custom_username, custom_password, sender_email, sender_name)
    VALUES (1, 'googlegroup', '127.0.0.1', 2525, 'smtp.gmail.com', 587, 1, 0, '', '', 'notices@raiganjuniversity.ac.in', 'Raiganj University Notice Board')
    ''')

    # Migration: Add google_group_email and gemini_api_key if not exists
    try:
        cursor.execute("ALTER TABLE smtp_config ADD COLUMN google_group_email TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE smtp_config ADD COLUMN gemini_api_key TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    # Migration: Add AI and markdown columns to notices table
    for col, col_type in [
        ('raw_markdown', "TEXT DEFAULT ''"),
        ('polished_markdown', "TEXT DEFAULT ''"),
        ('polished_html', "TEXT DEFAULT ''"),
        ('attachment_path', "TEXT DEFAULT ''"),
        ('has_gemini_polish', "INTEGER DEFAULT 0")
    ]:
        try:
            cursor.execute(f"ALTER TABLE notices ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    # Local SMTP inbox to inspect captured emails
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS smtp_inbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        recipients TEXT,
        subject TEXT,
        body_text TEXT,
        body_html TEXT,
        received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # System activity logs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT DEFAULT 'INFO',
        category TEXT DEFAULT 'SYSTEM',
        message TEXT NOT NULL,
        details TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Dispatch history
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS dispatch_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        notice_id TEXT,
        notice_title TEXT,
        recipient_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'SUCCESS',
        error_message TEXT DEFAULT '',
        dispatched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    conn.commit()
    conn.close()

# ----------------- Students Operations ----------------- #

def add_student(name, email, department='General', roll_no='', is_active=1):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        INSERT INTO students (name, email, department, roll_no, is_active)
        VALUES (?, ?, ?, ?, ?)
        ''', (name.strip(), email.strip().lower(), department.strip(), roll_no.strip(), int(is_active)))
        conn.commit()
        student_id = cursor.lastrowid
        log_event('SUCCESS', 'STUDENTS', f'Added student: {name.strip()} ({email.strip().lower()})')
        return {'success': True, 'id': student_id}
    except sqlite3.IntegrityError:
        return {'success': False, 'error': f'Student with email {email} already exists'}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()

def bulk_add_students(students_list):
    """students_list: list of dicts [{'name': ..., 'email': ..., 'department': ..., 'roll_no': ...}]"""
    conn = get_db()
    cursor = conn.cursor()
    added = 0
    skipped = 0
    errors = []

    for item in students_list:
        name = item.get('name', '').strip() or 'Student'
        email = item.get('email', '').strip().lower()
        dept = item.get('department', 'General').strip() or 'General'
        roll = item.get('roll_no', '').strip()

        if not email or '@' not in email:
            skipped += 1
            continue

        try:
            cursor.execute('''
            INSERT INTO students (name, email, department, roll_no, is_active)
            VALUES (?, ?, ?, ?, 1)
            ''', (name, email, dept, roll))
            added += 1
        except sqlite3.IntegrityError:
            skipped += 1
        except Exception as e:
            errors.append(f'{email}: {str(e)}')

    conn.commit()
    conn.close()
    log_event('INFO', 'STUDENTS', f'Bulk import: {added} added, {skipped} duplicate/invalid skipped')
    return {'success': True, 'added': added, 'skipped': skipped, 'errors': errors}

def get_students(search='', active_only=False):
    conn = get_db()
    cursor = conn.cursor()
    query = 'SELECT * FROM students WHERE 1=1'
    params = []

    if active_only:
        query += ' AND is_active = 1'

    if search:
        search_param = f'%{search}%'
        query += ' AND (name LIKE ? OR email LIKE ? OR department LIKE ? OR roll_no LIKE ?)'
        params.extend([search_param, search_param, search_param, search_param])

    query += ' ORDER BY id DESC'
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def delete_student(student_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM students WHERE id = ?', (student_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    if deleted:
        log_event('INFO', 'STUDENTS', f'Deleted student ID: {student_id}')
    return deleted

def toggle_student_status(student_id, is_active):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE students SET is_active = ? WHERE id = ?', (int(is_active), student_id))
    conn.commit()
    conn.close()
    return True

# ----------------- Notices Operations ----------------- #

def get_notices(limit=100, search=''):
    conn = get_db()
    cursor = conn.cursor()
    query = 'SELECT * FROM notices WHERE 1=1'
    params = []

    if search:
        search_param = f'%{search}%'
        query += ' AND (title LIKE ? OR id LIKE ? OR category LIKE ?)'
        params.extend([search_param, search_param, search_param])

    query += ' ORDER BY discovered_at DESC, id DESC LIMIT ?'
    params.append(limit)
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_notice_by_id(notice_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM notices WHERE id = ?', (str(notice_id),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def save_notice(notice_dict):
    """
    Returns (saved_notice, is_new_entry)
    """
    conn = get_db()
    cursor = conn.cursor()
    notice_id = str(notice_dict['id'])

    cursor.execute('SELECT id, email_status FROM notices WHERE id = ?', (notice_id,))
    existing = cursor.fetchone()

    if existing:
        # Already exists
        conn.close()
        return False

    cursor.execute('''
    INSERT INTO notices (id, title, link, published_on, category, is_new, email_status)
    VALUES (?, ?, ?, ?, ?, 1, 'pending')
    ''', (
        notice_id,
        notice_dict.get('title', '').strip(),
        notice_dict.get('link', '').strip(),
        notice_dict.get('published_on', ''),
        notice_dict.get('category', 'General'),
    ))
    conn.commit()
    conn.close()
    return True

def mark_notice_emailed(notice_id, status='sent'):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE notices 
    SET emailed_at = CURRENT_TIMESTAMP, email_status = ?, is_new = 0 
    WHERE id = ?
    ''', (status, str(notice_id)))
    conn.commit()
    conn.close()

def update_notice_ai(notice_id, raw_md='', polished_md='', polished_html='', attachment_path='', has_gemini=0):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE notices 
    SET raw_markdown = ?,
        polished_markdown = ?,
        polished_html = ?,
        attachment_path = ?,
        has_gemini_polish = ?
    WHERE id = ?
    ''', (raw_md, polished_md, polished_html, attachment_path, int(has_gemini), str(notice_id)))
    conn.commit()
    conn.close()
    return True

def get_recent_ai_notice():
    """Returns the most recent notice with markdown/AI content, or the latest notice."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM notices 
    ORDER BY CASE WHEN (raw_markdown IS NOT NULL AND raw_markdown != '') OR (polished_markdown IS NOT NULL AND polished_markdown != '') THEN 0 ELSE 1 END,
             discovered_at DESC, id DESC
    LIMIT 1
    ''')
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# ----------------- SMTP Config ----------------- #

def get_smtp_config():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM smtp_config WHERE id = 1')
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {}

def save_smtp_config(data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE smtp_config
    SET mode = ?,
        local_host = ?,
        local_port = ?,
        custom_host = ?,
        custom_port = ?,
        custom_use_tls = ?,
        custom_use_ssl = ?,
        custom_username = ?,
        custom_password = ?,
        sender_email = ?,
        sender_name = ?,
        google_group_email = ?,
        gemini_api_key = ?,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = 1
    ''', (
        data.get('mode', 'googlegroup'),
        data.get('local_host', '127.0.0.1'),
        int(data.get('local_port', 2525)),
        data.get('custom_host', 'smtp.gmail.com'),
        int(data.get('custom_port', 587)),
        1 if data.get('custom_use_tls') else 0,
        1 if data.get('custom_use_ssl') else 0,
        data.get('custom_username', ''),
        data.get('custom_password', ''),
        data.get('sender_email', ''),
        data.get('sender_name', 'Raiganj University Notice Board'),
        data.get('google_group_email', ''),
        data.get('gemini_api_key', '')
    ))
    conn.commit()
    conn.close()
    log_event('SUCCESS', 'SMTP', 'Dispatch settings updated successfully')
    return True

# ----------------- Local SMTP Inbox ----------------- #

def add_inbox_email(sender, recipients, subject, body_text, body_html):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO smtp_inbox (sender, recipients, subject, body_text, body_html)
    VALUES (?, ?, ?, ?, ?)
    ''', (
        str(sender),
        isinstance(recipients, list) and ', '.join(recipients) or str(recipients),
        str(subject),
        str(body_text),
        str(body_html)
    ))
    conn.commit()
    msg_id = cursor.lastrowid
    conn.close()
    return msg_id

def get_inbox_emails(limit=50):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM smtp_inbox ORDER BY received_at DESC, id DESC LIMIT ?', (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def clear_inbox():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM smtp_inbox')
    conn.commit()
    conn.close()
    log_event('INFO', 'SMTP', 'Local SMTP inbox cleared')
    return True

# ----------------- Logs & Audit ----------------- #

def log_event(level, category, message, details=''):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO logs (level, category, message, details)
        VALUES (?, ?, ?, ?)
        ''', (str(level).upper(), str(category).upper(), str(message), str(details)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'Logging error: {e}')

def get_logs(limit=100, level=None, category=None):
    conn = get_db()
    cursor = conn.cursor()
    query = 'SELECT * FROM logs WHERE 1=1'
    params = []

    if level and level != 'ALL':
        query += ' AND level = ?'
        params.append(level.upper())

    if category and category != 'ALL':
        query += ' AND category = ?'
        params.append(category.upper())

    query += ' ORDER BY created_at DESC, id DESC LIMIT ?'
    params.append(limit)
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def clear_logs():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM logs')
    conn.commit()
    conn.close()
    return True

# ----------------- Dispatch History ----------------- #

def add_dispatch_record(notice_id, notice_title, recipient_count, status='SUCCESS', error_message=''):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO dispatch_history (notice_id, notice_title, recipient_count, status, error_message)
    VALUES (?, ?, ?, ?, ?)
    ''', (str(notice_id), str(notice_title), int(recipient_count), str(status), str(error_message)))
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()
    return record_id

def get_dispatch_history(limit=50):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM dispatch_history ORDER BY dispatched_at DESC, id DESC LIMIT ?', (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# ----------------- Overall Stats ----------------- #

def get_stats():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM students')
    total_students = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM students WHERE is_active = 1')
    active_students = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM notices')
    total_notices = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM notices WHERE DATE(discovered_at) = DATE('now')")
    new_notices_today = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM smtp_inbox')
    captured_emails = cursor.fetchone()[0]

    cursor.execute("SELECT MAX(created_at) FROM logs WHERE category = 'SCRAPER'")
    last_scrape_row = cursor.fetchone()
    last_scraped_at = last_scrape_row[0] if last_scrape_row and last_scrape_row[0] else None

    conn.close()
    return {
        'total_students': total_students,
        'active_students': active_students,
        'total_notices': total_notices,
        'new_notices_today': new_notices_today,
        'captured_emails': captured_emails,
        'last_scraped_at': last_scraped_at
    }

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
