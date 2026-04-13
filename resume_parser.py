import re
from pdfminer.high_level import extract_text
import io

def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        text = extract_text(io.BytesIO(file_bytes))
        return text.strip()
    except Exception as e:
        print(f"PDF extraction error: {e}")
        return ""

def clean_text(text: str) -> str:
    """Remove special unicode characters like bullets"""
    text = re.sub(r'[^\x00-\x7F\u0900-\u097F]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_name(lines: list) -> dict:
    """First non-empty line is usually the name"""
    for line in lines[:5]:
        line = line.strip()
        # Name usually has 2-3 words, no special chars except spaces
        if line and re.match(r'^[A-Za-z\s]{3,50}$', line):
            parts = line.split()
            if len(parts) >= 2:
                return {
                    "first_name": parts[0].capitalize(),
                    "last_name": " ".join(parts[1:]).capitalize()
                }
    return {"first_name": None, "last_name": None}

def extract_email(text: str) -> str:
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    return match.group(0).strip() if match else None

def extract_phone(text: str) -> str:
    # Matches +91 7800046119 or 9876543210 or +1-555-123-4567
    match = re.search(r'(\+?\d[\d\s\-().]{8,15}\d)', text)
    if match:
        phone = re.sub(r'\s+', ' ', match.group(0)).strip()
        return phone
    return None

def extract_linkedin(text: str) -> str:
    match = re.search(r'linkedin\.com/in/[\w\-]+', text, re.IGNORECASE)
    return match.group(0).strip() if match else None

def extract_location(text: str) -> str:
    """
    Extract location - look for City, State, Country patterns
    Handles: Bangalore, Karnataka, India | Lucknow | San Francisco, CA
    """
    # Pattern 1: City, State, Country (e.g. Bangalore, Karnataka, India)
    match = re.search(
        r'\b([A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z\s]+)\b',
        text
    )
    if match:
        return match.group(0).strip()

    # Pattern 2: City, State (e.g. Lucknow, UP or San Francisco, CA)
    match = re.search(
        r'\b([A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z]{1,20})\b',
        text
    )
    if match:
        loc = match.group(0).strip()
        # Avoid false positives like "Python, Laravel"
        non_locations = ['Python', 'Laravel', 'React', 'Node', 'MySQL', 'GitHub',
                        'MongoDB', 'JavaScript', 'PHP', 'CodeIgniter', 'LangChain']
        if not any(nl in loc for nl in non_locations):
            return loc

    # Pattern 3: Just a city name near location keywords
    match = re.search(
        r'(?:location|address|city|based in|residing in)[:\s]+([A-Z][a-zA-Z\s,]+)',
        text, re.IGNORECASE
    )
    if match:
        return match.group(1).strip()[:50]

    return None

def extract_years_of_experience(text: str) -> str:
    """Always return as string"""
    match = re.search(r'(\d+)\+?\s*years?\s*(of\s*)?(experience|exp)?', text, re.IGNORECASE)
    if match:
        return str(match.group(1))  # always string
    return None

def extract_current_title(lines: list, text: str) -> str:
    """Extract job title from objective/summary or early lines"""
    title_keywords = [
        "developer", "engineer", "manager", "designer", "analyst",
        "architect", "consultant", "specialist", "lead", "director",
        "scientist", "intern", "executive", "officer", "head",
        "full stack", "backend", "frontend", "software", "devops",
        "data", "php", "python", "java", "web"
    ]
    # Check first 5 lines
    for line in lines[1:6]:
        line = line.strip()
        if line and any(kw in line.lower() for kw in title_keywords):
            if len(line) < 80:
                return line

    # Check objective section
    obj_match = re.search(
        r'(?:objective|summary|profile)[:\s]*\n?(.*?)(?:\n)',
        text, re.IGNORECASE
    )
    if obj_match:
        obj_text = obj_match.group(1).strip()
        # Extract title from objective like "Innovative Full Stack Developer..."
        title_match = re.search(
            r'(?:Innovative|Experienced|Passionate|Skilled|Senior|Junior|Mid)?\s*([A-Z][a-zA-Z\s]+(?:Developer|Engineer|Designer|Analyst|Manager|Architect))',
            obj_text
        )
        if title_match:
            return title_match.group(1).strip()

    return None

def extract_current_company(text: str) -> str:
    """
    Extract most recent/current company
    Looks for patterns like 'Company Name — Role' or 'Present'
    """
    # Look for company with "Present" - most recent job
    match = re.search(
        r'([A-Z][a-zA-Z\s&.,]+(?:Pvt\.?\s*Ltd\.?|Inc\.?|LLC|Corp|Technologies|Solutions|Apps)?)[,\s—–-]+.*?(?:Present|Current)',
        text, re.IGNORECASE
    )
    if match:
        company = match.group(1).strip()
        company = re.sub(r'\s+', ' ', company)
        return company[:100]

    return None

def extract_bio(text: str) -> str:
    """Extract objective/summary section"""
    patterns = [
        r'(?:OBJECTIVE|SUMMARY|PROFILE|ABOUT)[:\s]*\n?(.*?)(?:\n\n|\n[A-Z]{2,}|\Z)',
        r'(?:Professional Summary)[:\s]*\n?(.*?)(?:\n\n|\Z)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            bio = match.group(1).strip()
            bio = re.sub(r'\s+', ' ', bio)
            if len(bio) > 30:
                return bio[:800]
    return None

def extract_skills(text: str) -> str:
    """Extract skills section content"""
    # Try to get the skills section
    skills_match = re.search(
        r'(?:TECHNICAL SKILLS?|SKILLS?|CORE COMPETENCIES)[:\s]*\n?(.*?)(?:\n\n|\n[A-Z]{3,}|\Z)',
        text, re.IGNORECASE | re.DOTALL
    )
    if skills_match:
        skills_text = skills_match.group(1).strip()
        # Clean up the text
        skills_text = re.sub(r'\s+', ' ', skills_text)

        # Extract individual skill words/phrases
        common_skills = [
            "PHP", "Laravel", "CodeIgniter", "JavaScript", "ES6", "React.js", "React",
            "Node.js", "LangChain", "Python", "MySQL", "MongoDB", "GitHub", "Postman",
            "WhatsApp Cloud API", "Google APIs", "HubSpot", "Zoho", "GoHighLevel",
            "OpenAI", "Chatbot", "Razorpay", "Stripe", "REST API", "AJAX", "JSON",
            "FastAPI", "Django", "Flask", "TypeScript", "Vue", "Angular", "HTML", "CSS",
            "PostgreSQL", "Redis", "Docker", "Kubernetes", "AWS", "Azure", "GCP",
            "Git", "GraphQL", "Machine Learning", "TensorFlow", "PyTorch",
            "Java", "C++", "C#", "Go", "Leadership", "Agile", "Scrum",
            "System Design", "Problem Solving", "WebSocket", "AJAX"
        ]
        found = [s for s in common_skills if s.lower() in skills_text.lower()]
        if found:
            return ", ".join(found)

        # Fallback: return raw skills text (first 500 chars)
        return skills_text[:500]

    return None

def extract_projects(text: str) -> str:
    """Extract projects section - especially useful for IT students"""
    projects_match = re.search(
        r'(?:PROJECTS?|PERSONAL PROJECTS?|ACADEMIC PROJECTS?|KEY PROJECTS?)[:\s]*\n?(.*?)(?:\n[A-Z]{3,}(?:\s[A-Z]{2,})*\n|\Z)',
        text, re.IGNORECASE | re.DOTALL
    )
    if projects_match:
        projects_text = projects_match.group(1).strip()
        projects_text = re.sub(r'\s+', ' ', projects_text)
        return projects_text[:2000]  # store up to 2000 chars
    return None

def parse_resume(file_bytes: bytes, filename: str) -> dict:
    """Main function - parse resume and return all extracted info"""
    raw_text = extract_text_from_pdf(file_bytes)
    text = clean_text(raw_text)

    # Split into lines for line-based extraction
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]

    name = extract_name(lines)
    location = extract_location(raw_text)  # use raw for better pattern matching

    print(f"DEBUG - Extracted name: {name}")
    print(f"DEBUG - Extracted location: {location}")
    print(f"DEBUG - Extracted email: {extract_email(text)}")

    return {
        "first_name": name["first_name"],
        "last_name": name["last_name"],
        "email": extract_email(text),
        "phone": extract_phone(text),
        "location": location,
        "linkedin_url": extract_linkedin(text),
        "current_title": extract_current_title(lines, text),
        "current_company": extract_current_company(raw_text),
        "years_of_experience": extract_years_of_experience(text),  # always string
        "bio": extract_bio(raw_text),
        "skills": extract_skills(raw_text),
        "projects": extract_projects(raw_text),
        "resume_filename": filename,
        "resume_text": raw_text[:5000]
    }
# import re
# from pdfminer.high_level import extract_text
# import io

# def extract_text_from_pdf(file_bytes: bytes) -> str:
#     """Extract raw text from PDF bytes"""
#     try:
#         text = extract_text(io.BytesIO(file_bytes))
#         return text.strip()
#     except Exception as e:
#         print(f"PDF extraction error: {e}")
#         return ""

# def extract_email(text: str) -> str:
#     match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
#     return match.group(0) if match else None

# def extract_phone(text: str) -> str:
#     match = re.search(r'(\+?\d[\d\s\-().]{7,}\d)', text)
#     return match.group(0).strip() if match else None

# def extract_linkedin(text: str) -> str:
#     match = re.search(r'(linkedin\.com/in/[\w\-]+)', text, re.IGNORECASE)
#     return match.group(0) if match else None

# def extract_location(text: str) -> str:
#     # Common patterns like "City, State" or "City, Country"
#     match = re.search(
#         r'\b([A-Z][a-zA-Z\s]+,\s?[A-Z]{2,})\b', text
#     )
#     return match.group(0).strip() if match else None

# def extract_years_of_experience(text: str) -> str:
#     match = re.search(r'(\d+)\+?\s*years?\s*(of)?\s*(experience)?', text, re.IGNORECASE)
#     return match.group(1) if match else None

# def extract_skills(text: str) -> str:
#     """Extract skills section from resume"""
#     common_skills = [
#         "Python", "FastAPI", "Django", "Flask", "JavaScript", "TypeScript",
#         "React", "Node.js", "Vue", "Angular", "HTML", "CSS",
#         "PostgreSQL", "MySQL", "MongoDB", "Redis",
#         "Docker", "Kubernetes", "AWS", "Azure", "GCP",
#         "Git", "REST APIs", "GraphQL", "Machine Learning",
#         "TensorFlow", "PyTorch", "Pandas", "NumPy",
#         "Java", "C++", "C#", "Go", "Rust", "Swift",
#         "Agile", "Scrum", "System Design", "Team Leadership",
#         "Problem Solving", "Communication"
#     ]
#     found_skills = [skill for skill in common_skills if skill.lower() in text.lower()]
#     return ", ".join(found_skills) if found_skills else None

# def extract_name(text: str) -> dict:
#     """Extract first and last name from first line of resume"""
#     lines = [line.strip() for line in text.split('\n') if line.strip()]
#     if lines:
#         name_parts = lines[0].split()
#         if len(name_parts) >= 2:
#             return {
#                 "first_name": name_parts[0],
#                 "last_name": " ".join(name_parts[1:])
#             }
#         elif len(name_parts) == 1:
#             return {"first_name": name_parts[0], "last_name": None}
#     return {"first_name": None, "last_name": None}

# def extract_current_title(text: str) -> str:
#     """Extract job title - usually on second line of resume"""
#     lines = [line.strip() for line in text.split('\n') if line.strip()]
#     title_keywords = [
#         "developer", "engineer", "manager", "designer", "analyst",
#         "architect", "consultant", "specialist", "lead", "director",
#         "scientist", "intern", "executive", "officer", "head"
#     ]
#     for line in lines[1:5]:  # Check first 5 lines
#         if any(keyword in line.lower() for keyword in title_keywords):
#             return line
#     return None

# def extract_current_company(text: str) -> str:
#     """Extract company name - look for common patterns"""
#     patterns = [
#         r'(?:at|@)\s+([A-Z][a-zA-Z\s&.,]+(?:Inc|LLC|Ltd|Corp|Co|Technologies|Solutions|Services)?\.?)',
#         r'([A-Z][a-zA-Z\s&]+(?:Inc|LLC|Ltd|Corp|Co|Technologies|Solutions|Services)\.?)',
#     ]
#     for pattern in patterns:
#         match = re.search(pattern, text)
#         if match:
#             return match.group(1).strip()
#     return None

# def extract_bio(text: str) -> str:
#     """Extract summary/bio section"""
#     patterns = [
#         r'(?:summary|profile|about|objective)[:\s]*\n?(.*?)(?:\n\n|\Z)',
#         r'(?:professional summary)[:\s]*\n?(.*?)(?:\n\n|\Z)',
#     ]
#     for pattern in patterns:
#         match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
#         if match:
#             bio = match.group(1).strip()
#             if len(bio) > 20:
#                 return bio[:500]  # limit to 500 chars
#     return None

# def parse_resume(file_bytes: bytes, filename: str) -> dict:
#     """Main function - parse resume and return all extracted info"""
#     text = extract_text_from_pdf(file_bytes)
#     name = extract_name(text)

#     return {
#         "first_name": name["first_name"],
#         "last_name": name["last_name"],
#         "email": extract_email(text),
#         "phone": extract_phone(text),
#         "location": extract_location(text),
#         "linkedin_url": extract_linkedin(text),
#         "current_title": extract_current_title(text),
#         "current_company": extract_current_company(text),
#         "years_of_experience": extract_years_of_experience(text),
#         "bio": extract_bio(text),
#         "skills": extract_skills(text),
#         "resume_filename": filename,
#         "resume_text": text[:5000]  # store first 5000 chars
#     }