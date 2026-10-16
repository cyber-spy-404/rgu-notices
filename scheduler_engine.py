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
    Scheduled job that runs everyday at 00:00:00 IST.
    1. Scrapes Raiganj University website
    2. Dispatches emails to students if new notices are found
    3. If not, logs status and schedules work for next 00:00:00
    """
    global _last_run_time, _last_result
    now_ist = datetime.now(KOLKATA_TZ)
    _last_run_time = now_ist.strftime('%Y-%m-%d %H:%M:%S')

    db.log_event('INFO', 'SCHEDULER', f'Daily 00:00 IST scheduled task triggered at {_last_run_time}')
    
    result = scraper.run_notice_check()
    _last_result = result
    
    next_run = get_next_run_time()
    next_str = next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else 'Tomorrow 00:00:00'
    
    if result.get('new_count', 0) > 0:
        db.log_event('SUCCESS', 'SCHEDULER', f"Completed 00:00 check: Dispatched {result['new_count']} new notice(s) to students. Next check scheduled for {next_str}.")
    else:
        db.log_event('INFO', 'SCHEDULER', f"Completed 00:00 check: No new notices found on Raiganj University website. Rescheduled for {next_str}.")
    
    return result

def get_next_run_time():
    job = scheduler.get_job('daily_rgu_check')
    if job and job.next_run_time:
        return job.next_run_time.astimezone(KOLKATA_TZ)
    # Fallback calculate next 00:00:00 IST
    now_ist = datetime.now(KOLKATA_TZ)
    today_midnight = datetime.combine(now_ist.date(), time(0, 0, 0), tzinfo=KOLKATA_TZ)
    if now_ist < today_midnight:
        return today_midnight
    else:
        return today_midnight + timedelta(days=1)

def start_scheduler():
    global scheduler
    if not scheduler.running:
        # Schedule everyday at 00:00:00 IST (midnight)
        scheduler.add_job(
            scheduled_daily_check,
            CronTrigger(hour=0, minute=0, second=0, timezone=KOLKATA_TZ),
            id='daily_rgu_check',
            name='Raiganj University Daily Notice Scan at 00:00 IST',
            misfire_grace_time=3600,
            replace_existing=True
        )
        scheduler.start()
        next_run = get_next_run_time()
        next_str = next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else '00:00:00'
        db.log_event('SUCCESS', 'SCHEDULER', f'Daily automated scheduler started. Next run at 00:00 IST ({next_str})')

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
        'cron': '00:00:00 IST Everyday',
        'last_run': _last_run_time,
        'next_run': next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else None,
        'server_time': now_ist.strftime('%Y-%m-%d %H:%M:%S'),
        'countdown_seconds': countdown_seconds,
        'last_result': _last_result
    }
