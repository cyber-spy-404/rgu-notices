import zoneinfo
from datetime import datetime, time, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import database as db
import scraper

KOLKATA_TZ = zoneinfo.ZoneInfo('Asia/Kolkata')
scheduler = BackgroundScheduler(timezone=KOLKATA_TZ)
_last_run_time = None
_last_result = None

def scheduled_daily_check():
    """
    Scheduled job that runs twice a day at 7:00:00 AM IST and 7:00:00 PM IST.
    1. Scrapes Raiganj University website
    2. Checks if notices exist and are polished
    3. If not, polishes with Gemini (or fallback), adds to database, and mails instantly
    """
    global _last_run_time, _last_result
    now_ist = datetime.now(KOLKATA_TZ)
    _last_run_time = now_ist.strftime('%Y-%m-%d %H:%M:%S')

    db.log_event('INFO', 'SCHEDULER', f'Twice-daily check (7:00 AM / 7:00 PM IST) triggered at {_last_run_time}')
    
    result = scraper.run_notice_check()
    _last_result = result
    
    next_run = get_next_run_time()
    next_str = next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else 'Next check at 7:00 AM/PM IST'
    
    if result.get('new_count', 0) > 0 or result.get('dispatch_count', 0) > 0:
        db.log_event('SUCCESS', 'SCHEDULER', f"Completed scheduled check: Dispatched {result.get('sent_ok', 0)} notice(s) to students. Next check scheduled for {next_str}.")
    else:
        db.log_event('INFO', 'SCHEDULER', f"Completed scheduled check: All notices up to date. Next check scheduled for {next_str}.")
    
    return result

def get_next_run_time():
    job = scheduler.get_job('daily_rgu_check')
    if job and job.next_run_time:
        return job.next_run_time.astimezone(KOLKATA_TZ)
    # Calculate next scheduled check: 7:00 AM today, 7:00 PM today, or 7:00 AM tomorrow
    now_ist = datetime.now(KOLKATA_TZ)
    candidates = [
        datetime.combine(now_ist.date(), time(7, 0, 0), tzinfo=KOLKATA_TZ),
        datetime.combine(now_ist.date(), time(19, 0, 0), tzinfo=KOLKATA_TZ),
        datetime.combine(now_ist.date() + timedelta(days=1), time(7, 0, 0), tzinfo=KOLKATA_TZ),
    ]
    for c in candidates:
        if c > now_ist:
            return c
    return candidates[-1]

def check_pending_notices_queue():
    """Periodically checks and delivers any unmailed/pending notices."""
    try:
        unmailed = db.get_unmailed_notices(limit=50)
        if not unmailed:
            return

        import email_dispatcher
        can_connect, reason = email_dispatcher.check_smtp_availability()
        if not can_connect and ('101' in reason or 'unreachable' in reason.lower() or 'blocked' in reason.lower() or 'denied' in reason.lower() or 'error code' in reason.lower()):
            return

        db.log_event('INFO', 'SCHEDULER', f'Queue watcher detected {len(unmailed)} unmailed notice(s). Checking polish and starting instant delivery...')
        import gemini_polisher
        import time
        for notice in unmailed:
            try:
                # Ensure notice is polished before mailing
                if not notice.get('polished_markdown') and not notice.get('has_gemini_polish'):
                    gemini_polisher.process_notice_complete(notice)
                res = email_dispatcher.dispatch_notice_to_students(notice)
                if res.get('success'):
                    db.mark_notice_emailed(notice['id'], 'sent')
                elif res.get('is_cloud_blocked'):
                    pass
                else:
                    db.mark_notice_emailed(notice['id'], 'failed')
                time.sleep(1.2)
            except Exception as e:
                db.log_event('ERROR', 'DISPATCH', f"Queue delivery error on notice #{notice.get('id')}: {e}")
                db.mark_notice_emailed(notice['id'], 'failed')
    except Exception as err:
        print(f"Pending queue interval error: {err}")

def start_scheduler():
    global scheduler
    if not scheduler.running:
        # Schedule twice a day at 7:00:00 AM and 7:00:00 PM (19:00:00) IST
        scheduler.add_job(
            scheduled_daily_check,
            CronTrigger(hour='7,19', minute=0, second=0, timezone=KOLKATA_TZ),
            id='daily_rgu_check',
            name='Raiganj University Twice-Daily Notice Scan at 7:00 AM & 7:00 PM IST',
            misfire_grace_time=3600,
            replace_existing=True
        )
        # Periodically deliver any pending notices every 15 minutes
        scheduler.add_job(
            check_pending_notices_queue,
            'interval',
            minutes=15,
            id='pending_queue_watcher',
            name='Raiganj University Pending Notice Delivery Watcher',
            replace_existing=True
        )
        scheduler.start()
        next_run = get_next_run_time()
        next_str = next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else '7:00 AM/PM IST'
        db.log_event('SUCCESS', 'SCHEDULER', f'Automated scheduler started. Twice-daily checks active (7:00 AM & 7:00 PM IST). Next run at {next_str}')

def get_scheduler_status():
    global _last_run_time, _last_result
    next_run = get_next_run_time()
    now_ist = datetime.now(KOLKATA_TZ)
    
    countdown_seconds = 0
    if next_run:
        try:
            if hasattr(next_run, 'tzinfo') and next_run.tzinfo is not None:
                diff = next_run.astimezone(KOLKATA_TZ) - now_ist
            else:
                next_aware = next_run.replace(tzinfo=KOLKATA_TZ)
                diff = next_aware - now_ist
            countdown_seconds = max(0, int(diff.total_seconds()))
        except Exception:
            countdown_seconds = 0

    return {
        'running': scheduler.running if scheduler else False,
        'cron': 'Twice Daily at 7:00 AM & 7:00 PM IST',
        'last_run': _last_run_time,
        'next_run': next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else None,
        'server_time': now_ist.strftime('%Y-%m-%d %H:%M:%S'),
        'countdown_seconds': countdown_seconds,
        'last_result': _last_result
    }
