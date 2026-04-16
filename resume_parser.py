import re
import io
from pdfminer.high_level import extract_pages, extract_text
from pdfminer.layout import LTTextBox, LAParams

STANDARD_ATTRIBUTES = [
    {"code": "objective",               "name": "Objective",                "type": "text"},
    {"code": "technical_skills",        "name": "Technical Skills",         "type": "multi"},
    {"code": "education",               "name": "Education",                "type": "text"},
    {"code": "project_details",         "name": "Project Details",          "type": "text"},
    {"code": "professional_experience", "name": "Professional Experience",  "type": "text"},
    {"code": "achievements",            "name": "Achievements",             "type": "multi"},
    {"code": "strengths",               "name": "Strengths",                "type": "multi"},
    {"code": "certifications",          "name": "Certifications",           "type": "multi"},
    {"code": "languages",               "name": "Languages",                "type": "multi"},
    {"code": "hobbies",                 "name": "Hobbies",                  "type": "multi"},
    {"code": "references",              "name": "References",               "type": "text"},
    {"code": "location",                "name": "Location",                 "type": "text"},
    {"code": "linkedin",                "name": "LinkedIn",                 "type": "text"},
    {"code": "key_results",             "name": "Key Results Area",         "type": "multi"},
    {"code": "personal_details",        "name": "Personal Details",         "type": "text"},
    {"code": "contact",                 "name": "Contact",                  "type": "text"},
]

SECTION_PATTERNS = {
    "objective": r'(?:CAREER\s+OBJECTIVE|OBJECTIVE|SUMMARY|CAREER\s+SUMMARY|PROFESSIONAL\s+SUMMARY|PROFILE\s+SUMMARY|ABOUT\s+ME)',
    "technical_skills": r'(?:TECHNICAL\s+SKILLS?|SOFTWARE\s+SKILLS?|SKILLS?|CORE\s+COMPETENCIES|KEY\s+SKILLS?|IT\s+SKILLS?|PROGRAMMING\s+SKILLS?|TOOLS?\s+(?:&|AND)\s+TECHNOLOGIES?)',
    "education": r'(?:EDUCATION(?:AL\s+QUALIFICATIONS?)?|ACADEMIC\s+(?:BACKGROUND|DETAILS|QUALIFICATIONS?)|QUALIFICATIONS?|ACADEMICS?)',
    "project_details": r'(?:PROJECTS?|PERSONAL\s+PROJECTS?|ACADEMIC\s+PROJECTS?|KEY\s+PROJECTS?|MAJOR\s+PROJECTS?)',
    "professional_experience": r'(?:PROFESSIONAL\s+EXPERIENCE|WORK\s+EXPERIENCE|EXPERIENCE|EMPLOYMENT(?:\s+HISTORY)?|INTERNSHIPS?|WORK\s+HISTORY|CAREER\s+HISTORY)',
    "achievements": r'(?:ACHIEVEMENTS?|ACCOMPLISHMENTS?|AWARDS?\s*(?:&|AND)?\s*RECOGNITIONS?|HONORS?\s*(?:&|AND)?\s*AWARDS?)',
    "strengths": r'(?:STRENGTHS?|CORE\s+STRENGTHS?|KEY\s+STRENGTHS?|PERSONAL\s+STRENGTHS?)',
    "certifications": r'(?:CERTIFICATIONS?|CERTIFICATES?|PROFESSIONAL\s+CERTIFICATIONS?|COURSES?\s*(?:&|AND)?\s*CERTIFICATIONS?|TRAININGS?)',
    "languages": r'(?:LANGUAGES?\s+KNOWN|KNOWN\s+LANGUAGES?|LANGUAGES?|LANGUAGE\s+PROFICIENCY)',
    "hobbies": r'(?:HOBBIES|INTERESTS|HOBBIES\s*(?:&|AND)\s*INTERESTS|EXTRACURRICULAR(?:\s+ACTIVITIES)?|PERSONAL\s+INTERESTS?)',
    "references": r'(?:REFERENCES?|REFEREES?)',
    "key_results": r'(?:KEY\s+RESULTS?\s+AREA|KEY\s+RESPONSIBILITIES?|AREAS?\s+OF\s+EXPERTISE|CORE\s+AREAS?|RESPONSIBILITIES?)',
    "personal_details": r'(?:PERSONAL\s+DETAILS?|PERSONAL\s+INFORMATION|PERSONAL\s+PROFILE|PERSONAL\s+DATA)',
    "contact": r'(?:CONTACT(?:\s+DETAILS?|\s+INFO(?:RMATION)?)?)',
}


