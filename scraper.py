import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
import database as db

BASE_URL = 'https://raiganjuniversity.ac.in/'
ALL_NOTICES_URL = 'https://raiganjuniversity.ac.in/Website/AllNotices'
HOMEPAGE_URL = 'https://raiganjuniversity.ac.in/'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9'
}

def detect_category(title):
    t = title.lower()
    if any(k in t for k in ['admission', 'mop-up', 'counseling', 'verification']):
        return 'Admission'
    if any(k in t for k in ['exam', 'sem', 'theoretical', 'schedule', 'programme', 'reassessment', 'scrutiny']):
        return 'Examination'
    if any(k in t for k in ['holiday', 'closed', 'puja', 'vacation']):
        return 'Holiday'
    if any(k in t for k in ['ph.d', 'viva', 'viva-voce', 'research', 'thesis']):
        return 'Research & PhD'
    if any(k in t for k in ['tender', 'niq', 'niet', 'quotation', 'contract', 'supply']):
        return 'Tender / NIQ'
    if any(k in t for k in ['recruit', 'roster', 'employment', 'assistant', 'post']):
        return 'Recruitment'
    if any(k in t for k in ['seminar', 'conference', 'workshop', 'webinar', 'essay']):
        return 'Academic / Events'
    return 'General'

def fetch_rgu_notices():
    """
    Scrapes Raiganj University official website for the latest notices.
    Returns list of dicts: [{'id': ..., 'title': ..., 'link': ..., 'published_on': ..., 'category': ...}]
    """
    notices = []
    seen_ids = set()

    # Step 1: Scrape AllNotices page
    try:
        response = requests.get(ALL_NOTICES_URL, headers=HEADERS, timeout=4)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.select('.notice-item')
            
            for item in items:
                a_tag = item.find('a', href=lambda h: h and 'ViewNotice' in h)
                if not a_tag:
                    continue
                
                title = a_tag.get_text(strip=True)
                href = a_tag['href']
                full_link = urljoin(BASE_URL, href)

                # Extract Notice ID / Ref No
                badge = item.find('span', class_='badge')
                if badge and badge.get_text(strip=True):
                    notice_id = badge.get_text(strip=True)
                else:
                    match = re.search(r'ViewNotice/([0-9A-Za-z_-]+)', href)
                    if match:
                        notice_id = match.group(1)
                    else:
                        notice_id = str(abs(hash(full_link)))[:10]

                if notice_id in seen_ids:
                    continue
                seen_ids.add(notice_id)

                # Extract Published Date
                item_text = item.get_text(' ', strip=True)
                date_match = re.search(r'Published\s+On:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4}|\d{2}[-/]\d{2}[-/]\d{4})', item_text, re.IGNORECASE)
                published_on = date_match.group(1) if date_match else datetime.now().strftime('%b %d, %Y')

                category = detect_category(title)
                is_new_badge = 'new-notice' in item.get('class', []) or 'new' in item_text.lower()

                notices.append({
                    'id': notice_id,
                    'title': title,
                    'link': full_link,
                    'published_on': published_on,
                    'category': category,
                    'is_new': is_new_badge
                })
    except Exception as e:
        db.log_event('INFO', 'SCRAPER', f'Portal scrape note (cloud network): {str(e)[:100]}')

    # Step 2: Also scrape homepage for any marquee or new notices not yet in AllNotices
    try:
        hp_resp = requests.get(HOMEPAGE_URL, headers=HEADERS, timeout=4)
        if hp_resp.status_code == 200:
            hp_soup = BeautifulSoup(hp_resp.text, 'html.parser')
            hp_links = hp_soup.find_all('a', href=lambda h: h and ('ViewNotice' in h or 'notice' in h.lower()))
            
            for a in hp_links:
                href = a.get('href', '')
                title = a.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                # Filter out generic navigation links
                if title.lower() in ['view all notices', 'all notices', 'more notices', 'view all', 'notices']:
                    continue
                if 'allnotices' in href.lower():
                    continue
                
                # Check for refno in query or path
                ref_match = re.search(r'refno=([0-9A-Za-z]+)', href) or re.search(r'ViewNotice/([0-9A-Za-z]+)', href)
                notice_id = ref_match.group(1) if ref_match else str(abs(hash(title)))[:10]
                
                if notice_id in seen_ids:
                    continue
                seen_ids.add(notice_id)
                
                full_link = urljoin(BASE_URL, href)
                notices.append({
                    'id': notice_id,
                    'title': title,
                    'link': full_link,
                    'published_on': datetime.now().strftime('%b %d, %Y'),
                    'category': detect_category(title),
                    'is_new': True
                })
    except Exception as e:
        db.log_event('INFO', 'SCRAPER', f'Homepage scrape note: {str(e)[:100]}')

    return notices

