import os
import sys
import webbrowser
from threading import Timer
import database as db

def main():
    print("=" * 65)
    print("   RAIGANJ UNIVERSITY AUTOMATED NOTICE & SMTP DISPATCHER")
    print("=" * 65)
    
    # Initialize SQLite Database
    db.init_db()

    # Pre-seed sample student data if empty
    students = db.get_students()
    if not students:
        print("[*] Initializing demo students list...")
        db.bulk_add_students([
            {'name': 'Souvik Mukherjee', 'email': 'souvik.rgu@example.com', 'department': 'Computer Science', 'roll_no': 'CS-2026-042'},
            {'name': 'Ananya Roy', 'email': 'ananya.roy@example.com', 'department': 'Mathematics', 'roll_no': 'MATH-2026-015'},
            {'name': 'Rohan Sen', 'email': 'rohan.sen@example.com', 'department': 'English Literature', 'roll_no': 'ENG-2026-088'},
            {'name': 'Priyanka Das', 'email': 'priyanka.das@example.com', 'department': 'Physics', 'roll_no': 'PHY-2026-023'},
            {'name': 'Debojyoti Paul', 'email': 'debojyoti.paul@example.com', 'department': 'Commerce', 'roll_no': 'COM-2026-110'}
        ])

    from app import app
    port = int(os.environ.get('PORT', 5000))

    def open_browser():
        try:
            webbrowser.open(f'http://127.0.0.1:{port}')
        except Exception:
            pass

    # Open browser automatically after 1.5 seconds
    Timer(1.5, open_browser).start()

    print(f"\n[+] Web Application: http://127.0.0.1:{port}")
    print("[+] Local SMTP Server: 127.0.0.1:2525 (Ready to capture/relay emails)")
    print("[+] Automated Scheduler: Active (Running Twice Daily at 7:00 AM & 7:00 PM IST)")
    print("[+] Notice Target: https://raiganjuniversity.ac.in/\n")
    print("Press Ctrl+C to terminate.\n")

    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    main()