def extract_columns(file_bytes: bytes):
    params = LAParams(line_margin=0.5, char_margin=2.0)
    all_boxes = []

    for page_layout in extract_pages(io.BytesIO(file_bytes), laparams=params):
        page_width = page_layout.width
        for element in page_layout:
            if isinstance(element, LTTextBox):
                x0, y0 = element.bbox[0], element.bbox[1]
                all_boxes.append((x0, y0, page_width, element.get_text()))

    if not all_boxes:
        return "", ""

    page_width = all_boxes[0][2]
    col_split = _detect_column_split(all_boxes, page_width)

    if col_split is None:
        all_boxes.sort(key=lambda b: -b[1])
        return '\n'.join(b[3] for b in all_boxes), ""

    left  = sorted([(b[0],b[1],b[3]) for b in all_boxes if b[0] <  col_split], key=lambda b: -b[1])
    right = sorted([(b[0],b[1],b[3]) for b in all_boxes if b[0] >= col_split], key=lambda b: -b[1])

    print(f"DEBUG col_split={col_split:.0f}, left_boxes={len(left)}, right_boxes={len(right)}")
    return '\n'.join(b[2] for b in left), '\n'.join(b[2] for b in right)


def _detect_column_split(boxes, page_width):
    x0_vals = [b[0] for b in boxes]
    if max(x0_vals) - min(x0_vals) < 50:
        return None
    sorted_x = sorted(set(round(x) for x in x0_vals))
    biggest_gap, split_point = 0, None
    for i in range(1, len(sorted_x)):
        gap = sorted_x[i] - sorted_x[i-1]
        mid = (sorted_x[i] + sorted_x[i-1]) / 2
        if gap > biggest_gap and page_width * 0.2 < mid < page_width * 0.8:
            biggest_gap, split_point = gap, mid
    return split_point if biggest_gap > 50 else None