def run_notice_check(force_email=False):
    """
    Executes scheduled notice check cycle (runs strictly twice a day at 7:00 AM & 7:00 PM IST):
    1. Scrapes notices from Raiganj University official portal
    2. Checks if each notice already exists in database and is polished
    3. If not polished, polishes notice (via Gemini Multimodal or direct link fallback)
    4. Saves/updates in database and mails instantly to Google Group / active students
    5. Also ensures any existing unmailed notices in database are polished and mailed instantly
    """
    from email_dispatcher import dispatch_notice_to_students
    import gemini_polisher
    import time

    db.log_event('INFO', 'SCRAPER', 'Starting scheduled notice check cycle (7:00 AM / 7:00 PM IST)...')
    
    try:
        scraped_notices = fetch_rgu_notices() or []
        total_scraped = len(scraped_notices)
        
        dispatched_results = []
        newly_handled_count = 0
        
        # 1. First process all scraped notices
        for n in scraped_notices:
            nid = str(n.get('id', ''))
            if not nid:
                continue
            
            existing = db.get_notice_by_id(nid)
            is_polished = bool(existing and (existing.get('polished_markdown') or existing.get('has_gemini_polish') == 1))
            is_mailed = bool(existing and existing.get('email_status') == 'sent')
            
            # If notice already exists, is already polished, and already mailed: skip
            if existing and is_polished and is_mailed:
                continue
            
            # If not in DB, add to DB
            if not existing:
                db.save_notice(n)
                existing = db.get_notice_by_id(nid)
            
            # If not polished, polish now (Gemini or direct link fallback)
            if not is_polished:
                db.log_event('INFO', 'AI', f"Notice #{nid} not yet polished. Processing with AI / direct portal link fallback...")
                proc = gemini_polisher.process_notice_complete(n)
                n['polished_markdown'] = proc.get('polished_md', '')
                n['polished_html'] = proc.get('polished_html', '')
                n['has_gemini_polish'] = 1 if proc.get('has_gemini') else 0
            else:
                n['polished_markdown'] = existing.get('polished_markdown', '')
                n['polished_html'] = existing.get('polished_html', '')
                n['has_gemini_polish'] = existing.get('has_gemini_polish', 0)
                n['attachment_path'] = existing.get('attachment_path', '')

            # Mail instantly
            db.log_event('INFO', 'DISPATCH', f"Instantly mailing Notice #{nid} ('{n.get('title')[:60]}')...")
            try:
                res = dispatch_notice_to_students(n)
                dispatched_results.append(res)
                status = 'sent' if res.get('success') else 'failed'
                db.mark_notice_emailed(nid, status)
                newly_handled_count += 1
                time.sleep(1.2)  # respectful SMTP pacing
            except Exception as de:
                db.log_event('ERROR', 'DISPATCH', f"Instant dispatch failed for notice #{nid}: {de}")
                db.mark_notice_emailed(nid, 'failed')

        # 2. Check for any remaining unmailed notices in database
        unmailed_in_db = db.get_unmailed_notices(limit=50)
        for notice in unmailed_in_db:
            nid = str(notice.get('id', ''))
            # Skip if already dispatched in this run
            if nid in [str(x.get('id')) for x in scraped_notices]:
                continue
            
            # Check if polished, if not polish
            if not notice.get('polished_markdown') and not notice.get('has_gemini_polish'):
                db.log_event('INFO', 'AI', f"Unmailed notice #{nid} missing polish. Polishing now...")
                proc = gemini_polisher.process_notice_complete(notice)
                notice['polished_markdown'] = proc.get('polished_md', '')
                notice['polished_html'] = proc.get('polished_html', '')
            
            # Mail instantly
            db.log_event('INFO', 'DISPATCH', f"Instantly mailing pending notice #{nid} ('{notice.get('title')[:60]}')...")
            try:
                res = dispatch_notice_to_students(notice)
                dispatched_results.append(res)
                status = 'sent' if res.get('success') else 'failed'
                db.mark_notice_emailed(nid, status)
                newly_handled_count += 1
                time.sleep(1.2)
            except Exception as de:
                db.log_event('ERROR', 'DISPATCH', f"Failed delivering pending notice #{nid}: {de}")
                db.mark_notice_emailed(nid, 'failed')

        sent_ok = sum(1 for r in dispatched_results if r.get('success'))
        dispatch_count = len(dispatched_results)
        
        if dispatch_count > 0:
            msg = f"Check cycle complete: Polished and instantly mailed {sent_ok}/{dispatch_count} notice(s)."
            db.log_event('SUCCESS', 'SCRAPER', msg)
            return {
                'status': 'success',
                'message': msg,
                'new_count': newly_handled_count,
                'dispatch_count': dispatch_count,
                'sent_ok': sent_ok,
                'total_scraped': total_scraped,
                'dispatch_results': dispatched_results
            }
        else:
            msg = f'Scheduled check completed at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}: All notices are already polished and mailed. Next check scheduled for 7:00 AM/PM IST.'
            db.log_event('INFO', 'SCHEDULER', msg)
            return {
                'status': 'no_new',
                'message': msg,
                'new_count': 0,
                'dispatch_count': 0,
                'total_scraped': total_scraped,
                'new_notices': []
            }

    except Exception as e:
        err_msg = f'Error during notice scan: {str(e)}'
        db.log_event('ERROR', 'SCRAPER', err_msg)
        return {'status': 'error', 'message': err_msg, 'new_count': 0, 'total_scraped': 0}

if __name__ == '__main__':
    db.init_db()
    results = fetch_rgu_notices()
    print(f'Fetched {len(results)} notices.')
    for n in results[:3]:
        print(n)
