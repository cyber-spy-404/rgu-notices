import sqlite3
import os
import json
import re
from datetime import datetime

DATA_DIR = os.getenv('DATA_DIR') or os.path.join(os.path.dirname(__file__), 'data')
DB_PATH = os.path.join(DATA_DIR, 'rgu_smtp.db')
SEEN_IDS_PATH = os.path.join(DATA_DIR, 'seen_ids.txt')

# ----------------- External Database Configuration & Adapters ----------------- #

def is_postgres_configured():
    """
    Checks if an external PostgreSQL database (Supabase, Neon, Render Postgres, etc.)
    is configured in the environment.
    """
    db_url = os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL') or os.getenv('EXTERNAL_DB_URL') or ''
    db_url = db_url.strip().strip('"\'')
    return bool(db_url and ('postgres' in db_url or 'psql' in db_url))

def get_database_url():
    """
    Returns sanitized PostgreSQL URL, converting postgres:// to postgresql:// if needed.
    """
    db_url = os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL') or os.getenv('EXTERNAL_DB_URL') or ''
    db_url = db_url.strip().strip('"\'')
    if db_url.startswith('postgres://'):
        db_url = 'postgresql://' + db_url[len('postgres://'):]
    return db_url

def mask_db_url(url):
    """
    Safely masks database credentials for display in logs and UI status.
    """
    if not url:
        return 'Local SQLite (Standalone)'
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        netloc = p.netloc
        if '@' in netloc:
            creds, hostport = netloc.split('@', 1)
            user = creds.split(':')[0]
            masked_netloc = f"{user}:••••@{hostport}"
        else:
            masked_netloc = netloc
        return f"{p.scheme}://{masked_netloc}{p.path}"
    except Exception:
        return 'Cloud PostgreSQL (Active)'

class PostgresCursorWrapper:
    """
    Wraps psycopg2 cursor to provide uniform parameter translation (? -> %s),
    ANSI SQL syntax compatibility, and dict-like row access matching sqlite3.Row.
    """
    def __init__(self, pg_cursor):
        self._cur = pg_cursor

    def execute(self, query, params=None):
        # 1. Translate ? parameter placeholder to %s
        pg_query = query.replace('?', '%s')
        
        # 2. Translate SQLite DATE('now') to CURRENT_DATE
        if "DATE('now')" in pg_query:
            pg_query = pg_query.replace("DATE('now')", "CURRENT_DATE")

        # 3. Skip SQLite PRAGMA commands
        if pg_query.strip().upper().startswith('PRAGMA'):
            return self

        if params is None:
            self._cur.execute(pg_query)
        else:
            self._cur.execute(pg_query, tuple(params) if isinstance(params, (list, tuple)) else params)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        try:
            return getattr(self._cur, 'lastrowid', None)
        except Exception:
            return None

    @property
    def description(self):
        return self._cur.description

    def close(self):
        return self._cur.close()

class SQLiteCursorWrapper:
    """
    Wraps standard sqlite3 cursor with uniform execution and error handling.
    """
    def __init__(self, sq_cursor):
        self._cur = sq_cursor

    def execute(self, query, params=None):
        if params is None:
            self._cur.execute(query)
        else:
            self._cur.execute(query, tuple(params) if isinstance(params, (list, tuple)) else params)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def description(self):
        return self._cur.description

    def close(self):
        return self._cur.close()

