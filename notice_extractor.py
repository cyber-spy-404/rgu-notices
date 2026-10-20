import re

def clean_clause(text):
    """Cleans orphaned prepositions and punctuation from extracted clauses."""
    s = text.strip()
    s = re.sub(r'^(?:for|of|regarding|about)\s+', '', s, flags=re.IGNORECASE)
    s = re.sub(r'[,\.;\s]+$', '', s)
    return s.strip()

def clean_text_lines(text):
    """Filters out boilerplate portal headers, copyright, metadata, and download stamps."""
    cleaned = []
    for line in text.splitlines():
        l = line.strip()
        if not l:
            continue
        lower_l = l.lower()
        # Skip portal watermarks and metadata lines
        if any(b in lower_l for b in [
            'downloaded from raiganj university',
            'downloaded from',
            'copyright (c)',
            'viewnoticefilebyref',
            'raiganjuniversity.ac.in',
            'official notice text:',
            '# raiganj university notice',
            '**notice title:**',
            '**published date:**',
            '**category:**',
            '**official source link:**',
            '**local file attached:**'
        ]):
            continue
        cleaned.append(l)
    return cleaned

def extract_dates_and_times(text):
    """Extracts explicit calendar dates and timings from genuine circular text."""
    cleaned_lines = clean_text_lines(text)
    clean_body = "\n".join(cleaned_lines)

    date_patterns = [
        # e.g., July 3, 2026 or 3rd July, 2026 or 03 July 2026
        r'\b(?:\d{1,2}(?:st|nd|rd|th)?\s+)?(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{2,4}\b',
        # e.g., 26.09.2026 or 26/09/2026 or 26-09-2026
        r'\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b',
        # Bengali calendar dates: e.g. 18 সেপ্টেম্বর থেকে ২৫ সেপ্টেম্বর, ২০২৬
        r'\b\d{1,2}\s+[^\s0-9]+(?:\s+থেকে\s+\d{1,2}\s+[^\s0-9]+)?,\s*\d{4}\b'
    ]
    
    found_dates = []
    for p in date_patterns:
        for m in re.finditer(p, clean_body, re.IGNORECASE):
            d_str = m.group(0).strip().replace('\n', ' ')
            if d_str not in found_dates and len(d_str) < 35:
                found_dates.append(d_str)

    # Standard meeting/exam timings: e.g. 10:00 AM to 1:00 PM, 11:30 AM
    time_pattern = r'\b(?:0?[1-9]|1[0-2]):[0-5][0-9]\s*(?:AM|PM|am|pm)(?:\s*(?:to|-|–)\s*(?:0?[1-9]|1[0-2]):[0-5][0-9]\s*(?:AM|PM|am|pm))?\b'
    found_times = []
    for m in re.finditer(time_pattern, clean_body):
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
    if any(k in combined.lower() for k in ['research scholar', 'viva-voce', 'viva voce']):
        audiences.append("Ph.D. / Research Scholars")
    if any(k in combined.lower() for k in ['tender', 'quotation', 'niq', 'bidder']):
        audiences.append("Registered Vendors / Contractors")

    if not audiences:
        if str(category).lower() == 'holiday' or 'holiday' in combined.lower() or 'vacation' in combined.lower():
            audiences.append("All University Students, Faculty & Staff")
        elif any(k in str(category).lower() for k in ['tender', 'niq']):
            audiences.append("Registered Vendors / Contractors")
        elif category and str(category).lower() != 'general':
            audiences.append(f"Students & Faculty ({category})")
        else:
            audiences.append("All University Students & Faculty")

    return audiences[:3]

