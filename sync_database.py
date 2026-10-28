"""
Raiganj University Notice Engine - Cloud & Local Database Synchronizer
Supports seamless synchronization between Local SQLite and External Cloud PostgreSQL (Neon / Supabase / Render Postgres).
Allows local and hosted environments to share the exact same notice states (mailed, pending, polished) without discrepancy.

Usage:
  python sync_database.py --status           # Compares local and cloud databases
  python sync_database.py --push             # Pushes local notices/students to cloud PostgreSQL
  python sync_database.py --pull             # Pulls cloud notices/students to local SQLite
  python sync_database.py --bidirectional    # Merges both databases bidirectionally (Default)
  python sync_database.py --test             # Tests connectivity to external database
"""

import sys
import os
import argparse
import database as db

# Ensure project directory in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def show_status():
    info = db.get_database_info()
    print("=" * 65)
    print("   RAIGANJ UNIVERSITY NOTICE ENGINE - DATABASE SYNC STATUS")
    print("=" * 65)
    print(f"Active Primary Engine : {info.get('type')}")
    print(f"External Cloud DB     : {'YES (Configured)' if info.get('is_external') else 'NO (Local SQLite)'}")
    print(f"Database Target       : {info.get('database_url_masked') or info.get('db_path')}")
    print("-" * 65)

    # Local SQLite stats
    import sqlite3
    sq_notices = 0
    sq_mailed = 0
    sq_pending = 0
    sq_students = 0
    if os.path.exists(db.DB_PATH):
        try:
            conn = sqlite3.connect(db.DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM notices")
            sq_notices = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM notices WHERE email_status = 'sent'")
            sq_mailed = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM notices WHERE email_status != 'sent'")
            sq_pending = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM students")
            sq_students = cur.fetchone()[0]
            conn.close()
        except Exception as sq_err:
            print(f"[!] Local SQLite query note: {sq_err}")

    print(f"[Local SQLite File: {db.DB_PATH}]")
    print(f"  • Total Notices Tracked : {sq_notices}")
    print(f"  • Mailed Notices        : {sq_mailed}")
    print(f"  • Pending Unmailed      : {sq_pending}")
    print(f"  • Registered Students   : {sq_students}")

    # Cloud PostgreSQL stats if configured
    if db.is_postgres_configured():
        pg_url = db.get_database_url()
        print("-" * 65)
        print(f"[External Cloud Database: {db.mask_db_url(pg_url)}]")
        test_res = db.test_database_connection(pg_url)
        if test_res.get('success'):
            print(f"  • Connection Health     : ONLINE ({test_res.get('latency_ms')} ms)")
            try:
                import psycopg2
                import psycopg2.extras
                p_conn = psycopg2.connect(pg_url, connect_timeout=5)
                p_cur = p_conn.cursor()
                p_cur.execute("SELECT COUNT(*) FROM notices")
                p_notices = p_cur.fetchone()[0]
                p_cur.execute("SELECT COUNT(*) FROM notices WHERE email_status = 'sent'")
                p_mailed = p_cur.fetchone()[0]
                p_cur.execute("SELECT COUNT(*) FROM notices WHERE email_status != 'sent'")
                p_pending = p_cur.fetchone()[0]
                p_cur.execute("SELECT COUNT(*) FROM students")
                p_students = p_cur.fetchone()[0]
                p_conn.close()

                print(f"  • Total Notices Tracked : {p_notices}")
                print(f"  • Mailed Notices        : {p_mailed}")
                print(f"  • Pending Unmailed      : {p_pending}")
                print(f"  • Registered Students   : {p_students}")

                # Sync Diff Analysis
                diff_notices = abs(sq_notices - p_notices)
                diff_pending = abs(sq_pending - p_pending)
                if diff_notices == 0 and diff_pending == 0:
                    print("\n[+] Status: Local and Hosted databases are 100% IN SYNC!")
                else:
                    print(f"\n[*] Status: {diff_notices} notice diff / {diff_pending} pending status diff detected.")
                    print("    Run 'python sync_database.py --bidirectional' to synchronize both.")
            except Exception as pe:
                print(f"  • Cloud DB query error  : {pe}")
        else:
            print(f"  • Connection Health     : OFFLINE ({test_res.get('error')})")
    else:
        print("-" * 65)
        print("[!] No external DATABASE_URL configured.")
        print("    To sync local and hosted seamlessly, set DATABASE_URL in your .env or Render dashboard:")
        print("    DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require")
    print("=" * 65)

def main():
    parser = argparse.ArgumentParser(description="Synchronize Local SQLite with Cloud PostgreSQL")
    parser.add_argument('--status', action='store_true', help="Check database connection and compare sync diff")
    parser.add_argument('--push', action='store_true', help="Push local SQLite data to Cloud PostgreSQL")
    parser.add_argument('--pull', action='store_true', help="Pull Cloud PostgreSQL data into local SQLite")
    parser.add_argument('--bidirectional', action='store_true', help="Bidirectionally merge local and cloud databases")
    parser.add_argument('--test', action='store_true', help="Test database connection latency")
    parser.add_argument('--url', type=str, help="Specify database URL override")

    args = parser.parse_args()

    if args.url:
        os.environ['DATABASE_URL'] = args.url

    if args.test:
        res = db.test_database_connection(args.url)
        print(f"Connection Test Result: {res.get('message')}")
        return

    if args.push:
        print("\n[*] Pushing local records to Cloud PostgreSQL...")
        res = db.sync_databases('push', args.url)
        print(f"Result: {res.get('message') if res.get('success') else res.get('error')}")
        return

    if args.pull:
        print("\n[*] Pulling Cloud PostgreSQL records to local SQLite...")
        res = db.sync_databases('pull', args.url)
        print(f"Result: {res.get('message') if res.get('success') else res.get('error')}")
        return

    if args.bidirectional:
        print("\n[*] Synchronizing Local and Cloud databases bidirectionally...")
        res = db.sync_databases('bidirectional', args.url)
        print(f"Result: {res.get('message') if res.get('success') else res.get('error')}")
        return

    # Default action: show status
    show_status()

if __name__ == '__main__':
    main()
