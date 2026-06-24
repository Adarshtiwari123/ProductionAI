import os
import json
import uuid
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, black
from reportlab.lib.units import inch
from sqlalchemy.orm import Session
from groq import Groq

import models

def evaluate_interview(session, questions, user, db: Session):
    # 1. Fetch from DB if already exists
    report = db.query(models.InterviewReport).filter(models.InterviewReport.session_id == session.id).first()
    if report and report.overall_score is not None:
        return report

    # 2. Prepare the transcript
    transcript = ""
    for sq in questions:
        q_text = sq.question.text if sq.question else "Question"
        ans_text = sq.answer_text if sq.answer_text else "No answer provided"
        feedback_text = sq.ai_feedback if sq.ai_feedback else "No feedback provided"
        transcript += f"Q{sq.question_order}: {q_text}\nAnswer: {ans_text}\nFeedback given: {feedback_text}\n\n"

    # 3. Call Groq
    groq_api_key = os.getenv("GROQ_API_KEY")
    client = Groq(api_key=groq_api_key)
    
    prompt = f"""You are an expert technical interviewer evaluating a candidate named {user.name}.
Interview Type: {session.role} - {session.topic}

Transcript:
{transcript}

You must evaluate the candidate strictly. Return ONLY valid JSON in the exact format:
{{
  "overall_score": 75,
  "technical_score": 20,
  "communication_score": 18,
  "problem_solving_score": 17,
  "project_score": 20,
  "strengths": ["Strength point 1", "Strength point 2"],
  "improvements": ["Area for improvement 1", "Area for improvement 2"],
  "suggestions": "A paragraph of actionable suggestions for the candidate."
}}
Each sub-score is out of 25. The overall score is out of 100.
"""

    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        data = json.loads(resp.choices[0].message.content)
        
        if not report:
            report = models.InterviewReport(
                session_id=session.id,
                user_id=user.id,
            )
            db.add(report)

        report.overall_score = data.get("overall_score", 0)
        report.technical_score = data.get("technical_score", 0)
        report.communication_score = data.get("communication_score", 0)
        report.problem_solving_score = data.get("problem_solving_score", 0)
        report.project_score = data.get("project_score", 0)
        report.strengths = data.get("strengths", [])
        report.improvements = data.get("improvements", [])
        report.suggestions = data.get("suggestions", "")
        report.generated_at = datetime.utcnow()
        db.commit()
        db.refresh(report)
        return report
    except Exception as e:
        print("Error evaluating interview:", e)
        return None

def generate_pdf_report(session, questions, user, report):
    file_name = f"interview_report_{uuid.uuid4().hex}.pdf"
    file_path = os.path.join("reports", file_name)
    os.makedirs("reports", exist_ok=True)
    
    doc = SimpleDocTemplate(file_path, pagesize=letter,
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    
    styles = getSampleStyleSheet()
    
    # Custom Styles matching the example
    title_style = ParagraphStyle(
        'MainTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=HexColor("#1A365D"),
        spaceAfter=30
    )
    
    heading2_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=16,
        spaceBefore=20,
        spaceAfter=10,
        textColor=black
    )
    
    normal_style = styles["Normal"]
    bullet_style = ParagraphStyle(
        'Bullet',
        parent=styles['Normal'],
        leftIndent=20,
        spaceAfter=5
    )
    
    qa_style = ParagraphStyle(
        'QAStyle',
        parent=styles['Normal'],
        spaceAfter=10,
        leading=14
    )

    elements = []
    
    # Title
    elements.append(Paragraph("Interview Evaluation Report", title_style))
    
    # Candidate Info
    date_str = session.started_at.strftime("%Y-%m-%d %H:%M") if session.started_at else datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    elements.append(Paragraph(f"<b>Candidate:</b> {user.name}", normal_style))
    elements.append(Paragraph(f"<b>Interview Type:</b> {session.role} - {session.topic}", normal_style))
    elements.append(Paragraph(f"<b>Date:</b> {date_str}", normal_style))
    elements.append(Spacer(1, 20))
    
    # Performance Summary
    elements.append(Paragraph("Performance Summary", heading2_style))
    
    data = [
        ['Category', 'Score'],
        ['Overall Score', f"{report.overall_score}/100"],
        ['Technical Knowledge', f"{report.technical_score}/25"],
        ['Communication Skills', f"{report.communication_score}/25"],
        ['Problem Solving', f"{report.problem_solving_score}/25"],
        ['Project Understanding', f"{report.project_score}/25"]
    ]
    
    t = Table(data, colWidths=[3*inch, 2*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (1,0), HexColor("#2D3748")),
        ('TEXTCOLOR', (0,0), (1,0), HexColor("#FFFFFF")),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (1,0), 10),
        ('TOPPADDING', (0,0), (1,0), 10),
        ('GRID', (0,0), (-1,-1), 1, HexColor("#E2E8F0")),
        ('BACKGROUND', (0,1), (-1,-1), HexColor("#F7FAFC")),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('ALIGN', (0,1), (0,-1), 'CENTER'),
        ('ALIGN', (1,1), (1,-1), 'CENTER'),
    ]))
    elements.append(t)
    
    import html
    def safe_json_load(data):
        if isinstance(data, str):
            try:
                return json.loads(data)
            except Exception:
                return []
        return data if isinstance(data, list) else []

    strengths = safe_json_load(report.strengths)
    improvements = safe_json_load(report.improvements)
    
    # Strengths
    elements.append(Paragraph("Strengths", heading2_style))
    if strengths:
        for item in strengths:
            elements.append(Paragraph(f"- {html.escape(str(item))}", bullet_style))
            
    # Areas for Improvement
    elements.append(Paragraph("Areas for Improvement", heading2_style))
    if improvements:
        for item in improvements:
            elements.append(Paragraph(f"- {html.escape(str(item))}", bullet_style))
            
    # Suggestions
    elements.append(Paragraph("Suggestions", heading2_style))
    suggs = report.suggestions
    if isinstance(suggs, list):
        for item in suggs:
            elements.append(Paragraph(f"- {html.escape(str(item))}", bullet_style))
    elif isinstance(suggs, str) and suggs:
        try:
            parsed = json.loads(suggs)
            if isinstance(parsed, list):
                for item in parsed:
                    elements.append(Paragraph(f"- {html.escape(str(item))}", bullet_style))
            else:
                elements.append(Paragraph(f"- {html.escape(suggs)}", bullet_style))
        except Exception:
            elements.append(Paragraph(f"- {html.escape(suggs)}", bullet_style))
        
    elements.append(Spacer(1, 20))
    
    # Interview Questions & Answers
    elements.append(Paragraph("Interview Questions & Answers", heading2_style))
    for sq in questions:
        q_text = html.escape(str(sq.question.text)) if sq.question else "Question"
        ans_text = html.escape(str(sq.answer_text)) if sq.answer_text else "No answer provided"
        feedback = html.escape(str(sq.ai_feedback)) if sq.ai_feedback else "No feedback provided"
        score = sq.score if sq.score is not None else "N/A"
        
        elements.append(Paragraph(f"<b>Q{sq.question_order}:</b> {q_text}", qa_style))
        elements.append(Paragraph(f"<b>Answer:</b> {ans_text}", qa_style))
        elements.append(Paragraph(f"<b>Score: {score}/10 | Feedback:</b> {feedback}", qa_style))
        elements.append(Spacer(1, 10))
        
    doc.build(elements)
    return file_path