def extract_notice_reason(title, category="General", text=""):
    """
    Extracts the specific underlying reason/purpose for the notice:
    - For Holiday: Exact festival/occasion (e.g. Durga Puja, Gandhi Jayanti, Diwali)
    - For Exam/Program: Exact examination, schedule, or routine
    - For Tender/NIQ: Specific procurement, work contract, or equipment
    - For Admission: Specific admission round, verification, or registration
    - For Recruitment: Specific post or engagement
    - For General: Core official directive or administrative subject
    """
    title_clean = title.strip()
    clean_t = re.sub(
        r'^(?:urgent\s+)?(?:notice\s+(?:regarding|for|relating to)?|notification\s+(?:regarding|for)?|announcement\s+(?:regarding|for)?)\s*',
        '',
        title_clean,
        flags=re.IGNORECASE
    ).strip()
    clean_t = re.sub(r'[,\.;\s]+$', '', clean_t).strip()

    combined = f"{title_clean}\n{clean_t}\n{text}"
    cat_lower = str(category).lower()
    t_lower = title_clean.lower()

    # 1. Holiday / Vacation Reason
    if any(k in cat_lower for k in ['holiday']) or any(k in t_lower for k in ['holiday', 'vacation', 'recess', 'closure', 'closed']):
        festivals = [
            ('Durga Puja', [r'\bdurga\s*puja\b', r'\bdurgapuja\b', r'\bdurga\b']),
            ('Lakshmi Puja', [r'\blaxmi\s*puja\b', r'\blakshmi\s*puja\b', r'\blaxmi\b', r'\blakshmi\b']),
            ('Kali Puja & Diwali', [r'\bkali\s*puja\b', r'\bdiwali\b', r'\bdeepavali\b', r'\bdewali\b', r'\bkalipuja\b']),
            ('Bhatridwitiya (Bhai Dooj)', [r'\bbhatridwitiya\b', r'\bbhai\s*dooj\b', r'\bbhatriditiya\b']),
            ('Chhath Puja', [r'\bchhath\b', r'\bchhat\b']),
            ('Puja Vacation / Autumn Recess', [r'\bpuja\s*vacation\b', r'\bpuja\s*holidays\b', r'\bautumn\s*recess\b']),
            ('Mahatma Gandhi Birthday (Gandhi Jayanti)', [r'\bgandhi\s*jayanti\b', r'\bmahatma\s*gandhi\b', r'\bgandhiji\b']),
            ('Eid-ul-Fitr', [r'\beid-ul-fitr\b', r'\bid-ul-fitr\b', r'\beid\s*ul\s*fitr\b']),
            ('Eid-uz-Zoha (Bakrid)', [r'\beid-uz-zoha\b', r'\bbakrid\b', r'\bid-uz-zoha\b', r'\bid-uz-zuha\b']),
            ('Muharram', [r'\bmuharram\b', r'\bmoharram\b']),
            ('Fateha-Dwaz-Daham', [r'\bfateha-dwaz-daham\b', r'\bfateha\b']),
            ('Saraswati Puja (Vasant Panchami)', [r'\bsaraswati\s*puja\b', r'\bvasant\s*panchami\b']),
            ('Doljatra & Holi', [r'\bdoljatra\b', r'\bholi\b', r'\bdolyatra\b']),
            ('Netaji Subhas Chandra Bose Birthday', [r'\bnetaji\b', r'\bsubhas\s*chandra\s*bose\b']),
            ('Republic Day', [r'\brepublic\s*day\b']),
            ('Independence Day', [r'\bindependence\s*day\b']),
            ('Rabindra Jayanti', [r'\brabindra\s*jayanti\b', r'\btagore\b']),
            ('Summer Vacation', [r'\bsummer\s*vacation\b', r'\bsummer\s*recess\b']),
            ('Winter Recess', [r'\bwinter\s*recess\b', r'\bwinter\s*break\b', r'\bwinter\s*vacation\b']),
            ('Christmas & Year End', [r'\bchristmas\b', r'\bxmas\b', r'\bnew\s*year\b']),
            ('Bhanu Bhakta Acharya Jayanti', [r'\bbhanu\s*bhakta\b', r'\bbhanu\s*jayanti\b'])
        ]
        matched = []
        for fest_name, patterns in festivals:
            if any(re.search(pat, combined, re.IGNORECASE) for pat in patterns):
                matched.append(fest_name)
        if matched:
            return 'Holiday on account of ' + ' & '.join(matched)

        m = re.search(r'(?:on account of|on the occasion of|in observance of|due to|celebration of)\s+([^,\n\.;]+)', combined, re.IGNORECASE)
        if m:
            clean_occ = m.group(1).strip()
            if len(clean_occ) > 3 and len(clean_occ) < 60:
                return f'Holiday on account of {clean_occ}'

        comb_lower = combined.lower()
        if any(d in comb_lower for d in ['oct 01', 'oct 02', 'october 01', 'october 02']):
            return 'Holiday on account of Mahatma Gandhi Jayanti & Autumn Recess'
        if any(d in comb_lower for d in ['oct 1', 'oct 2', 'october']):
            return 'Holiday on account of Autumn Recess / Durga Puja & Lakshmi Puja Vacation'

        return 'University Holiday / Scheduled Vacation'

    # 2. Examination / Routine / Viva-Voce
    if any(k in cat_lower for k in ['exam', 'routine']) or any(k in t_lower for k in ['exam', 'programme', 'routine', 'viva-voce', 'viva voce']):
        if 'viva-voce' in t_lower or 'viva voce' in t_lower:
            m = re.search(r'(?:viva-voce|viva voce)\s+(?:examination\s+)?(?:of|for)?\s+([A-Za-z\s\.\-]+(?:department\s+of\s+[A-Za-z\s&]+)?)', title_clean, re.IGNORECASE)
            if m:
                return f'Ph.D Final Viva-Voce Examination of {clean_clause(m.group(1))}'
            return f'Ph.D Final Viva-Voce Examination: {clean_t}'

        if any(k in t_lower for k in ['reassessment', 'scrutiny', 'review']):
            m = re.search(r'(?:post publication reassessment\s*/?\s*post publication scrutiny|reassessment|scrutiny)\s*(?:of|for)?\s*([^,\n;]+)', title_clean, re.IGNORECASE)
            if m:
                return f'Post Publication Reassessment / Scrutiny for {clean_clause(m.group(1))}'

        if 'form fill' in t_lower:
            m = re.search(r'(?:form fill-?up\s+(?:notification|notice)?\s*(?:regarding|for)?)\s*([^,\n;]+)', title_clean, re.IGNORECASE)
            if m:
                return f'Online Form Fill-up for {clean_clause(m.group(1))}'

        m = re.search(r'(?:programme|schedule|routine)\s+(?:schedule\s+)?(?:for|of)\s+([^,\n;]+)', title_clean, re.IGNORECASE)
        if m:
            return f'Examination Schedule / Programme for {clean_clause(m.group(1))}'

    # 3. Tender / NIQ Reason
    if any(k in cat_lower for k in ['tender', 'niq']) or any(k in t_lower for k in ['tender', 'niq', 'quotation']):
        m = re.search(r'(?:niq|quotation|tender)\s+(?:rate contract\s+)?(?:for|regarding)\s+([^,\n;]+)', title_clean, re.IGNORECASE)
        if m:
            return f'Tender / NIQ for {clean_clause(m.group(1))}'
        m = re.search(r'(?:supplying|supply|purchase|installation|cleaning|fitting|fixing)\s+([^,\n;]+)', title_clean, re.IGNORECASE)
        if m:
            return f'Procurement / Maintenance for {clean_clause(m.group(1))}'

    # 4. Admission Reason
    if any(k in cat_lower for k in ['admission']) or any(k in t_lower for k in ['admission', 'mop-up', 'counselling', 'document verification', 'physical verification']):
        if any(k in t_lower for k in ['physical verification', 'documents verification', 'document verification', 'document verifications']):
            m_stud = re.search(r'(?:of|for)\s+([0-9]+(?:st|nd|rd|th)?\s+semester\s+provisionally\s+admitted\s+[^\n;]+)', title_clean, re.IGNORECASE)
            if not m_stud:
                m_stud = re.search(r'(?:of|for)\s+([A-Za-z0-9\s\.\-–]+(?:students?|candidates?|scholars?|ug|pg))', title_clean, re.IGNORECASE)
            if m_stud:
                return f'Physical Document Verification for {clean_clause(m_stud.group(1))}'
            return 'Physical Verification of Original Documents for Newly Admitted Students'

        if 'mop-up' in t_lower or 'mop up' in t_lower:
            m = re.search(r'(?:mop-up|mop up)\s+phase\s*(?:of)?\s*([^,\n;]+)', title_clean, re.IGNORECASE)
            if m:
                return f'Admission Mop-Up Phase for {clean_clause(m.group(1))}'

        if 'fresh application' in t_lower:
            m = re.search(r'(?:fresh application\s+for admission\s*([^,\n;]+))', title_clean, re.IGNORECASE)
            if m:
                return f'Fresh Admission Applications for {clean_clause(m.group(1))}'

        if 'extension' in t_lower:
            return f'Admission Schedule / Date Extension: {clean_t}'

    # 5. Recruitment Reason
    if any(k in cat_lower for k in ['recruitment']) or any(k in t_lower for k in ['recruitment', 'roster', 'engagement']):
        m = re.search(r'(?:recruitment|engagement|appointment)\s+(?:for|of)?\s+([^,\n;]+)', title_clean, re.IGNORECASE)
        if m:
            return f'Recruitment / Engagement for {clean_clause(m.group(1))}'
        return f'University Recruitment / Employment Notice: {clean_t}'

    # 6. Events / Competitions / Programs
    if any(k in cat_lower for k in ['event', 'academic']) or any(k in t_lower for k in ['competition', 'seminar', 'webinar', 'workshop', 'celebration', 'comp']):
        return f'University Event / Academic Program: {clean_t}'

    # 7. Specific administrative subjects
    if 'hra' in t_lower:
        return 'Declaration / Guidelines regarding House Rent Allowance (HRA)'
    if 'ncc' in t_lower:
        return 'Enrollment & Selection for National Cadet Corps (NCC) 2026'
    if 'ncl' in t_lower:
        return 'Mandatory Submission of Non-Creamy Layer (NCL) Certificate'

    # Fallback: cleaned concise title
    return clean_t if clean_t else title_clean

