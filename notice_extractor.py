import re

def clean_text_lines(text):
    """Filters out boilerplate portal headers, copyright, and download stamps."""
    cleaned = []
    for line in text.splitlines():
        l = line.strip()
        if not l:
            continue
        # Skip portal watermarks and metadata lines
        if any(b in l.lower() for b in [
            'downloaded from raiganj university',
            'copyright (c)',
            'viewnoticefilebyref',
            'raiganjuniversity.ac.in',
            'official notice text:',
            '# raiganj university notice'
        ]):
            continue
        cleaned.append(l)
    return cleaned

def extract_dates_and_times(text):
    """Extracts explicit calendar dates and timings from the text."""
    date_patterns = [
        # e.g., July 3, 2026 or 3rd July, 2026 or 03 July 2026
        r'\b(?:\d{1,2}(?:st|nd|rd|th)?\s+)?(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{2,4}\b',
        # e.g., 26.09.2026 or 26/09/2026 or 26-09-2026
        r'\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b',
        # e.g., 18 সেপ্টেম্বর থেকে ২৫ সেপ্টেম্বর, ২০২৬
        r'\b\d{1,2}\s+[^\s0-9]+(?:\s+থেকে\s+\d{1,2}\s+[^\s0-9]+)?,\s*\d{4}\b'
    ]
    
    found_dates = []
    for p in date_patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            d_str = m.group(0).strip().replace('\n', ' ')
            if d_str not in found_dates and len(d_str) < 35:
                found_dates.append(d_str)

    # Timings: e.g. 10:00 AM to 1:00 PM, 11:30 AM
    time_pattern = r'\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)(?:\s*(?:to|-|–)\s*\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))?\b'
    found_times = []
    for m in re.finditer(time_pattern, text):
        t_str = m.group(0).strip()
        if t_str not in found_times:
            found_times.append(t_str)

    return found_dates, found_times

def extract_target_audience(title, text, category="General"):
    """Identifies the semester, program, department, or student group this notice applies to."""
    combined = f"{title}\n{text}"
    audiences = []

    # Semester & program pattern: e.g. UG 1st Semester, PG 3rd Sem, MBA, Ph.D.
    prog_pattern = r'\b(?:UG|PG|Undergraduate|Postgraduate|B\.?A\.?|B\.?Sc\.?|B\.?Com\.?|M\.?A\.?|M\.?Sc\.?|MBA|M\.?Com\.?|B\.?Tech|Ph\.?D|M\.?Phil|Diploma|Certificate)\s*(?:Sem(?:ester)?\s*[-–]?\s*(?:[I|V|X|1-8]+))?\b'
    for m in re.finditer(prog_pattern, combined, re.IGNORECASE):
        item = m.group(0).strip()
        if item and item.lower() not in [a.lower() for a in audiences]:
            audiences.append(item)

    # Department pattern
    dept_pattern = r'\bDepartment\s+of\s+([A-Za-z\s&]+?)(?:,|\.|\n|;|\s+Raiganj)'
    for m in re.finditer(dept_pattern, combined, re.IGNORECASE):
        d = m.group(1).strip()
        if len(d) > 2 and len(d) < 35:
            full_dept = f"Department of {d}"
            if full_dept not in audiences:
                audiences.append(full_dept)

    # Specific common groups
    if any(k in combined.lower() for k in ['newly admitted', 'provisionally admitted', 'cap student']):
        audiences.append("Newly Admitted / CAP Students")
    if 'research scholar' in combined.lower() or 'viva-voce' in combined.lower():
        audiences.append("Ph.D. / Research Scholars")
    if any(k in combined.lower() for k in ['tender', 'quotation', 'niq', 'bidder']):
        audiences.append("Registered Vendors / Contractors")

    if not audiences:
        if category and category.lower() != 'general':
            audiences.append(f"All students associated with {category}")
        else:
            audiences.append("All University Students & Faculty")

    return audiences[:3]

def extract_key_instructions(text):
    """Extracts critical directive sentences, action requirements, venues, or conditions."""
    # Split text into sentences
    raw_sentences = re.split(r'(?<=[.!?\n])\s+', text)
    action_keywords = [
        'must', 'mandatory', 'physical', 'verification', 'report to',
        'submission', 'deadline', 'scheduled on', 'held on', 'held at',
        'cancellation', 'attend', 'admit card', 'examination', 'timing',
        'fee', 'registration', 'session', 'viva-voce', 'interview',
        'commencing', 'directed to', 'requested to'
    ]
    
    actions = []
    seen = set()
    for s in raw_sentences:
        clean_s = s.strip().replace('\n', ' ')
        # Clean extra spaces
        clean_s = re.sub(r'\s+', ' ', clean_s)
        lower_s = clean_s.lower()
        
        # Skip portal headers, generic titles, or short snippets
        if len(clean_s) < 25 or len(clean_s) > 220:
            continue
        if any(b in lower_s for b in ['downloaded from', 'copyright', 'all rights reserved', 'http']):
            continue

        if any(k in lower_s for k in action_keywords):
            # Normalize to avoid duplicates
            key = lower_s[:40]
            if key not in seen:
                seen.add(key)
                # Capitalize first letter cleanly
                clean_s = clean_s[0].upper() + clean_s[1:]
                if not clean_s.endswith('.'):
                    clean_s += '.'
                actions.append(clean_s)

    return actions[:5]

def generate_key_details_and_summary(notice, raw_extracted_text=""):
    """
    Main extraction tool: Analyzes notice text and returns a simple, complete Markdown
    summary containing real Key Details, Target Audience, Dates, and Action Instructions.
    Runs 100% locally and reliably without requiring Gemini AI.
    """
    title = notice.get('title', 'Official University Notice').strip()
    category = notice.get('category', 'General').strip()
    pub_date = notice.get('published_on', 'Recent').strip()
    notice_id = str(notice.get('id', 'N/A')).replace('/', '_')
    link = notice.get('link', f"https://raiganjuniversity.ac.in/Website/ViewNotice/{notice_id}")

    # Combine title, category, and raw text
    full_text = f"{title}\n\n{raw_extracted_text}"

    # 1. Extract Target Audience
    audiences = extract_target_audience(title, raw_extracted_text, category)
    audience_str = ", ".join(audiences)

    # 2. Extract Dates & Times
    dates, times = extract_dates_and_times(raw_extracted_text)
    
    dates_display = []
    if pub_date and pub_date != 'Recent':
        dates_display.append(f"Published Date: {pub_date}")
    for d in dates[:3]:
        if d not in pub_date:
            dates_display.append(d)
    if times:
        dates_display.append(f"Timing: {times[0]}")
        
    dates_str = " | ".join(dates_display) if dates_display else f"Published On: {pub_date}"

    # 3. Extract Key Instructions / Directives
    instructions = extract_key_instructions(raw_extracted_text)
    
    instructions_block = ""
    if instructions:
        instructions_block = "\n" + "\n".join(f"- {act}" for act in instructions)
    else:
        instructions_block = "\n- Please review the attached circular document for specific procedures and directives."

    # 4. Generate Notice Overview (Clean 1-2 sentence summary)
    overview = f"Official notification issued by Raiganj University for **{audience_str}** regarding **{title}**."

    # 5. Build Final Clean Markdown
    markdown_output = f"""**Notice Overview:**  
{overview}

**Key Details:**  
- **Target Audience:** {audience_str}  
- **Category:** {category}  
- **Important Dates / Timing:** {dates_str}  
- **Official Document:** Official circular file is attached to this notification.

**Key Instructions & Actions:**{instructions_block}

Please refer to the attached document or official university link for complete schedule and instructions."""

    return markdown_output
