"""
Standalone Scheduled Task for PythonAnywhere / Cron
Run this script via PythonAnywhere 'Tasks' tab scheduled at 00:00 everyday:
    python3 /home/<your-username>/RGU-SMTP/cron_task.py
"""

import sys
import os

# Ensure project directory is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db
import scraper

def main():
    print("=" * 60)
    print("Executing Raiganj University 00:00 Daily Notice Check")
    print("=" * 60)

    db.init_db()
    result = scraper.run_notice_check()

    print(f"Status: {result.get('status')}")
    print(f"Message: {result.get('message')}")
    print(f"New Notices Found: {result.get('new_count', 0)}")
    print(f"Total Scraped: {result.get('total_scraped', 0)}")

    if result.get('new_notices'):
        print("\nDispatched Notices:")
        for n in result['new_notices']:
            print(f" - [{n.get('id')}] {n.get('title')}")

if __name__ == '__main__':
    main()
