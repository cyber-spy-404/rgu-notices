import os
import io
import re
import zipfile
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import pypdf
import markdown
import database as db
import notice_extractor

NOTICES_MD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notices_md')
NOTICES_FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notices_files')
os.makedirs(NOTICES_MD_DIR, exist_ok=True)
os.makedirs(NOTICES_FILES_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Referer': 'https://raiganjuniversity.ac.in/'
}

def get_request_target_and_proxies(url):
    """
    Resolves request target URL and proxy dictionary if cloud proxy / scraping API is configured.
    Supports SCRAPERAPI_KEY, SCRAPEOPS_API_KEY, or SCRAPER_PROXY / PROXY_URL.
    """
    scraperapi_key = (os.getenv('SCRAPERAPI_KEY') or os.getenv('SCRAPER_API_KEY') or '').strip().strip('"\'')
    scrapeops_key = (os.getenv('SCRAPEOPS_API_KEY') or os.getenv('SCRAPEOPS_KEY') or '').strip().strip('"\'')
    proxy_url = (os.getenv('SCRAPER_PROXY', '').strip() or os.getenv('PROXY_URL', '').strip()).strip('"\'')

    if scraperapi_key:
        from urllib.parse import quote
        target = f"https://api.scraperapi.com?api_key={scraperapi_key}&url={quote(url, safe='')}&country_code=in"
        return target, None
    elif scrapeops_key:
        from urllib.parse import quote
        target = f"https://proxy.scrapeops.io/v1/?api_key={scrapeops_key}&url={quote(url, safe='')}&country=in"
        return target, None
    elif proxy_url:
        return url, {'http': proxy_url, 'https': proxy_url}
    
    return url, None

def extract_docx_text(file_bytes):
    """Extracts text from a .docx file without requiring external docx libraries."""
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            xml_content = z.read('word/document.xml')
            tree = ET.fromstring(xml_content)
            paragraphs = []
            for node in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                texts = [n.text for n in node.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if n.text]
                if texts:
                    paragraphs.append(''.join(texts))
            return '\n'.join(paragraphs)
    except Exception as e:
        return f"(Could not parse DOCX text: {e})"

def ocr_with_tesseract(file_bytes, mime_type='image/png'):
    """
    Performs OCR using Tesseract (pytesseract) on image or PDF bytes if tesseract is installed.
    Automatically discovers tesseract executable in standard Windows & Linux paths.
    """
    if not file_bytes:
        return ""
    try:
        import pytesseract
        from PIL import Image

        # Auto-configure tesseract path on Windows
        if os.name == 'nt':
            for p in [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                os.path.expanduser(r'~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'),
            ]:
                if os.path.exists(p):
                    pytesseract.pytesseract.tesseract_cmd = p
                    break

        if 'pdf' in mime_type:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            texts = []
            for page in reader.pages:
                for img_obj in page.images:
                    try:
                        pil_img = Image.open(io.BytesIO(img_obj.data))
                        txt = pytesseract.image_to_string(pil_img)
                        if txt.strip():
                            texts.append(txt.strip())
                    except Exception:
                        pass
            return "\n\n".join(texts).strip()
        else:
            pil_img = Image.open(io.BytesIO(file_bytes))
            return pytesseract.image_to_string(pil_img).strip()
    except Exception as e:
        return ""

