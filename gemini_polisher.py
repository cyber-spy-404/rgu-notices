import os
import io
import re
import requests
from bs4 import BeautifulSoup
import pypdf
import markdown
import database as db

NOTICES_MD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notices_md')
os.makedirs(NOTICES_MD_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def grab_and_convert_to_md(notice):
    """
    1. Downloads the notice file/webpage (PDF or HTML)
    2. Extracts clean text
    3. Converts and saves as a raw .md file in notices_md/{notice_id}.md
    """
    notice_id = str(notice.get('id', 'notice')).replace('/', '_')
    title = notice.get('title', 'Official Notice')
    link = notice.get('link', 'https://raiganjuniversity.ac.in/')
    pub_date = notice.get('published_on', 'Recent')
    category = notice.get('category', 'General')

    extracted_body = ""

    try:
        resp = requests.get(link, headers=HEADERS, timeout=20)
        content_type = resp.headers.get('Content-Type', '').lower()

        if resp.content[:4] == b'%PDF' or 'application/pdf' in content_type:
            # Extract PDF text
            reader = pypdf.PdfReader(io.BytesIO(resp.content))
            pages_text = []
            for i, page in enumerate(reader.pages):
                txt = page.extract_text()
                if txt and txt.strip():
                    pages_text.append(txt.strip())
            extracted_body = "\n\n".join(pages_text) if pages_text else "(Scanned PDF document or image notice)"
        else:
            # Extract HTML notice text
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Remove scripts, styles
            for s in soup(['script', 'style', 'nav', 'header', 'footer']):
                s.decompose()
            main_elem = soup.find('article') or soup.find(class_='notice-content') or soup.find('main') or soup.body
            extracted_body = main_elem.get_text('\n', strip=True) if main_elem else soup.get_text('\n', strip=True)

    except Exception as e:
        extracted_body = f"(Could not fetch full document text: {str(e)})"
        db.log_event('WARNING', 'SCRAPER', f"Notice #{notice_id} document fetch warning: {e}")

    # Build structured markdown
    raw_md = f"""# Raiganj University Notice #{notice_id}

**Notice Title:** {title}  
**Published Date:** {pub_date}  
**Category:** {category}  
**Official Source Link:** {link}  

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

    return raw_md, md_filepath

def polish_with_gemini(raw_md, notice):
    """
    Sends the raw notice markdown to Google Gemini to polish into an executive,
    student-friendly announcement with clear highlights, deadlines, and actions.
    Saves polished markdown to notices_md/{notice_id}_polished.md
    """
    notice_id = str(notice.get('id', 'notice')).replace('/', '_')
    title = notice.get('title', 'Official Notice')
    link = notice.get('link', 'https://raiganjuniversity.ac.in/')
    
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    
    if not api_key:
        db.log_event('INFO', 'AI', f"No GEMINI_API_KEY configured. Using raw notice markdown for Notice #{notice_id}.")
        return raw_md

    prompt = f"""You are the official student communications officer for Raiganj University (রায়গঞ্জ বিশ্ববিদ্যালয়).
Review the following raw markdown of an official university notice.
Convert and polish it into an executive, crystal-clear, student-friendly announcement.

Notice Title: {title}
Official Link: {link}

Raw Notice Content:
{raw_md[:6000]}

Please structure your response strictly in clean GitHub-Flavored Markdown with these sections:
### 📌 Executive Summary (TL;DR)
(2-3 clear sentences explaining what this notice is about in simple terms)

### 👥 Who is Affected?
(e.g., UG Sem 4, PG Students, All Departments, Applicants, etc.)

### ⚡ Key Action Items & Instructions
(Clear bullet points of what students must do step-by-step)

### 📅 Important Dates & Deadlines
(List any dates, timings, or write 'Not specified' if none)

### ⚠️ Important Notes / Venue / Fees
(Any fee amount, contact person, office room, or warning)

Guidelines:
- Do NOT invent facts or fake dates; extract only what is in the notice.
- If the notice is a holiday notice, clearly state the date of university reopening.
- Keep the language engaging, helpful, and easily scannable on mobile phones.
"""

    # Call Gemini REST API (gemini-1.5-flash or gemini-2.0-flash)
    models_to_try = ['gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-1.5-pro']
    polished_text = None

    for model in models_to_try:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key.strip()}"
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1000
            }
        }
        try:
            r = requests.post(endpoint, json=payload, headers={'Content-Type': 'application/json'}, timeout=25)
            if r.status_code == 200:
                data = r.json()
                candidates = data.get('candidates', [])
                if candidates:
                    parts = candidates[0].get('content', {}).get('parts', [])
                    if parts and 'text' in parts[0]:
                        polished_text = parts[0]['text'].strip()
                        db.log_event('SUCCESS', 'AI', f"Gemini ({model}) successfully polished Notice #{notice_id}!")
                        break
            else:
                db.log_event('WARNING', 'AI', f"Gemini {model} returned HTTP {r.status_code}: {r.text[:150]}")
        except Exception as e:
            db.log_event('WARNING', 'AI', f"Gemini {model} call error: {e}")

    if not polished_text:
        db.log_event('WARNING', 'AI', f"Gemini polishing unavailable. Falling back to original markdown.")
        return raw_md

    # Save polished markdown to disk
    polished_filepath = os.path.join(NOTICES_MD_DIR, f"{notice_id}_polished.md")
    try:
        with open(polished_filepath, 'w', encoding='utf-8') as f:
            f.write(polished_text)
    except Exception as e:
        print(f"Error saving polished markdown: {e}")

    return polished_text

def convert_md_to_html(md_text):
    """
    Converts markdown text to styled HTML for email body.
    """
    html = markdown.markdown(
        md_text,
        extensions=['extra', 'nl2br', 'sane_lists']
    )
    return html
