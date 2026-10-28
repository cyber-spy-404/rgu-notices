import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
import database as db

BASE_URL = 'https://raiganjuniversity.ac.in/'
ALL_NOTICES_URL = 'https://raiganjuniversity.ac.in/Website/AllNotices'
HOMEPAGE_URL = 'https://raiganjuniversity.ac.in/'

# Resilient timeouts for slow university server: (connect_timeout, read_timeout)
REQUEST_TIMEOUT = (12, 30)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://raiganjuniversity.ac.in/',
    'Connection': 'keep-alive'
}

# Module-level tracking for diagnostic reporting
LAST_SCRAPE_DIAGNOSTICS = {
    'attempted_at': None,
    'portal_reachable': False,
    'portal_status_code': None,
    'portal_error': None,
    'homepage_reachable': False,
    'homepage_error': None,
    'total_found': 0
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

def extract_notice_id(href, badge_text, full_link, title):
    """
    Reliably extracts notice reference ID.
    Prioritizes URL query/path patterns over generic badge text (e.g. 'NEW').
    """
    if href:
        # Check path parameter: ViewNotice/79 or ViewNoticeFileByRef/123
        m = re.search(r'(?:ViewNotice|ViewNoticeFileByRef)/([0-9A-Za-z_-]+)', href, re.IGNORECASE)
        if m and m.group(1).lower() not in ['viewnotice', 'file', 'index', 'view']:
            return m.group(1).strip()
        
        # Check query parameter: fileRefId=2026101337 or refno=79 or id=79
        m = re.search(r'(?:fileRefId|refno|notice_id|id)=([0-9A-Za-z_-]+)', href, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    # Check badge text if present and numeric/reference-like (exclude generic keywords like 'NEW')
    if badge_text:
        clean = badge_text.strip()
        ignore_words = {'new', 'hot', 'notice', 'notices', 'download', 'pdf', 'click', 'view', 'alert', 'latest'}
        if clean.lower() not in ignore_words and len(clean) <= 30:
            if re.search(r'\d', clean):
                return clean

    # Deterministic fallback based on link or title
    val = full_link or title or str(time.time())
    return str(abs(hash(val)))[:10]

def get_request_target_and_proxies(url):
    """
    Resolves request target URL and proxy dictionary if cloud proxy / scraping API is configured.
    Supports SCRAPERAPI_KEY, SCRAPEOPS_API_KEY, or SCRAPER_PROXY / PROXY_URL.
    """
    scraperapi_key = (os.getenv('SCRAPERAPI_KEY') or os.getenv('SCRAPER_API_KEY') or '').strip()
    scrapeops_key = (os.getenv('SCRAPEOPS_API_KEY') or os.getenv('SCRAPEOPS_KEY') or '').strip()
    proxy_url = os.getenv('SCRAPER_PROXY', '').strip() or os.getenv('PROXY_URL', '').strip()

    if scraperapi_key:
        from urllib.parse import quote
        target = f"http://api.scraperapi.com?api_key={scraperapi_key}&url={quote(url, safe='')}&country_code=in"
        return target, None
    elif scrapeops_key:
        from urllib.parse import quote
        target = f"https://proxy.scrapeops.io/v1/?api_key={scrapeops_key}&url={quote(url, safe='')}&country=in"
        return target, None
    elif proxy_url:
        return url, {'http': proxy_url, 'https': proxy_url}
    
    return url, None

def fetch_page_with_retry(url, retries=2, timeout=REQUEST_TIMEOUT):
    """
    Fetches a web page with retries and resilient timeouts for university servers.
    Supports optional Indian residential / cloud proxy (SCRAPERAPI_KEY, SCRAPEOPS_API_KEY, SCRAPER_PROXY).
    Returns (response_or_None, error_string_or_None)
    """
    target_url, proxies = get_request_target_and_proxies(url)
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(target_url, headers=HEADERS, proxies=proxies, timeout=timeout)
            if resp.status_code == 200:
                return resp, None
            else:
                last_err = f"HTTP {resp.status_code}"
        except requests.exceptions.ConnectTimeout:
            last_err = f"Connection timed out (after {timeout[0]}s)"
        except requests.exceptions.ReadTimeout:
            last_err = f"Read timed out (after {timeout[1]}s)"
        except requests.exceptions.SSLError as ssl_err:
            last_err = f"SSL handshake failed: {ssl_err}"
        except Exception as e:
            last_err = str(e)
        
        if attempt < retries:
            time.sleep(2)
            
    return None, last_err

def fetch_rgu_notices():
    """
    Scrapes Raiganj University official website for the latest notices.
    Uses multi-selector parsing (notice-item, table rows, lists, anchors).
    Returns list of dicts: [{'id': ..., 'title': ..., 'link': ..., 'published_on': ..., 'category': ...}]
    """
    global LAST_SCRAPE_DIAGNOSTICS
    notices = []
    seen_ids = set()

    LAST_SCRAPE_DIAGNOSTICS['attempted_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    LAST_SCRAPE_DIAGNOSTICS['portal_reachable'] = False
    LAST_SCRAPE_DIAGNOSTICS['portal_error'] = None
    LAST_SCRAPE_DIAGNOSTICS['homepage_reachable'] = False
    LAST_SCRAPE_DIAGNOSTICS['homepage_error'] = None
    LAST_SCRAPE_DIAGNOSTICS['total_found'] = 0

    # Step 1: Scrape AllNotices page
    resp, err = fetch_page_with_retry(ALL_NOTICES_URL, retries=2, timeout=REQUEST_TIMEOUT)
    if resp and resp.status_code == 200:
        LAST_SCRAPE_DIAGNOSTICS['portal_reachable'] = True
        LAST_SCRAPE_DIAGNOSTICS['portal_status_code'] = 200
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Selector Strategy 1: Standard .notice-item elements
        items = soup.select('.notice-item')

        # Selector Strategy 2: Fallback to table rows / list items if .notice-item not present
        if not items:
            items = soup.select('table tr, .table tr, .list-group-item')

        for item in items:
            a_tag = item.find('a', href=lambda h: h and ('ViewNotice' in h or 'notice' in h.lower() or 'file' in h.lower() or '.pdf' in h.lower()))
            if not a_tag:
                continue

            title = a_tag.get_text(strip=True)
            if not title or len(title) < 4:
                continue

            # Filter out generic navigation links
            if title.lower() in ['view all notices', 'all notices', 'more notices', 'view all', 'notices', 'download', 'click here']:
                continue

            href = a_tag.get('href', '')
            full_link = urljoin(BASE_URL, href)

            # Badge check
            badge = item.find('span', class_='badge')
            badge_text = badge.get_text(strip=True) if badge else ""

            notice_id = extract_notice_id(href, badge_text, full_link, title)
            if notice_id in seen_ids:
                continue
            seen_ids.add(notice_id)

            # Extract Published Date
            item_text = item.get_text(' ', strip=True)
            date_match = re.search(r'(?:Published\s+On:|Date:?)\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4}|\d{2}[-/]\d{2}[-/]\d{4})', item_text, re.IGNORECASE)
            published_on = date_match.group(1) if date_match else datetime.now().strftime('%b %d, %Y')

            category = detect_category(title)
            is_new_badge = 'new-notice' in item.get('class', []) or 'new' in item_text.lower() or (badge and 'new' in badge.get_text(strip=True).lower())

            notices.append({
                'id': notice_id,
                'title': title,
                'link': full_link,
                'published_on': published_on,
                'category': category,
                'is_new': is_new_badge
            })

        # Selector Strategy 3: Direct scan for all <a> tags with ViewNotice if still 0 notices
        if not notices:
            all_anchors = soup.find_all('a', href=lambda h: h and ('ViewNotice' in h or 'ViewNoticeFile' in h))
            for a in all_anchors:
                title = a.get_text(strip=True)
                href = a.get('href', '')
                if not title or len(title) < 4 or title.lower() in ['view all', 'all notices', 'notices']:
                    continue
                full_link = urljoin(BASE_URL, href)
                notice_id = extract_notice_id(href, "", full_link, title)
                if notice_id in seen_ids:
                    continue
                seen_ids.add(notice_id)
                notices.append({
                    'id': notice_id,
                    'title': title,
                    'link': full_link,
                    'published_on': datetime.now().strftime('%b %d, %Y'),
                    'category': detect_category(title),
                    'is_new': True
                })
    else:
        LAST_SCRAPE_DIAGNOSTICS['portal_error'] = err
        db.log_event('WARNING', 'SCRAPER', f"Portal scrape note ({ALL_NOTICES_URL}): {err}")

    # Step 2: Also scrape homepage for marquee or announcements not yet in AllNotices
    hp_resp, hp_err = fetch_page_with_retry(HOMEPAGE_URL, retries=2, timeout=REQUEST_TIMEOUT)
    if hp_resp and hp_resp.status_code == 200:
        LAST_SCRAPE_DIAGNOSTICS['homepage_reachable'] = True
        hp_soup = BeautifulSoup(hp_resp.text, 'html.parser')
        hp_links = hp_soup.find_all('a', href=lambda h: h and ('ViewNotice' in h or 'notice' in h.lower() or 'fileRefId' in h))

        for a in hp_links:
            href = a.get('href', '')
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Filter out navigation links
            if title.lower() in ['view all notices', 'all notices', 'more notices', 'view all', 'notices']:
                continue
            if 'allnotices' in href.lower():
                continue

            full_link = urljoin(BASE_URL, href)
            notice_id = extract_notice_id(href, "", full_link, title)

            if notice_id in seen_ids:
                continue
            seen_ids.add(notice_id)

            notices.append({
                'id': notice_id,
                'title': title,
                'link': full_link,
                'published_on': datetime.now().strftime('%b %d, %Y'),
                'category': detect_category(title),
                'is_new': True
            })
    else:
        LAST_SCRAPE_DIAGNOSTICS['homepage_error'] = hp_err
        if not LAST_SCRAPE_DIAGNOSTICS['portal_reachable']:
            db.log_event('WARNING', 'SCRAPER', f"Homepage scrape note ({HOMEPAGE_URL}): {hp_err}")

    LAST_SCRAPE_DIAGNOSTICS['total_found'] = len(notices)
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

        portal_ok = LAST_SCRAPE_DIAGNOSTICS.get('portal_reachable') or LAST_SCRAPE_DIAGNOSTICS.get('homepage_reachable')
        portal_err = LAST_SCRAPE_DIAGNOSTICS.get('portal_error') or LAST_SCRAPE_DIAGNOSTICS.get('homepage_error')

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
                if res.get('success'):
                    db.mark_notice_emailed(nid, 'sent')
                    newly_handled_count += 1
                elif res.get('is_cloud_blocked'):
                    pass
                else:
                    db.mark_notice_emailed(nid, 'failed')
                time.sleep(1.5)  # respectful SMTP pacing
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
                if res.get('success'):
                    db.mark_notice_emailed(nid, 'sent')
                    newly_handled_count += 1
                elif res.get('is_cloud_blocked'):
                    pass
                else:
                    db.mark_notice_emailed(nid, 'failed')
                time.sleep(1.5)
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

        # Case: Portal was unreachable (timeout or connection error)
        if not portal_ok and total_scraped == 0:
            msg = f"Could not reach Raiganj University portal ({portal_err or 'Server timed out'}). The university server may be slow or temporarily offline. Rescheduled for next cycle at 7:00 AM/PM IST."
            db.log_event('WARNING', 'SCRAPER', msg)
            return {
                'status': 'connection_error',
                'message': msg,
                'new_count': 0,
                'dispatch_count': 0,
                'total_scraped': 0,
                'error': portal_err
            }

        # Case: Portal reached successfully, but no new notices to dispatch
        latest_id = scraped_notices[0].get('id') if scraped_notices else 'N/A'
        msg = f'Scheduled check completed at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}: Scanned {total_scraped} notices from portal. All notices are up to date (latest: #{latest_id}). Next check at 7:00 AM/PM IST.'
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