def grab_notice_file_and_text(notice):
    """
    1. Downloads the notice file (PDF, DOCX, Image, or HTML).
    2. If it's an HTML page embedding a PDF, follows and grabs the actual PDF document.
    3. Saves the original file into notices_files/{notice_id}.ext
    4. Extracts text from the document (using pypdf and Tesseract OCR).
    5. Generates structured raw markdown and saves into notices_md/{notice_id}.md
    Returns: (raw_md, md_path, file_path, mime_type, file_bytes)
    """
    notice_id = str(notice.get('id', 'notice')).replace('/', '_')
    title = notice.get('title', 'Official Notice')
    link = notice.get('link', 'https://raiganjuniversity.ac.in/')
    pub_date = notice.get('published_on', 'Recent')
    category = notice.get('category', 'General')

    # Normalize link if it's pointing to generic root URL
    if not link or link.strip().rstrip('/') in ['https://raiganjuniversity.ac.in', 'http://raiganjuniversity.ac.in']:
        link = f"https://raiganjuniversity.ac.in/Website/ViewNotice/{notice_id}"

    extracted_body = ""
    saved_filepath = None
    mime_type = "text/html"
    file_bytes = None

    try:
        req_url, req_proxies = get_request_target_and_proxies(link)
        resp = requests.get(req_url, headers=HEADERS, proxies=req_proxies, timeout=(12, 35))
        content = resp.content
        ctype = resp.headers.get('Content-Type', '').lower()

        # Check for direct PDF
        if content[:4] == b'%PDF' or 'application/pdf' in ctype:
            mime_type = 'application/pdf'
            file_bytes = content
            saved_filepath = os.path.join(NOTICES_FILES_DIR, f"{notice_id}.pdf")
            with open(saved_filepath, 'wb') as f:
                f.write(content)
            
            # Extract text via pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            pages = [p.extract_text() for p in reader.pages if p.extract_text() and p.extract_text().strip()]
            extracted_body = "\n\n".join(pages) if pages else ""
            if not extracted_body or len(extracted_body.strip()) < 30:
                ocr_text = ocr_with_tesseract(content, 'application/pdf')
                if ocr_text:
                    extracted_body = ocr_text
                    db.log_event('INFO', 'OCR', f"Notice #{notice_id}: Extracted text via Tesseract OCR.")
                else:
                    extracted_body = "(Official scanned notice document attached)"

        # Check for Images (JPEG/PNG)
        elif content[:3] == b'\xff\xd8\xff' or 'image/jpeg' in ctype:
            mime_type = 'image/jpeg'
            file_bytes = content
            saved_filepath = os.path.join(NOTICES_FILES_DIR, f"{notice_id}.jpg")
            with open(saved_filepath, 'wb') as f:
                f.write(content)
            ocr_text = ocr_with_tesseract(content, 'image/jpeg')
            extracted_body = ocr_text if ocr_text else "(Official notice image attached)"
            if ocr_text:
                db.log_event('INFO', 'OCR', f"Notice #{notice_id}: Extracted text from image via Tesseract OCR.")

        elif content[:4] == b'\x89PNG' or 'image/png' in ctype:
            mime_type = 'image/png'
            file_bytes = content
            saved_filepath = os.path.join(NOTICES_FILES_DIR, f"{notice_id}.png")
            with open(saved_filepath, 'wb') as f:
                f.write(content)
            ocr_text = ocr_with_tesseract(content, 'image/png')
            extracted_body = ocr_text if ocr_text else "(Official notice image attached)"
            if ocr_text:
                db.log_event('INFO', 'OCR', f"Notice #{notice_id}: Extracted text from image via Tesseract OCR.")

        # Check for DOCX / Office files
        elif content[:4] == b'PK\x03\x04' and ('word' in ctype or link.endswith('.docx')):
            mime_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            file_bytes = content
            saved_filepath = os.path.join(NOTICES_FILES_DIR, f"{notice_id}.docx")
            with open(saved_filepath, 'wb') as f:
                f.write(content)
            extracted_body = extract_docx_text(content)

        # HTML Webpage - check if it links to an actual PDF
        else:
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Check for embedded PDF or download links
            pdf_link = soup.find('a', href=lambda h: h and ('.pdf' in h.lower() or 'ViewNoticeFile' in h or 'download' in h.lower()))
            iframe_pdf = soup.find('iframe', src=lambda s: s and ('.pdf' in s.lower() or 'ViewNotice' in s))

            target_pdf_url = None
            if pdf_link:
                from urllib.parse import urljoin
                target_pdf_url = urljoin(link, pdf_link['href'])
            elif iframe_pdf:
                from urllib.parse import urljoin
                target_pdf_url = urljoin(link, iframe_pdf['src'])

            if target_pdf_url and target_pdf_url != link:
                try:
                    pdf_target, pdf_proxies = get_request_target_and_proxies(target_pdf_url)
                    pdf_resp = requests.get(pdf_target, headers=HEADERS, proxies=pdf_proxies, timeout=(12, 35))
                    if pdf_resp.content[:4] == b'%PDF' or 'application/pdf' in pdf_resp.headers.get('Content-Type', '').lower():
                        mime_type = 'application/pdf'
                        file_bytes = pdf_resp.content
                        saved_filepath = os.path.join(NOTICES_FILES_DIR, f"{notice_id}.pdf")
                        with open(saved_filepath, 'wb') as f:
                            f.write(pdf_resp.content)
                        reader = pypdf.PdfReader(io.BytesIO(pdf_resp.content))
                        pages = [p.extract_text() for p in reader.pages if p.extract_text() and p.extract_text().strip()]
                        extracted_body = "\n\n".join(pages) if pages else ""
                        if not extracted_body or len(extracted_body.strip()) < 30:
                            ocr_text = ocr_with_tesseract(pdf_resp.content, 'application/pdf')
                            if ocr_text:
                                extracted_body = ocr_text
                                db.log_event('INFO', 'OCR', f"Notice #{notice_id}: Extracted text from embedded PDF via Tesseract OCR.")
                            else:
                                extracted_body = "(Official scanned document attached)"
                except Exception as inner_e:
                    print(f"Inner PDF download note: {inner_e}")

            if not extracted_body:
                for s in soup(['script', 'style', 'nav', 'header', 'footer']):
                    s.decompose()
                main_elem = soup.find('article') or soup.find(class_='notice-content') or soup.find('main') or soup.body
                extracted_body = main_elem.get_text('\n', strip=True) if main_elem else soup.get_text('\n', strip=True)

    except Exception as e:
        extracted_body = f"(Could not download notice file: {str(e)})"
        db.log_event('WARNING', 'SCRAPER', f"Notice #{notice_id} file fetch warning: {e}")

    # Build raw markdown document
    raw_md = f"""# Raiganj University Notice #{notice_id}

**Notice Title:** {title}  
**Published Date:** {pub_date}  
**Category:** {category}  
**Official Source Link:** {link}  
**Local File Attached:** {os.path.basename(saved_filepath) if saved_filepath else 'None'}  

---

### Official Notice Text:
{extracted_body}
"""

    md_filepath = os.path.join(NOTICES_MD_DIR, f"{notice_id}.md")
    try:
        with open(md_filepath, 'w', encoding='utf-8') as f:
            f.write(raw_md)
    except Exception as e:
        print(f"Error saving raw markdown: {e}")

    return raw_md, md_filepath, saved_filepath, mime_type, file_bytes