def extract_key_instructions(text):
    """Extracts critical directive sentences, action requirements, venues, or conditions."""
    cleaned_lines = clean_text_lines(text)
    clean_body = " ".join(cleaned_lines)

    # Split text into sentences
    raw_sentences = re.split(r'(?<=[.!?\n])\s+', clean_body)
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
        clean_s = re.sub(r'\s+', ' ', clean_s)
        lower_s = clean_s.lower()
        
        # Skip portal headers, generic titles, or short snippets
        if len(clean_s) < 25 or len(clean_s) > 220:
            continue
        if any(b in lower_s for b in ['downloaded from', 'copyright', 'all rights reserved', 'http', 'raiganjuniversity.ac.in']):
            continue

        if any(k in lower_s for k in action_keywords):
            # Normalize to avoid duplicates
            key = lower_s[:40]
            if key not in seen:
                seen.add(key)
                clean_s = clean_s[0].upper() + clean_s[1:]
                if not clean_s.endswith('.'):
                    clean_s += '.'
                actions.append(clean_s)

    return actions[:5]

def generate_key_details_and_summary(notice, raw_extracted_text=""):
    """
    Main extraction tool: Analyzes notice text and returns a simple, complete Markdown
    summary containing the Notice Reason / Purpose, Key Details, Target Audience, Dates,
    and Action Instructions.
    Runs 100% locally and reliably without requiring Gemini AI.
    """
    title = notice.get('title', 'Official University Notice').strip()
    category = notice.get('category', 'General').strip()
    pub_date = notice.get('published_on', 'Recent').strip()
    notice_id = str(notice.get('id', 'N/A')).replace('/', '_')

    # 1. Extract Specific Notice Reason / Purpose
    reason = extract_notice_reason(title, category, raw_extracted_text)

    # 2. Extract Target Audience
    audiences = extract_target_audience(title, raw_extracted_text, category)
    audience_str = ", ".join(audiences)

    # 3. Extract Dates & Times from clean circular text
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

    # 4. Extract Key Instructions / Directives
    instructions = extract_key_instructions(raw_extracted_text)
    
    instructions_block = ""
    if instructions:
        instructions_block = "\n" + "\n".join(f"- {act}" for act in instructions)
    else:
        instructions_block = "\n- Please review the attached circular document for specific procedures and directives."

    # 5. Build Final Clean Markdown
    markdown_output = f"""**Notice Overview:**  
Official circular issued by Raiganj University concerning **{reason}** for **{audience_str}**.

**Key Details:**  
- **Reason / Purpose:** {reason}  
- **Target Audience:** {audience_str}  
- **Category:** {category}  
- **Important Dates / Timing:** {dates_str}  
- **Official Document:** Official circular file is attached to this notification.

**Key Instructions & Actions:**{instructions_block}

Please refer to the attached document or official university link for complete schedule and instructions."""

    return markdown_output