class DBConnectionWrapper:
    """
    Universal database connection wrapper supporting both SQLite and PostgreSQL.
    """
    def __init__(self, raw_conn, is_postgres=False):
        self._conn = raw_conn
        self.is_postgres = is_postgres
        self.row_factory = None

    def cursor(self):
        if self.is_postgres:
            import psycopg2.extras
            return PostgresCursorWrapper(self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor))
        return SQLiteCursorWrapper(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def execute(self, query, params=None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

def get_db():
    """
    Acquires an active database connection.
    If DATABASE_URL or POSTGRES_URL is configured, connects directly to external PostgreSQL.
    Otherwise, seamlessly connects to local SQLite database.
    """
    if is_postgres_configured():
        try:
            import psycopg2
            import psycopg2.extras
            pg_url = get_database_url()
            conn = psycopg2.connect(pg_url, connect_timeout=10)
            return DBConnectionWrapper(conn, is_postgres=True)
        except Exception as pge:
            print(f"[!] External PostgreSQL connection note: {pge}. Using local SQLite fallback.")

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return DBConnectionWrapper(conn, is_postgres=False)

def init_db():
    """
    Initializes tables and schema across whichever database engine is currently active.
    If external PostgreSQL is connected for the first time, automatically migrates
    all notices, students, and settings from local SQLite to external PostgreSQL.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()
    is_pg = conn.is_postgres

    auto_id = 'SERIAL PRIMARY KEY' if is_pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'

    if not is_pg:
        # Enable WAL mode and normal synchronous for high SQLite concurrency
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass

    # 1. Students table
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS students (
        id {auto_id},
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        department TEXT DEFAULT 'General',
        roll_no TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 2. Notices table
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
        email_status TEXT DEFAULT 'pending',
        raw_markdown TEXT DEFAULT '',
        polished_markdown TEXT DEFAULT '',
        polished_html TEXT DEFAULT '',
        attachment_path TEXT DEFAULT '',
        has_gemini_polish INTEGER DEFAULT 0
    )
    ''')

    # 3. SMTP configuration table (singleton row id=1)
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
        google_group_email TEXT DEFAULT '',
        gemini_api_key TEXT DEFAULT '',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Insert default smtp config if not exists
    cursor.execute('''
    INSERT INTO smtp_config (id, mode, local_host, local_port, custom_host, custom_port, custom_use_tls, custom_use_ssl, custom_username, custom_password, sender_email, sender_name, google_group_email, gemini_api_key)
    VALUES (1, 'googlegroup', '127.0.0.1', 2525, 'smtp.gmail.com', 587, 1, 0, '', '', 'notices@raiganjuniversity.ac.in', 'Raiganj University Notice Board', '', '')
    ON CONFLICT (id) DO NOTHING
    ''')

    # Migration: Ensure columns exist if working on older SQLite DB
    if not is_pg:
        for col, col_type in [
            ('google_group_email', "TEXT DEFAULT ''"),
            ('gemini_api_key', "TEXT DEFAULT ''")
        ]:
            try:
                cursor.execute(f"ALTER TABLE smtp_config ADD COLUMN {col} {col_type}")
            except Exception:
                pass

        for col, col_type in [
            ('raw_markdown', "TEXT DEFAULT ''"),
            ('polished_markdown', "TEXT DEFAULT ''"),
            ('polished_html', "TEXT DEFAULT ''"),
            ('attachment_path', "TEXT DEFAULT ''"),
            ('has_gemini_polish', "INTEGER DEFAULT 0")
        ]:
            try:
                cursor.execute(f"ALTER TABLE notices ADD COLUMN {col} {col_type}")
            except Exception:
                pass

    # 4. Local SMTP inbox to inspect captured emails
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS smtp_inbox (
        id {auto_id},
        sender TEXT,
        recipients TEXT,
        subject TEXT,
        body_text TEXT,
        body_html TEXT,
        received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 5. System activity logs
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS logs (
        id {auto_id},
        level TEXT DEFAULT 'INFO',
        category TEXT DEFAULT 'SYSTEM',
        message TEXT NOT NULL,
        details TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 6. Dispatch history
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS dispatch_history (
        id {auto_id},
        notice_id TEXT,
        notice_title TEXT,
        recipient_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'SUCCESS',
        error_message TEXT DEFAULT '',
        dispatched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    conn.commit()

    # Automatic initial population:
    # If the active DB (Postgres or SQLite) has 0 notices, populate from local SQLite or notices_seed.json
    cursor.execute('SELECT COUNT(*) FROM notices')
    cnt_row = cursor.fetchone()
    notice_count = cnt_row[0] if cnt_row else 0

    if notice_count == 0:
        # Check if local SQLite exists and has notices to migrate to external PostgreSQL
        migrated_from_sqlite = False
        if is_pg and os.path.exists(DB_PATH):
            try:
                sq_conn = sqlite3.connect(DB_PATH)
                sq_conn.row_factory = sqlite3.Row
                sq_cur = sq_conn.cursor()
                sq_cur.execute('SELECT * FROM notices')
                sq_notices = sq_cur.fetchall()
                if sq_notices:
                    for ln in sq_notices:
                        keys = ln.keys()
                        cursor.execute('''
                        INSERT INTO notices (id, title, link, published_on, category, is_new, email_status, emailed_at, raw_markdown, polished_markdown, polished_html, has_gemini_polish)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (id) DO NOTHING
                        ''', (
                            str(ln['id']), ln['title'], ln['link'], ln['published_on'], ln['category'],
                            ln['is_new'], ln['email_status'], ln['emailed_at'],
                            ln['raw_markdown'] if 'raw_markdown' in keys else '',
                            ln['polished_markdown'] if 'polished_markdown' in keys else '',
                            ln['polished_html'] if 'polished_html' in keys else '',
                            ln['has_gemini_polish'] if 'has_gemini_polish' in keys else 0
                        ))
                    conn.commit()
                    migrated_from_sqlite = True
                    log_event('SUCCESS', 'MIGRATION', f"Seamless initial migration: Copied {len(sq_notices)} notice(s) from local SQLite into external Cloud PostgreSQL.")
                sq_conn.close()
            except Exception as me:
                print(f"Initial migration note: {me}")

        if not migrated_from_sqlite:
            # Seed full notices metadata from notices_seed.json
            NOTICES_SEED_PATH = os.path.join(DATA_DIR, 'notices_seed.json')
            if os.path.exists(NOTICES_SEED_PATH):
                try:
                    with open(NOTICES_SEED_PATH, 'r', encoding='utf-8') as f:
                        seed_data = json.load(f)
                        for item in seed_data:
                            cursor.execute('''
                            INSERT INTO notices (id, title, link, published_on, category, is_new, email_status, emailed_at)
                            VALUES (?, ?, ?, ?, ?, 0, 'sent', CURRENT_TIMESTAMP)
                            ON CONFLICT(id) DO UPDATE SET
                                title = excluded.title,
                                link = excluded.link,
                                published_on = excluded.published_on,
                                category = excluded.category
                            ''', (
                                str(item.get('id')),
                                item.get('title'),
                                item.get('link'),
                                item.get('published_on'),
                                item.get('category', 'General')
                            ))
                    conn.commit()
                except Exception as se:
                    print(f"Seed notices note: {se}")
            elif os.path.exists(SEEN_IDS_PATH):
                try:
                    with open(SEEN_IDS_PATH, 'r', encoding='utf-8') as f:
                        for line in f:
                            nid = line.strip()
                            if nid:
                                cursor.execute('''
                                INSERT INTO notices (id, title, link, published_on, category, is_new, email_status, emailed_at)
                                VALUES (?, ?, 'https://raiganjuniversity.ac.in/Website/ViewNotice/' || ?, '', 'General', 0, 'sent', CURRENT_TIMESTAMP)
                                ON CONFLICT (id) DO NOTHING
                                ''', (nid, f"Notice #{nid}", nid))
                    conn.commit()
                except Exception as e:
                    print(f"Warning: seen_ids sync note: {e}")

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
    except Exception as e:
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() or 'integrity' in str(e).lower():
            return {'success': False, 'error': f'Student with email {email} already exists'}
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
        except Exception as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() or 'integrity' in str(e).lower():
                skipped += 1
            else:
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

    new_title = (notice_dict.get('title') or '').strip()
    new_link = (notice_dict.get('link') or '').strip()
    new_pub = (notice_dict.get('published_on') or '').strip()
    new_cat = (notice_dict.get('category') or '').strip()

    if existing:
        updates = []
        params = []
        if new_title:
            updates.append("title = ?")
            params.append(new_title)
        if new_link:
            updates.append("link = ?")
            params.append(new_link)
        if new_pub:
            updates.append("published_on = ?")
            params.append(new_pub)
        if new_cat:
            updates.append("category = ?")
            params.append(new_cat)

        if updates:
            params.append(str(notice_id))
            cursor.execute(f"UPDATE notices SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

        conn.close()
        return False

    cursor.execute('''
    INSERT INTO notices (id, title, link, published_on, category, is_new, email_status)
    VALUES (?, ?, ?, ?, ?, 1, 'pending')
    ''', (
        notice_id,
        new_title or f"Notice #{notice_id}",
        new_link or f"https://raiganjuniversity.ac.in/Website/ViewNotice/{notice_id}",
        new_pub,
        new_cat or 'General',
    ))
    conn.commit()
    conn.close()

    # Append to public seen_ids.txt cache (non-sensitive)
    try:
        os.makedirs(os.path.dirname(SEEN_IDS_PATH), exist_ok=True)
        already_present = False
        if os.path.exists(SEEN_IDS_PATH):
            with open(SEEN_IDS_PATH, 'r', encoding='utf-8') as f:
                if notice_id in [l.strip() for l in f if l.strip()]:
                    already_present = True
        if not already_present:
            with open(SEEN_IDS_PATH, 'a', encoding='utf-8') as f:
                f.write(f"{notice_id}\n")
    except Exception:
        pass

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

def get_unmailed_notices(limit=50):
    """Returns any notices in database that have not yet been successfully delivered."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM notices 
    WHERE email_status != 'sent'
    ORDER BY id DESC LIMIT ?
    ''', (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_all_notice_ids():
    """Returns list of all notice IDs present in the database."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM notices')
    rows = [str(r[0]) for r in cursor.fetchall()]
    conn.close()
    return rows

def upsert_notice(n):
    """
    Inserts or updates a notice in database (used for sync from GitHub Actions to Web App / Render).
    """
    conn = get_db()
    cursor = conn.cursor()
    notice_id = str(n.get('id', '')).strip()
    if not notice_id:
        conn.close()
        return False

    try:
        cursor.execute('''
        INSERT INTO notices (id, title, link, published_on, category, is_new, email_status, raw_markdown, polished_markdown, polished_html, has_gemini_polish)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            link = excluded.link,
            published_on = excluded.published_on,
            category = excluded.category,
            email_status = excluded.email_status,
            raw_markdown = CASE WHEN excluded.raw_markdown != '' THEN excluded.raw_markdown ELSE notices.raw_markdown END,
            polished_markdown = CASE WHEN excluded.polished_markdown != '' THEN excluded.polished_markdown ELSE notices.polished_markdown END,
            polished_html = CASE WHEN excluded.polished_html != '' THEN excluded.polished_html ELSE notices.polished_html END,
            has_gemini_polish = CASE WHEN excluded.has_gemini_polish = 1 THEN 1 ELSE notices.has_gemini_polish END
        ''', (
            notice_id,
            n.get('title', '').strip(),
            n.get('link', '').strip(),
            n.get('published_on', ''),
            n.get('category', 'General'),
            int(n.get('is_new', 0)),
            n.get('email_status', 'pending'),
            n.get('raw_markdown', ''),
            n.get('polished_markdown', ''),
            n.get('polished_html', ''),
            int(n.get('has_gemini_polish', 0))
        ))
        conn.commit()
    except Exception as e:
        log_event('ERROR', 'DB', f"Failed to upsert notice #{notice_id}: {e}")
        conn.close()
        return False
    finally:
        conn.close()

    # Append to seen_ids cache
    try:
        os.makedirs(os.path.dirname(SEEN_IDS_PATH), exist_ok=True)
        already_present = False
        if os.path.exists(SEEN_IDS_PATH):
            with open(SEEN_IDS_PATH, 'r', encoding='utf-8') as f:
                if notice_id in [l.strip() for l in f if l.strip()]:
                    already_present = True
        if not already_present:
            with open(SEEN_IDS_PATH, 'a', encoding='utf-8') as f:
                f.write(f"{notice_id}\n")
    except Exception:
        pass

    return True

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
    cfg = dict(row) if row else {}

    import security
    if cfg.get('custom_password'):
        cfg['custom_password'] = security.decrypt_credential(cfg['custom_password'])
    if cfg.get('gemini_api_key'):
        cfg['gemini_api_key'] = security.decrypt_credential(cfg['gemini_api_key'])

    # Merge any environment variables from .env
    env_group = os.getenv('GOOGLE_GROUP_EMAIL')
    if env_group:
        cfg['google_group_email'] = env_group
    
    env_sender = os.getenv('SENDER_EMAIL') or os.getenv('SMTP_USER')
    if env_sender:
        cfg['sender_email'] = env_sender
        cfg['custom_username'] = env_sender
        
    env_pass = os.getenv('SMTP_PASS') or os.getenv('SMTP_PASSWORD')
    if env_pass:
        cfg['custom_password'] = env_pass
        
    env_gemini = os.getenv('GEMINI_API_KEY')
    if env_gemini:
        cfg['gemini_api_key'] = env_gemini

    return cfg

def save_smtp_config(data):
    import security
    conn = get_db()
    cursor = conn.cursor()

    raw_pass = (data.get('custom_password') or '').strip()
    raw_gemini = (data.get('gemini_api_key') or '').strip()

    enc_pass = security.encrypt_credential(raw_pass) if raw_pass else ''
    enc_gemini = security.encrypt_credential(raw_gemini) if raw_gemini else ''

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
        enc_pass,
        data.get('sender_email', ''),
        data.get('sender_name', 'Raiganj University Notice Board'),
        data.get('google_group_email', ''),
        enc_gemini
    ))
    conn.commit()
    conn.close()

    # Automatically sync to local .env file
    try:
        sync_payload = dict(data)
        sync_payload['custom_password'] = raw_pass
        sync_payload['gemini_api_key'] = raw_gemini
        security.sync_all_to_env(sync_payload)
    except Exception as env_err:
        print(f"Warning: .env sync notice: {env_err}")

    log_event('SUCCESS', 'SMTP', 'Dispatch settings updated successfully (encrypted at rest & synced to .env)')
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

    cursor.execute("SELECT COUNT(*) FROM notices WHERE DATE(discovered_at) = CURRENT_DATE")
    new_notices_today = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM smtp_inbox')
    captured_emails = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM notices WHERE email_status != 'sent'")
    unmailed_notices = cursor.fetchone()[0]

    cursor.execute("SELECT MAX(created_at) FROM logs WHERE category = 'SCRAPER'")
    last_scrape_row = cursor.fetchone()
    last_scraped_at = last_scrape_row[0] if last_scrape_row and last_scrape_row[0] else None

    conn.close()
    return {
        'total_students': total_students,
        'active_students': active_students,
        'total_notices': total_notices,
        'new_notices_today': new_notices_today,
        'pending_notices': unmailed_notices,
        'unmailed_notices': unmailed_notices,
        'captured_emails': captured_emails,
        'last_scraped_at': last_scraped_at
    }

# ----------------- External Database Management & Sync ----------------- #

def get_database_info():
    is_pg = is_postgres_configured()
    url = get_database_url() if is_pg else None
    return {
        'type': 'PostgreSQL' if is_pg else 'SQLite',
        'is_external': is_pg,
        'database_url_masked': mask_db_url(url),
        'db_path': DB_PATH if not is_pg else None
    }

def test_database_connection(url=None):
    target_url = (url or get_database_url() or '').strip()
    if not target_url:
        return {'success': True, 'type': 'SQLite', 'message': 'Local SQLite database active and healthy.'}
    try:
        import time
        import psycopg2
        start = time.time()
        conn = psycopg2.connect(target_url, connect_timeout=5)
        cur = conn.cursor()
        cur.execute('SELECT 1;')
        cur.close()
        conn.close()
        latency_ms = round((time.time() - start) * 1000, 1)
        return {
            'success': True,
            'type': 'PostgreSQL',
            'latency_ms': latency_ms,
            'message': f"Connected successfully to Cloud PostgreSQL ({latency_ms} ms latency)."
        }
    except Exception as e:
        return {
            'success': False,
            'type': 'PostgreSQL',
            'error': str(e),
            'message': f"Could not connect to database: {str(e)}"
        }

def sync_databases(mode='bidirectional', target_pg_url=None):
    """
    Seamless synchronization between Local SQLite and External Cloud PostgreSQL:
    - 'push': pushes all local notices, students, and settings to Cloud PostgreSQL
    - 'pull': pulls all cloud notices, students, and settings to local SQLite
    - 'bidirectional': merges both, ensuring mailed notices in either are marked sent in both
    """
    pg_url = target_pg_url or get_database_url()
    if not pg_url:
        return {'success': False, 'error': 'No external DATABASE_URL configured'}

    import psycopg2
    import psycopg2.extras

    try:
        pg_conn = psycopg2.connect(pg_url, connect_timeout=10)
        pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        sq_conn = sqlite3.connect(DB_PATH)
        sq_conn.row_factory = sqlite3.Row
        sq_cur = sq_conn.cursor()

        notices_synced = 0
        students_synced = 0

        # --- Sync Notices ---
        if mode in ('push', 'bidirectional'):
            sq_cur.execute('SELECT * FROM notices')
            for row in sq_cur.fetchall():
                keys = row.keys()
                pg_cur.execute('''
                INSERT INTO notices (id, title, link, published_on, category, is_new, email_status, emailed_at, raw_markdown, polished_markdown, polished_html, has_gemini_polish)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    email_status = CASE WHEN excluded.email_status = 'sent' THEN 'sent' ELSE notices.email_status END,
                    emailed_at = CASE WHEN excluded.email_status = 'sent' THEN COALESCE(excluded.emailed_at, CURRENT_TIMESTAMP) ELSE notices.emailed_at END,
                    polished_markdown = CASE WHEN excluded.polished_markdown != '' THEN excluded.polished_markdown ELSE notices.polished_markdown END,
                    polished_html = CASE WHEN excluded.polished_html != '' THEN excluded.polished_html ELSE notices.polished_html END,
                    has_gemini_polish = CASE WHEN excluded.has_gemini_polish = 1 THEN 1 ELSE notices.has_gemini_polish END
                ''', (
                    str(row['id']), row['title'], row['link'], row['published_on'], row['category'],
                    row['is_new'], row['email_status'], row['emailed_at'],
                    row['raw_markdown'] if 'raw_markdown' in keys else '',
                    row['polished_markdown'] if 'polished_markdown' in keys else '',
                    row['polished_html'] if 'polished_html' in keys else '',
                    row['has_gemini_polish'] if 'has_gemini_polish' in keys else 0
                ))
                notices_synced += 1

        if mode in ('pull', 'bidirectional'):
            pg_cur.execute('SELECT * FROM notices')
            for row in pg_cur.fetchall():
                keys = row.keys()
                sq_cur.execute('''
                INSERT INTO notices (id, title, link, published_on, category, is_new, email_status, emailed_at, raw_markdown, polished_markdown, polished_html, has_gemini_polish)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    email_status = CASE WHEN excluded.email_status = 'sent' THEN 'sent' ELSE notices.email_status END,
                    emailed_at = CASE WHEN excluded.email_status = 'sent' THEN COALESCE(excluded.emailed_at, CURRENT_TIMESTAMP) ELSE notices.emailed_at END,
                    polished_markdown = CASE WHEN excluded.polished_markdown != '' THEN excluded.polished_markdown ELSE notices.polished_markdown END,
                    polished_html = CASE WHEN excluded.polished_html != '' THEN excluded.polished_html ELSE notices.polished_html END,
                    has_gemini_polish = CASE WHEN excluded.has_gemini_polish = 1 THEN 1 ELSE notices.has_gemini_polish END
                ''', (
                    str(row['id']), row['title'], row['link'], row['published_on'], row['category'],
                    row['is_new'], row['email_status'], row['emailed_at'],
                    row['raw_markdown'] if 'raw_markdown' in keys else '',
                    row['polished_markdown'] if 'polished_markdown' in keys else '',
                    row['polished_html'] if 'polished_html' in keys else '',
                    row['has_gemini_polish'] if 'has_gemini_polish' in keys else 0
                ))
                notices_synced += 1

        # --- Sync Students ---
        if mode in ('push', 'bidirectional'):
            sq_cur.execute('SELECT * FROM students')
            for s in sq_cur.fetchall():
                pg_cur.execute('''
                INSERT INTO students (name, email, department, roll_no, is_active)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                ''', (s['name'], s['email'], s['department'], s['roll_no'], s['is_active']))
                students_synced += 1

        if mode in ('pull', 'bidirectional'):
            pg_cur.execute('SELECT * FROM students')
            for s in pg_cur.fetchall():
                sq_cur.execute('''
                INSERT INTO students (name, email, department, roll_no, is_active)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (email) DO NOTHING
                ''', (s['name'], s['email'], s['department'], s['roll_no'], s['is_active']))
                students_synced += 1

        pg_conn.commit()
        sq_conn.commit()
        pg_conn.close()
        sq_conn.close()

        msg = f"Database sync ({mode}) completed successfully: {notices_synced} notice record(s), {students_synced} student(s) synchronized."
        log_event('SUCCESS', 'SYNC', msg)
        return {'success': True, 'mode': mode, 'notices_synced': notices_synced, 'students_synced': students_synced, 'message': msg}
    except Exception as e:
        err = f"Database sync failed: {str(e)}"
        log_event('ERROR', 'SYNC', err)
        return {'success': False, 'error': err}

if __name__ == '__main__':
    init_db()
    info = get_database_info()
    print(f"Active Database Engine: {info.get('type')}")
    print(f"Database Target: {info.get('database_url_masked') or info.get('db_path')}")
    print("Database initialized successfully.")