def polish_with_gemini(raw_md, notice, file_bytes=None, mime_type=None):
    """
    (Deprecated) Kept for API compatibility.
    Uses notice_extractor for 100% local, deterministic, and instant summary extraction
    without any Gemini AI or external API calls.
    """
    return generate_structured_fallback_md(notice, raw_md)

def convert_md_to_html(md_text):
    """Converts markdown text to styled HTML for email body."""
    return markdown.markdown(
        md_text,
        extensions=['extra', 'nl2br', 'sane_lists']
    )

def generate_structured_fallback_md(notice, raw_extracted_text=""):
    """
    Creates rich Key Details and Summary using local notice_extractor tool
    (Notice Reason/Purpose, Target Audience, Dates/Timings, Action Items, Document attachment).
    Runs 100% locally with zero external AI dependency.
    """
    return notice_extractor.generate_key_details_and_summary(notice, raw_extracted_text)

def process_notice_complete(notice, force_ai=False):
    """
    Grabs notice file, extracts text via pypdf + Tesseract OCR, and generates
    rich key details, notice reason, and summary using notice_extractor completely locally.
    """
    notice_id = str(notice.get('id', 'notice')).replace('/', '_')
    md_filepath = os.path.join(NOTICES_MD_DIR, f"{notice_id}.md")
    polished_filepath = os.path.join(NOTICES_MD_DIR, f"{notice_id}_polished.md")

    raw_md = ""
    saved_filepath = None
    mime_type = "text/html"
    file_bytes = None
    attachment_name = None

    # Step 1: Check existing raw markdown on disk
    if os.path.exists(md_filepath) and not force_ai:
        try:
            with open(md_filepath, 'r', encoding='utf-8') as f:
                raw_md = f.read()
        except Exception:
            pass

    # Check existing attached file in notices_files/
    if os.path.exists(NOTICES_FILES_DIR):
        for fname in os.listdir(NOTICES_FILES_DIR):
            if fname.startswith(f"{notice_id}."):
                saved_filepath = os.path.join(NOTICES_FILES_DIR, fname)
                attachment_name = fname
                try:
                    with open(saved_filepath, 'rb') as f:
                        file_bytes = f.read()
                    mime_type = 'application/pdf' if fname.endswith('.pdf') else 'application/octet-stream'
                except Exception:
                    pass
                break

    if not raw_md or (not saved_filepath and force_ai):
        try:
            raw_md, md_filepath, saved_filepath, mime_type, file_bytes = grab_notice_file_and_text(notice)
            if saved_filepath:
                attachment_name = os.path.basename(saved_filepath)
        except Exception as e:
            raw_md = f"# Notice #{notice_id}: {notice.get('title')}\n\n(Could not retrieve file: {str(e)})"

    # Step 2: Generate Key Details & Notice Reason locally using notice_extractor
    polished_md = ""
    if os.path.exists(polished_filepath) and not force_ai:
        try:
            with open(polished_filepath, 'r', encoding='utf-8') as f:
                polished_md = f.read()
        except Exception:
            pass
    elif not force_ai and notice.get('polished_markdown'):
        polished_md = notice.get('polished_markdown')

    if not polished_md or force_ai:
        polished_md = notice_extractor.generate_key_details_and_summary(notice, raw_md)

    polished_html = convert_md_to_html(polished_md)

    # Save files to disk cache
    try:
        if raw_md and not os.path.exists(md_filepath):
            with open(md_filepath, 'w', encoding='utf-8') as f:
                f.write(raw_md)
        if polished_md:
            with open(polished_filepath, 'w', encoding='utf-8') as f:
                f.write(polished_md)
    except Exception as e:
        print(f"Error persisting markdown to disk: {e}")

    # Step 3: Update SQLite database with content
    try:
        db.update_notice_ai(
            notice_id=notice_id,
            raw_md=raw_md,
            polished_md=polished_md,
            polished_html=polished_html,
            attachment_path=saved_filepath or '',
            has_gemini=1
        )
    except Exception as e:
        print(f"Database update notice AI note: {e}")

    return {
        'id': notice_id,
        'title': notice.get('title', ''),
        'link': notice.get('link', ''),
        'published_on': notice.get('published_on', ''),
        'category': notice.get('category', 'General'),
        'raw_md': raw_md,
        'md_path': md_filepath,
        'polished_md': polished_md,
        'polished_html': polished_html,
        'saved_filepath': saved_filepath,
        'attachment_name': attachment_name,
        'has_gemini': False
    }

