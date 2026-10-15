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
        response = requests.get(ALL_NOTICES_URL, headers=HEADERS, timeout=18)
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
                    # Parse from URL or fallback
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
        db.log_event('WARNING', 'SCRAPER', f'Failed fetching AllNotices: {str(e)}')

    # Step 2: Also scrape homepage for any marquee or new notices not yet in AllNotices
    try:
        hp_resp = requests.get(HOMEPAGE_URL, headers=HEADERS, timeout=18)
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
        db.log_event('WARNING', 'SCRAPER', f'Homepage scrape warning: {str(e)}')

    return notices

def run_notice_check(force_email=False):
    """
    Executes a notice check cycle:
    1. Scrapes notices from Raiganj University
    2. Identifies new notices
    3. If new notices found (or force_email=True), dispatches alert to all active students
    4. Logs the status and returns report
    """
    from email_dispatcher import dispatch_notice_to_students

    db.log_event('INFO', 'SCRAPER', 'Starting scheduled notice scan from https://raiganjuniversity.ac.in/')
    
    try:
        scraped_notices = fetch_rgu_notices()
        if not scraped_notices:
            msg = 'Scraper completed: 0 notices fetched from Raiganj University. Connection may be restricted or page structure changed.'
            db.log_event('WARNING', 'SCRAPER', msg)
            return {'status': 'warning', 'message': msg, 'new_count': 0, 'total': 0}

        new_notices = []
        for n in scraped_notices:
            is_new = db.save_notice(n)
            if is_new:
                new_notices.append(n)

        total_scraped = len(scraped_notices)
        new_count = len(new_notices)

        if new_count > 0:
            db.log_event('SUCCESS', 'SCRAPER', f'Found {new_count} NEW notices from Raiganj University out of {total_scraped} scanned.')
            
            # Dispatch each new notice to students
            dispatch_results = []
            for notice in new_notices:
                res = dispatch_notice_to_students(notice)
                dispatch_results.append(res)
                db.mark_notice_emailed(notice['id'], 'sent' if res.get('success') else 'failed')

            return {
                'status': 'success',
                'message': f'Discovered {new_count} new notice(s) and dispatched emails to enrolled students.',
                'new_count': new_count,
                'total_scraped': total_scraped,
                'new_notices': new_notices,
                'dispatch_results': dispatch_results
            }
        else:
            msg = f'Daily check completed at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}: No new notices found on Raiganj University website. Total tracked: {total_scraped}. Rescheduled for next 00:00.'
            db.log_event('INFO', 'SCHEDULER', msg)
            return {
                'status': 'no_new',
                'message': msg,
                'new_count': 0,
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
