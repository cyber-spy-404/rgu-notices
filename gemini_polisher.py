import os
import io
import re
import base64
import zipfile
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import pypdf
import markdown
import database as db

NOTICES_MD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notices_md')
NOTICES_FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notices_files')
os.makedirs(NOTICES_MD_DIR, exist_ok=True)
os.makedirs(NOTICES_FILES_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

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
    Performs OCR using Tesseract (pytesseract) on image or PDF bytes.
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
        print(f"Tesseract OCR note: {e}")
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
        resp = requests.get(link, headers=HEADERS, timeout=12)
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
                    pdf_resp = requests.get(target_pdf_url, headers=HEADERS, timeout=20)
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
    Polishes notice using Google Gemini.
    If the notice is a PDF or image, uses Gemini's Multimodal capabilities (inlineData)
    to OCR and read scanned text, stamps, handwriting, and tables directly!
    """
    notice_id = str(notice.get('id', 'notice')).replace('/', '_')
    title = notice.get('title', 'Official Notice')
    link = notice.get('link', 'https://raiganjuniversity.ac.in/')
    
    cfg = db.get_smtp_config()
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY') or cfg.get('gemini_api_key', '').strip()
    
    if not api_key:
        db.log_event('INFO', 'AI', f"No GEMINI_API_KEY configured. Using direct notice portal link layout for Notice #{notice_id}.")
        return generate_structured_fallback_md(notice, raw_md)

    prompt = f"""You are the official communications assistant for Raiganj University.
Summarize the attached official university notice document/text into a simple, clear, concise notice summary.

Notice Title: {title}
Official Portal Link: {link}

Format your response in simple, clean Markdown using this structure:
**Notice Overview:**
(2-3 simple, factual sentences explaining what this notice is about)

**Key Details:**
- **Who it applies to:** (e.g. All Students, UG Sem 4, PG, Ph.D., Department of Commerce, etc.)
- **Important Dates / Deadlines:** (Dates mentioned in the notice, or 'Not specified' if none)
- **Instructions:** (Short bullet points of what students need to do, if applicable)

Keep the language clear, simple, and direct. Do not add marketing hype or unnecessary symbols.
"""

    parts = [{"text": prompt}]

    # Multimodal OCR support: If we have PDF or Image bytes, pass directly to Gemini!
    if file_bytes and mime_type in ['application/pdf', 'image/jpeg', 'image/png']:
        try:
            # Gemini inlineData size limit is ~20MB, our PDFs are <2MB
            b64_data = base64.b64encode(file_bytes).decode('utf-8')
            parts.append({
                "inlineData": {
                    "mimeType": mime_type,
                    "data": b64_data
                }
            })
            db.log_event('INFO', 'AI', f"Sending {mime_type} ({len(file_bytes)} bytes) to Gemini Multimodal OCR.")
        except Exception as b64_err:
            print(f"Base64 encoding note: {b64_err}")
            parts[0]["text"] += f"\n\nExtracted Text:\n{raw_md[:6000]}"
    else:
        parts[0]["text"] += f"\n\nExtracted Text:\n{raw_md[:6000]}"

    models_to_try = [
        'gemini-2.5-flash',
        'gemini-2.0-flash',
        'gemini-1.5-flash'
    ]
    polished_text = None

    for model in models_to_try:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key.strip()}"
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096
            }
        }
        try:
            r = requests.post(endpoint, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                candidates = data.get('candidates', [])
                if candidates:
                    resp_parts = candidates[0].get('content', {}).get('parts', [])
                    text_parts = [p['text'] for p in resp_parts if 'text' in p and not p.get('thought')]
                    if text_parts:
                        polished_text = "\n\n".join(text_parts).strip()
                        db.log_event('SUCCESS', 'AI', f"Gemini ({model}) successfully polished Notice #{notice_id} (multimodal)!")
                        break
            elif r.status_code in [400, 401, 403, 429]:
                db.log_event('INFO', 'AI', f"Gemini API returned HTTP {r.status_code}. Immediately falling back to direct notice portal link.")
                break
            else:
                db.log_event('WARNING', 'AI', f"Gemini {model} returned HTTP {r.status_code}: {r.text[:120]}")
        except Exception as e:
            db.log_event('WARNING', 'AI', f"Gemini API connection error ({e}). Falling back to direct portal link.")
            break

    if not polished_text:
        return generate_structured_fallback_md(notice, raw_md)

    # Save polished markdown to disk
    polished_filepath = os.path.join(NOTICES_MD_DIR, f"{notice_id}_polished.md")
    try:
        with open(polished_filepath, 'w', encoding='utf-8') as f:
            f.write(polished_text)
    except Exception as e:
        print(f"Error saving polished markdown: {e}")

    return polished_text

def convert_md_to_html(md_text):
    """Converts markdown text to styled HTML for email body."""
    return markdown.markdown(
        md_text,
        extensions=['extra', 'nl2br', 'sane_lists']
    )

def generate_structured_fallback_md(notice, raw_extracted_text=""):
    """
    Creates a clean, structured student announcement markdown when Gemini API fails for any reason
    or is not yet configured. Direct notice portal link is prominently featured.
    """
    title = notice.get('title', 'Official University Notice')
    pub_date = notice.get('published_on', 'Recent')
    category = notice.get('category', 'General')
    notice_id = str(notice.get('id', 'N/A')).replace('/', '_')

    content_excerpt = ""
    if raw_extracted_text and len(raw_extracted_text.strip()) > 30:
        clean_lines = []
        for l in raw_extracted_text.splitlines():
            s = l.strip()
            if not s or s.startswith('#') or s.startswith('**') or 'Downloaded from' in s or 'Copyright' in s or 'https://' in s or 'Official Notice' in s:
                continue
            if len(s) > 15 and s not in clean_lines:
                clean_lines.append(s)
        if clean_lines:
            sample = "\n".join(f"- {line}" for line in clean_lines[:4])
            content_excerpt = f"\n\n**Notice Highlights:**\n{sample}"

    return f"""**Notice Overview:**  
Official announcement published by Raiganj University under **{category}**:  
*{title}*

**Key Details:**  
- **Category:** {category}  
- **Published On:** {pub_date}  
- **Document Attached:** Official circular file is attached to this email.  
{content_excerpt}

Please refer to the attached document or official link for complete instructions."""

def process_notice_complete(notice, force_ai=False):
    """
    Ensures notice file is grabbed, raw markdown is generated, and Gemini AI polish is run.
    Saves to disk and updates SQLite database.
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

    # Step 2: Check or run Gemini Polish
    has_gemini = False
    polished_md = ""

    if os.path.exists(polished_filepath) and not force_ai:
        try:
            with open(polished_filepath, 'r', encoding='utf-8') as f:
                polished_md = f.read()
                has_gemini = True
        except Exception:
            pass
    elif not force_ai and notice.get('polished_markdown'):
        polished_md = notice.get('polished_markdown')
        has_gemini = bool(notice.get('has_gemini_polish'))

    if not polished_md or force_ai:
        cfg = db.get_smtp_config()
        api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY') or cfg.get('gemini_api_key', '').strip()

        if api_key:
            res = polish_with_gemini(raw_md, notice, file_bytes=file_bytes, mime_type=mime_type)
            if res and res != raw_md:
                polished_md = res
                has_gemini = True

        if not polished_md:
            polished_md = generate_structured_fallback_md(notice, raw_md)

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
            has_gemini=1 if has_gemini else 0
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
        'has_gemini': has_gemini
    }

def simplify_all_stored_notices():
    """
    Regenerates simple, clean markdown and HTML summaries for all notices in the database and on disk.
    Strips away legacy bloated emoji headers and replaces with clean, concise summaries.
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

        simple_md = generate_structured_fallback_md(n, raw_md)
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
            has_gemini=0
        )
        updated += 1

    db.log_event('SUCCESS', 'AI', f'Simplified all {updated} notices in database to clean format.')
    return updated