def simplify_all_stored_notices():
    """
    Extracts Notice Reason, Key Details, and clean Summaries for all notices in the database and on disk
    using notice_extractor tool (running 100% locally with zero external Gemini AI).
    """
    notices = db.get_notices(limit=500)
    updated = 0
    for n in notices:
        nid = str(n.get('id', ''))
        raw_md = n.get('raw_markdown', '')
        md_file = os.path.join(NOTICES_MD_DIR, f"{nid}.md")
        if not raw_md and os.path.exists(md_file):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    raw_md = f.read()
            except Exception:
                pass

        # If raw_md is minimal, attempt to extract directly from notices_files PDF
        if not raw_md or len(raw_md.strip()) < 50:
            if os.path.exists(NOTICES_FILES_DIR):
                for fname in os.listdir(NOTICES_FILES_DIR):
                    if fname.startswith(f"{nid}."):
                        fpath = os.path.join(NOTICES_FILES_DIR, fname)
                        if fname.endswith('.pdf'):
                            try:
                                reader = pypdf.PdfReader(fpath)
                                pages = [p.extract_text() for p in reader.pages if p.extract_text() and p.extract_text().strip()]
                                if pages:
                                    raw_md = f"# Notice #{nid}: {n.get('title')}\n\n" + "\n".join(pages)
                            except Exception:
                                pass
                        break

        # Generate Notice Reason, Key Details & Summary locally
        simple_md = notice_extractor.generate_key_details_and_summary(n, raw_md)
        simple_html = convert_md_to_html(simple_md)

        # Update disk file
        polished_file = os.path.join(NOTICES_MD_DIR, f"{nid}_polished.md")
        try:
            with open(polished_file, 'w', encoding='utf-8') as f:
                f.write(simple_md)
        except Exception:
            pass

        # Update database
        db.update_notice_ai(
            notice_id=nid,
            raw_md=raw_md or n.get('raw_markdown', ''),
            polished_md=simple_md,
            polished_html=simple_html,
            attachment_path=n.get('attachment_path', ''),
            has_gemini=1
        )
        updated += 1

    db.log_event('SUCCESS', 'SUMMARY', f'Extracted notice reasons, key details, and updated all {updated} notices in database.')
    return updated
