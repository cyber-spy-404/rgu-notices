"""
External Database Connection & Migration Tool for Raiganj University Notice Dispatcher

Usage:
  python setup_external_db.py
  python setup_external_db.py --url="postgresql://user:pass@host:5432/dbname?sslmode=require"
  python setup_external_db.py --migrate
"""

import sys
import os
import argparse

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db

def main():
    parser = argparse.ArgumentParser(description="Initialize and migrate external PostgreSQL database for RGU Notice Engine.")
    parser.add_argument('--url', help="External database connection string (e.g. Supabase, Neon, Render PostgreSQL)")
    parser.add_argument('--migrate', action='store_true', help="Migrate existing local SQLite data into the external database")
    args = parser.parse_args()

    print("=" * 70)
    print(" [*] Raiganj University External Database Setup & Verification")
    print("=" * 70)

    target_url = args.url or os.getenv('DATABASE_URL', '').strip()

    if not target_url:
        print("\n[?] No DATABASE_URL found in environment or arguments.")
        print("    You can enter your PostgreSQL connection string now (from Supabase, Neon, Render, etc.):")
        print("    Example: postgresql://postgres.xxxx:pass@aws-0-us-east-1.pooler.supabase.com:6543/postgres")
        try:
            user_input = input("\nEnter DATABASE_URL (or press Enter to cancel): ").strip()
            if user_input:
                target_url = user_input
        except (KeyboardInterrupt, EOFError):
            print("\nSetup cancelled.")
            return

    if not target_url:
        print("\n[-] No connection string provided. The application will continue using local SQLite (data/rgu_smtp.db).")
        print("    To configure later, set DATABASE_URL in your .env file.")
        return

    # Set environment variable temporarily for this run
    os.environ['DATABASE_URL'] = target_url

    print(f"\n[1/4] Connecting to External Database: {db.get_db_engine()}...")
    try:
        conn = db.get_db()
        if not conn.is_pg:
            print("[-] Connection failed or did not resolve to PostgreSQL.")
            return
        print("  -> [OK] Successfully connected to external PostgreSQL database!")
    except Exception as e:
        print(f"[-] Connection failed: {e}")
        return

    print("\n[2/4] Initializing Database Schema (Tables, Constraints, Indexes)...")
    try:
        db.init_db()
        print("  -> [OK] Schema created successfully:")
        print("     - students (id, name, email, department, roll_no, is_active)")
        print("     - notices (id, title, link, published_on, category, status, breakdowns)")
        print("     - smtp_config (singleton SMTP & Google Group credentials)")
        print("     - logs (system audit & scraper events)")
        print("     - dispatch_history (email delivery logs)")
    except Exception as e:
        print(f"[-] Schema initialization error: {e}")
        return

    # Check if migration requested or offered
    if args.migrate or os.path.exists(db.DB_PATH):
        print("\n[3/4] Migrating Existing SQLite Data to External PostgreSQL...")
        res = db.migrate_sqlite_to_external()
        if res.get('success'):
            m = res.get('migrated', {})
            print(f"  -> [OK] Migration Complete:")
            print(f"     - Students: {m.get('students', 0)} copied")
            print(f"     - Notices: {m.get('notices', 0)} copied")
            print(f"     - Dispatch History: {m.get('dispatch', 0)} copied")
        else:
            print(f"  -> Migration skipped or note: {res.get('error')}")
    else:
        print("\n[3/4] Skipping SQLite migration (no existing local SQLite database found).")

    print("\n[4/4] Verifying Final Database Statistics...")
    try:
        stats = db.get_stats()
        print(f"  -> Total Tracked Notices: {stats['total_notices']}")
        print(f"  -> Total Enrolled Students: {stats['total_students']}")
        print(f"  -> Pending / Unmailed Notices: {stats['unmailed_notices']}")
    except Exception as e:
        print(f"[-] Stats query note: {e}")

    # Save to local .env if requested
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    try:
        existing_env = ""
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                existing_env = f.read()

        if "DATABASE_URL=" not in existing_env:
            with open(env_path, 'a', encoding='utf-8') as f:
                f.write(f"\n# External Database Connection\nDATABASE_URL={target_url}\n")
            print(f"\n[+] Added DATABASE_URL to local .env file.")
        else:
            # Update existing DATABASE_URL line
            import re
            updated_env = re.sub(r'DATABASE_URL=.*', f'DATABASE_URL={target_url}', existing_env)
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(updated_env)
            print(f"\n[+] Updated DATABASE_URL in local .env file.")
    except Exception as env_err:
        print(f"[!] Could not update .env: {env_err}")

    print("\n" + "=" * 70)
    print(" [OK] External Database Initialization Complete!")
    print("=" * 70)
    print("\nNext Steps for GitHub Actions Automation:")
    print("1. Go to your GitHub Repository -> Settings -> Secrets and variables -> Actions")
    print("2. Under 'Repository secrets', add:")
    print(f"   - DATABASE_URL = {target_url[:25]}... (your full connection string)")
    print("   - SMTP_USER = your-gmail@gmail.com")
    print("   - SMTP_PASS = your-16-char-app-password")
    print("   - GOOGLE_GROUP_EMAIL = your-group@googlegroups.com")
    print("3. In your GitHub Actions tab, trigger 'Raiganj University Notice Scraper & Mail Dispatcher'!")
    print("=" * 70)

if __name__ == '__main__':
    main()

