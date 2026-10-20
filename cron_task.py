"""
Raiganj University Twice-Daily (7:00 AM & 7:00 PM IST) Notice Engine & Cloud Synchronizer
Supports two operational modes:
1. Cloud Sync Mode (When WEBAPP_URL is set, e.g. in GitHub Actions runner):
   - Phase 1: Queries web app (/api/sync/status) for seen_ids & unmailed_notices.
   - Phase 2: Scrapes official university portal (https://raiganjuniversity.ac.in/Website/AllNotices).
   - Phase 3: Downloads new notices/PDFs, extracts reason & key details locally, and POSTs new notices to web app (/api/sync/push-notices).
   - Phase 4: Dispatches ALL unmailed notices (both newly found + existing unmailed) to students / Google Group.
   - Phase 5: Updates web app with sent status (/api/sync/mark-sent).

2. Standalone Local Mode (When WEBAPP_URL is not set):
   - Operates directly against local SQLite database.
"""

import sys
import os
import requests
from datetime import datetime

# Ensure project directory is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db
import scraper
import gemini_polisher
import email_dispatcher

def run_cloud_sync_workflow(webapp_url, sync_token):
    webapp_url = webapp_url.rstrip('/')
    headers = {
        'User-Agent': 'RGU-Notice-Engine/2.0 (GitHub Actions Runner)',
        'Content-Type': 'application/json'
    }
    if sync_token:
        headers['X-Sync-Token'] = sync_token

    # Phase 0: Wake up web service if sleeping (e.g. Render free tier cold start)
    print(f"\n[PHASE 0] Waking up Web Service if asleep (Render / Cloud container)...")
    try:
        wake_resp = requests.get(f"{webapp_url}/api/health", headers={'User-Agent': 'RGU-Notice-Engine/2.0'}, timeout=75)
        if wake_resp.status_code == 200:
            print(f" -> Web server is active and awake (Status: 200 OK).")
        else:
            print(f" -> Web server responded with HTTP {wake_resp.status_code}.")
    except Exception as wake_err:
        print(f" -> Wakeup ping note: {wake_err}")

    print(f"\n[PHASE 1] Checking Web App Status: {webapp_url}")
    seen_ids = set()
    unmailed_from_server = []

    try:
        status_resp = requests.get(f"{webapp_url}/api/sync/status", headers=headers, timeout=30)
        if status_resp.status_code == 200:
            status_data = status_resp.json()
            seen_ids = set(str(i) for i in status_data.get('seen_ids', []))
            unmailed_from_server = status_data.get('unmailed_notices', [])
            print(f" -> Successfully connected to PythonAnywhere.")
            print(f" -> Found {len(seen_ids)} tracked notice IDs in PythonAnywhere database.")
            print(f" -> Found {len(unmailed_from_server)} unmailed notice(s) waiting in queue.")
        else:
            print(f" [!] Warning: PythonAnywhere status query returned HTTP {status_resp.status_code}: {status_resp.text}")
    except Exception as e:
        print(f" [!] Could not connect to PythonAnywhere ({e}). Proceeding with local cache.")

    # Also check local seen_ids.txt cache if any
    if os.path.exists(db.SEEN_IDS_PATH):
        try:
            with open(db.SEEN_IDS_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        seen_ids.add(line.strip())
        except Exception:
            pass

    print(f"\n[PHASE 2] Scraping Raiganj University Portal for New Notices...")
    scraped_notices = scraper.fetch_rgu_notices()
    print(f" -> Scraped {len(scraped_notices)} total notices from official university portal.")

    # Identify brand new notices
    new_notices = []
    for n in scraped_notices:
        nid = str(n.get('id', ''))
        if nid not in seen_ids:
            new_notices.append(n)

    print(f" -> Identified {len(new_notices)} NEW notice(s) not yet present in PythonAnywhere database.")

    # Phase 3: Download & extract key details locally, then push to web app
    pushed_notices = []
    if new_notices:
        print(f"\n[PHASE 3] Extracting Key Details & Notice Reasons locally and Pushing to Web App...")
        for notice in new_notices:
            print(f" -> Processing Notice #{notice.get('id')}: {notice.get('title')[:60]}...")
            try:
                proc = gemini_polisher.process_notice_complete(notice)
                notice['raw_markdown'] = proc.get('raw_md', '')
                notice['polished_markdown'] = proc.get('polished_md', '')
                notice['polished_html'] = proc.get('polished_html', '')
                notice['has_gemini_polish'] = 1 if proc.get('has_gemini') else 0
                notice['email_status'] = 'pending'
                notice['is_new'] = 1
                pushed_notices.append(notice)
            except Exception as pe:
                print(f"    [!] Polishing note: {pe}")
                notice['email_status'] = 'pending'
                notice['is_new'] = 1
                pushed_notices.append(notice)

        # Push to PythonAnywhere
        try:
            push_resp = requests.post(
                f"{webapp_url}/api/sync/push-notices",
                headers=headers,
                json={'notices': pushed_notices},
                timeout=30
            )
            if push_resp.status_code == 200:
                print(f" -> Successfully pushed {len(pushed_notices)} notices to PythonAnywhere database!")
            else:
                print(f" [!] Push failed with HTTP {push_resp.status_code}: {push_resp.text}")
        except Exception as push_err:
            print(f" [!] Push error to PythonAnywhere: {push_err}")

        # Also save to local SQLite & seen_ids.txt for local cache
        for n in pushed_notices:
            try:
                db.upsert_notice(n)
            except Exception:
                pass
    else:
        print("\n[PHASE 3] No new notices on portal to push to PythonAnywhere.")

    # Phase 4: Mail ALL unmailed notices at this time
    # Combine newly discovered notices + previously unmailed notices from PythonAnywhere
    print(f"\n[PHASE 4] Preparing Batch Dispatch for All Unmailed Notices...")
    all_unmailed = {}
    
    # Add unmailed notices from PythonAnywhere
    for n in unmailed_from_server:
        all_unmailed[str(n.get('id'))] = n
        
    # Add new notices found today
    for n in pushed_notices:
        all_unmailed[str(n.get('id'))] = n

    force_test = os.getenv('FORCE_SEND_SAMPLE', '').strip().lower() in ['true', '1', 'yes']
    if len(all_unmailed) == 0 and force_test:
        print("\n -> [TEST MODE ACTIVATED] 'force_send_sample' is TRUE.")
        print(" -> Selecting the latest notice to perform a full live dispatch test...")
        sample_notice = None
        if scraped_notices:
            sample_notice = scraped_notices[0]
        else:
            try:
                rn_resp = requests.get(f"{webapp_url}/api/notices?limit=1", headers=headers, timeout=10)
                if rn_resp.status_code == 200:
                    r_notices = rn_resp.json().get('notices', [])
                    if r_notices:
                        sample_notice = r_notices[0]
            except Exception:
                pass
        
        if sample_notice:
            print(f" -> Selected Notice #{sample_notice.get('id')} ('{sample_notice.get('title')}') for live test email.")
            all_unmailed[str(sample_notice.get('id'))] = sample_notice

    total_to_mail = len(all_unmailed)
    print(f" -> Total notices queued for dispatch: {total_to_mail}")

    sent_records = []
    if total_to_mail > 0:
        for nid, notice in all_unmailed.items():
            print(f"\n -> Dispatching Notice #{nid}: '{notice.get('title')}'")
            try:
                res = email_dispatcher.dispatch_notice_to_students(notice)
                status = 'sent' if res.get('success') else 'failed'
                target = os.getenv('GOOGLE_GROUP_EMAIL') or 'Google Group'
                err = '; '.join(res.get('errors', [])) if res.get('errors') else res.get('message', '')
                
                sent_records.append({
                    'id': str(nid),
                    'title': notice.get('title', ''),
                    'status': status,
                    'sent_count': res.get('sent_count', 1 if status == 'sent' else 0),
                    'recipient': target,
                    'error': err
                })
                
                # Update local DB if present
                db.mark_notice_emailed(nid, status)
                print(f"    Result: {status.upper()} (Sent count: {res.get('sent_count', 0)})")
            except Exception as dispatch_err:
                print(f"    [!] Dispatch error: {dispatch_err}")
                sent_records.append({
                    'id': str(nid),
                    'title': notice.get('title', ''),
                    'status': 'failed',
                    'sent_count': 0,
                    'recipient': os.getenv('GOOGLE_GROUP_EMAIL', 'Google Group'),
                    'error': str(dispatch_err)
                })

        # Phase 5: Update PythonAnywhere with the sent status
        print(f"\n[PHASE 5] Updating PythonAnywhere with Dispatch Results...")
        try:
            mark_resp = requests.post(
                f"{webapp_url}/api/sync/mark-sent",
                headers=headers,
                json={'sent_notices': sent_records},
                timeout=25
            )
            if mark_resp.status_code == 200:
                print(f" -> Successfully synced dispatch status to PythonAnywhere!")
                print(f" -> Notices marked sent: {sum(1 for r in sent_records if r['status'] == 'sent')}/{len(sent_records)}")
            else:
                print(f" [!] Mark-sent API returned HTTP {mark_resp.status_code}: {mark_resp.text}")
        except Exception as mark_err:
            print(f" [!] Failed to notify PythonAnywhere of sent status: {mark_err}")
    else:
        print(" -> Everything is up to date! No unmailed notices waiting.")

    print("\n" + "=" * 60)
    print("Twice-Daily (7:00 AM & 7:00 PM IST) Notice Engine Workflow Completed Successfully")
    print("=" * 60)
    return {
        'mode': 'cloud_sync',
        'scraped': len(scraped_notices),
        'new_notices': len(new_notices),
        'dispatched': len(sent_records)
    }

def run_local_workflow():
    print("\n[LOCAL MODE] WEBAPP_URL not specified. Running local database check & dispatch...")
    db.init_db()
    result = scraper.run_notice_check()

    # Also check if any existing notices in local DB are still unmailed
    unmailed = db.get_unmailed_notices(limit=50)
    if unmailed:
        print(f"Found {len(unmailed)} additional pending notice(s) in local DB. Dispatching now...")
        for notice in unmailed:
            res = email_dispatcher.dispatch_notice_to_students(notice)
            db.mark_notice_emailed(notice['id'], 'sent' if res.get('success') else 'failed')

    print(f"Status: {result.get('status')}")
    print(f"Message: {result.get('message')}")
    print(f"New Notices Found: {result.get('new_count', 0)}")
    return result

def main():
    print("=" * 60)
    print(f"Raiganj University Twice-Daily Notice Engine (7:00 AM & 7:00 PM IST) [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print("=" * 60)

    db.init_db()

    webapp_url = os.getenv('WEBAPP_URL', '').strip()
    sync_token = os.getenv('SYNC_TOKEN', '').strip() or os.getenv('CRON_SECRET', '').strip()

    if webapp_url:
        run_cloud_sync_workflow(webapp_url, sync_token)
    else:
        run_local_workflow()

if __name__ == '__main__':
    main()