def extract_personal_info(full_text: str, right_text: str = "") -> dict:
    name_source = right_text if right_text.strip() else full_text
    lines = [l.strip() for l in name_source.split('\n') if l.strip()]

    name = None
    for line in lines[:6]:
        cleaned = line.strip()
        if re.match(r'^[A-Za-z][a-z]+(?:\s+[A-Za-z][a-z]+)+$', cleaned) and 4 <= len(cleaned) <= 50 and len(cleaned.split()) >= 2:
            name = cleaned; break
        if re.match(r'^[A-Z]{2,}(?:\s+[A-Z]{2,})+$', cleaned) and 4 <= len(cleaned) <= 50:
            name = cleaned.title(); break

    email_m = re.search(r'[\w.\+\-]+@[\w.\-]+\.\w{2,}', full_text)
    email = email_m.group(0).lower() if email_m else None

    phone_m = re.search(r'(?:(?:\+91|91|0)[\s\-]?)?[6-9]\d{9}', full_text)
    if phone_m:
        raw = re.sub(r'[\s\-]', '', phone_m.group(0))
        if raw.startswith('91') and len(raw) == 12:   phone = '+' + raw
        elif raw.startswith('0') and len(raw) == 11:  phone = '+91' + raw[1:]
        elif len(raw) == 10:                           phone = '+91' + raw
        else:                                          phone = raw
    else:
        phone = None

    linkedin_m = re.search(r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+', full_text, re.IGNORECASE)
    linkedin = linkedin_m.group(0) if linkedin_m else None

    return {"name": name, "email": email, "phone": phone, "linkedin": linkedin, "location": _extract_location(full_text)}


def _extract_location(text: str) -> str:
    # Priority 1: Address: line — grab up to 3 lines after "Address:"
    m = re.search(r'Address\s*[:\-]\s*([^\n]+(?:\n[^\n]+){0,2})', text, re.IGNORECASE)
    if m:
        addr = re.sub(r'\s+', ' ', m.group(1)).strip()[:120]
        if len(addr) > 5: return addr

    # Priority 2: 6-digit pincode context
    m = re.search(r'([A-Za-z][A-Za-z\s,\-\.]{3,60}\s*[-\s]\s*\d{6})', text)
    if m:
        loc = re.sub(r'\s+', ' ', m.group(1)).strip()[:120]
        if len(loc) > 5: return loc

    # Priority 3: Known Indian cities
    cities = ['Mumbai','Delhi','Bangalore','Bengaluru','Hyderabad','Chennai','Kolkata','Pune',
              'Ahmedabad','Jaipur','Lucknow','Kanpur','Nagpur','Indore','Bhopal','Patna',
              'Noida','Gurgaon','Gurugram','Chandigarh','Agra','Varanasi','Prayagraj','Dehradun']
    m = re.search(rf'\b({"|".join(cities)})\b(?:\s*[-,]\s*[A-Za-z\s]{{2,30}})?', text, re.IGNORECASE)
    if m: return m.group(0).strip()

    return None


def get_section_content(text: str, section_pattern: str, all_patterns: list) -> str:
    stop = '|'.join(all_patterns)
    pat = rf'(?:^|\n)\s*(?:{section_pattern})\s*[:\-]?\s*\n(.*?)(?=\n\s*(?:{stop})\s*[:\-]?\s*\n|\Z)'
    m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
    if m:
        content = re.sub(r'\n{3,}', '\n\n', m.group(1).strip())
        content = re.sub(r'[ \t]+', ' ', content).strip()
        return content if content else None
    return None


def clean_multi_value(text: str) -> str:
    if not text: return None
    text = re.sub(r'[•·●▪◦▸►✓✔\-–—]\s*', '', text)
    text = re.sub(r'[|\n\r]+', ',', text)
    items = re.split(r'[,;]+', text)
    cleaned, seen = [], set()
    skip = {'and','or','the','a','an','in','of','to','for','with'}
    for item in items:
        item = item.strip()
        if len(item) < 2 or item.lower() in skip: continue
        if item.lower() not in seen:
            seen.add(item.lower()); cleaned.append(item)
    return ', '.join(cleaned) if cleaned else None


def detect_dynamic_sections(text: str, known_codes: list) -> list:
    headings = re.findall(r'(?:^|\n)\s*([A-Z][A-Z\s&/]{3,40})\s*(?:\n|:)', text)
    new_attrs, seen = [], set(known_codes)
    for h in headings:
        h = h.strip()
        if not h: continue
        code = re.sub(r'_+','_', re.sub(r'[^a-z0-9_]','', h.lower().replace(' ','_').replace('&','and').replace('/','_'))).strip('_')
        if len(code) < 3 or code in seen: continue
        seen.add(code)
        new_attrs.append({"code": code, "name": h.title(), "type": "text"})
    return new_attrs


def parse_resume(file_bytes: bytes) -> dict:
    left_text, right_text = extract_columns(file_bytes)
    combined_text = left_text + "\n\n" + right_text if right_text else left_text

    if not combined_text.strip():
        raise ValueError("Could not extract text from PDF. File may be scanned/image-based.")

    personal = extract_personal_info(combined_text, right_text)
    all_stop = list(SECTION_PATTERNS.values())
    sections = {}

    # Parse left column first
    for code, pattern in SECTION_PATTERNS.items():
        content = get_section_content(left_text, pattern, all_stop)
        if content:
            attr_type = next((a["type"] for a in STANDARD_ATTRIBUTES if a["code"] == code), "text")
            if attr_type == "multi": content = clean_multi_value(content)
            if content: sections[code] = content

    # Parse right column (only if not already found)
    for code, pattern in SECTION_PATTERNS.items():
        if code in sections: continue
        content = get_section_content(right_text, pattern, all_stop)
        if content:
            attr_type = next((a["type"] for a in STANDARD_ATTRIBUTES if a["code"] == code), "text")
            if attr_type == "multi": content = clean_multi_value(content)
            if content: sections[code] = content

    if personal.get("location"): sections["location"] = personal["location"]
    if personal.get("linkedin"): sections["linkedin"] = personal["linkedin"]

    print(f"DEBUG personal: {personal}")
    print(f"DEBUG sections found: {list(sections.keys())}")

    return {"personal": personal, "sections": sections, "raw_text": combined_text}
# import re
# from pdfminer.high_level import extract_text
# import io

# # ── Pre-defined attribute codes that always exist ────────────────────────────
# STANDARD_ATTRIBUTES = [
#     {"code": "objective",           "name": "Objective",            "type": "text"},
#     {"code": "technical_skills",    "name": "Technical Skills",     "type": "multi"},
#     {"code": "education",           "name": "Education",            "type": "text"},
#     {"code": "project_details",     "name": "Project Details",      "type": "text"},
#     {"code": "professional_experience", "name": "Professional Experience", "type": "text"},
#     {"code": "achievements",        "name": "Achievements",         "type": "multi"},
#     {"code": "strengths",           "name": "Strengths",            "type": "multi"},
#     {"code": "certifications",      "name": "Certifications",       "type": "multi"},
#     {"code": "languages",           "name": "Languages",            "type": "multi"},
#     {"code": "hobbies",             "name": "Hobbies",              "type": "multi"},
#     {"code": "references",          "name": "References",           "type": "text"},
# ]

# # Section heading patterns to detect dynamically
# SECTION_PATTERNS = {
#     "objective":               r'(?:OBJECTIVE|SUMMARY|CAREER OBJECTIVE|PROFESSIONAL SUMMARY)',
#     "technical_skills":        r'(?:TECHNICAL SKILLS?|SKILLS?|CORE COMPETENCIES|KEY SKILLS)',
#     "education":               r'(?:EDUCATION|ACADEMIC|QUALIFICATION)',
#     "project_details":         r'(?:PROJECTS?|PERSONAL PROJECTS?|ACADEMIC PROJECTS?|KEY PROJECTS?)',
#     "professional_experience": r'(?:EXPERIENCE|PROFESSIONAL EXPERIENCE|WORK EXPERIENCE|EMPLOYMENT)',
#     "achievements":            r'(?:ACHIEVEMENTS?|ACCOMPLISHMENTS?|AWARDS?)',
#     "strengths":               r'(?:STRENGTHS?|CORE STRENGTHS?)',
#     "certifications":          r'(?:CERTIFICATIONS?|CERTIFICATES?|COURSES?)',
#     "languages":               r'(?:LANGUAGES?|KNOWN LANGUAGES?)',
#     "hobbies":                 r'(?:HOBBIES|INTERESTS|EXTRACURRICULAR)',
#     "references":              r'(?:REFERENCES?)',
# }


# def extract_text_from_pdf(file_bytes: bytes) -> str:
#     try:
#         text = extract_text(io.BytesIO(file_bytes))
#         return text.strip()
#     except Exception as e:
#         print(f"PDF extraction error: {e}")
#         return ""


# def get_section_content(text: str, section_pattern: str, all_patterns: list) -> str:
#     """
#     Extract content of a section by finding its heading
#     and stopping at the next section heading.
#     """
#     # Build a combined pattern of all section headings as stop markers
#     stop_pattern = '|'.join(all_patterns)

#     # Match the target section and capture until next section or end
#     full_pattern = rf'(?:{section_pattern})[:\s]*\n(.*?)(?=\n\s*(?:{stop_pattern})[:\s]*\n|\Z)'
#     match = re.search(full_pattern, text, re.IGNORECASE | re.DOTALL)
#     if match:
#         content = match.group(1).strip()
#         content = re.sub(r'\s+', ' ', content)
#         return content
#     return None


# def extract_personal_info(text: str) -> dict:
#     """Extract personal details from top of resume"""
#     lines = [l.strip() for l in text.split('\n') if l.strip()]

#     # Name — first clean line (2+ words, letters only)
#     name = None
#     for line in lines[:5]:
#         if re.match(r'^[A-Za-z\s]{3,50}$', line) and len(line.split()) >= 2:
#             name = line.strip()
#             break

#     # Email
#     email_match = re.search(r'[\w\.\+\-]+@[\w\.\-]+\.\w+', text)
#     email = email_match.group(0) if email_match else None

#     # Phone — international friendly
#     phone_match = re.search(r'(\+?\d[\d\s\-().]{7,17}\d)', text)
#     phone = phone_match.group(0).strip() if phone_match else None

#     # LinkedIn
#     linkedin_match = re.search(r'linkedin\.com/in/[\w\-]+', text, re.IGNORECASE)
#     linkedin = linkedin_match.group(0) if linkedin_match else None

#     # Location — City, State, Country pattern
#     location = None
#     # Try City, State, Country
#     loc_match = re.search(
#         r'\b([A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z\s]+)\b', text
#     )
#     if loc_match:
#         location = loc_match.group(0).strip()
#     else:
#         # Try City, State
#         loc_match = re.search(r'\b([A-Z][a-zA-Z]+,\s*[A-Z][a-zA-Z\s]{2,20})\b', text)
#         if loc_match:
#             candidate = loc_match.group(0).strip()
#             # Exclude tech keywords
#             skip = ['Python','Laravel','React','Node','MySQL','PHP','GitHub',
#                     'MongoDB','JavaScript','CodeIgniter','LangChain','Django']
#             if not any(s in candidate for s in skip):
#                 location = candidate

#     return {
#         "name": name,
#         "email": email,
#         "phone": phone,
#         "linkedin": linkedin,
#         "location": location,
#     }


# def clean_multi_value(text: str) -> str:
#     """
#     Convert multi-value text into comma-separated string.
#     Handles bullet points, pipe separated, newline separated.
#     """
#     if not text:
#         return None
#     # Remove bullets and special chars
#     text = re.sub(r'[•·●▪\-–]\s*', '', text)
#     # Replace pipes and newlines with comma
#     text = re.sub(r'[|\n]+', ',', text)
#     # Split and clean each item
#     items = [item.strip() for item in text.split(',') if item.strip() and len(item.strip()) > 1]
#     # Remove duplicates while preserving order
#     seen = set()
#     unique = []
#     for item in items:
#         if item.lower() not in seen:
#             seen.add(item.lower())
#             unique.append(item)
#     return ', '.join(unique) if unique else None


# def detect_dynamic_sections(text: str, known_codes: list) -> list:
#     """
#     Detect any section headings in the resume that are NOT already
#     in the standard attributes — create them dynamically.
#     """
#     # Find all UPPERCASE headings (likely section titles)
#     headings = re.findall(r'\n([A-Z][A-Z\s&/]{3,40})\s*\n', text)
#     new_attributes = []

#     for heading in headings:
#         heading = heading.strip()
#         code = heading.lower().replace(' ', '_').replace('&', 'and').replace('/', '_')
#         code = re.sub(r'[^a-z0-9_]', '', code)

#         # Skip if already known
#         if code in known_codes:
#             continue
#         # Skip if too short or generic
#         if len(code) < 3:
#             continue

#         new_attributes.append({
#             "code": code,
#             "name": heading.title(),
#             "type": "text"
#         })

#     return new_attributes


# def parse_resume(file_bytes: bytes) -> dict:
#     """
#     Main parser — returns:
#     {
#         "personal": { name, email, phone, linkedin, location },
#         "sections": { "objective": "...", "technical_skills": "HTML, CSS, PHP", ... }
#     }
#     """
#     raw_text = extract_text_from_pdf(file_bytes)

#     personal = extract_personal_info(raw_text)
#     all_stop_patterns = list(SECTION_PATTERNS.values())
#     sections = {}

#     for code, pattern in SECTION_PATTERNS.items():
#         content = get_section_content(raw_text, pattern, all_stop_patterns)
#         if content:
#             # Multi-value fields get comma separated
#             attr_type = next(
#                 (a["type"] for a in STANDARD_ATTRIBUTES if a["code"] == code), "text"
#             )
#             if attr_type == "multi":
#                 content = clean_multi_value(content)
#             sections[code] = content

#     # Add personal info fields as sections if extracted
#     if personal.get("location"):
#         sections["location"] = personal["location"]
#     if personal.get("linkedin"):
#         sections["linkedin"] = personal["linkedin"]

#     print(f"DEBUG personal: {personal}")
#     print(f"DEBUG sections found: {list(sections.keys())}")

#     return {
#         "personal": personal,
#         "sections": sections,
#         "raw_text": raw_text
#     }
