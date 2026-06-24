import uuid, os
from datetime import datetime
from report_generator import generate_pdf_report
class DummyQuestion:
    def __init__(self, text):
        self.text = text
class DummySQ:
    def __init__(self, order, q_text, a_text, fb, sc):
        self.question_order = order
        self.question = DummyQuestion(q_text)
        self.answer_text = a_text
        self.ai_feedback = fb
        self.score = sc
class DummyUser:
    name = 'Adityaraj'
class DummySession:
    id = 1
    role = 'Data Analyst'
    topic = 'Python'
    started_at = datetime.utcnow()
class DummyReport:
    overall_score = 85
    technical_score = 80
    communication_score = 90
    problem_solving_score = 85
    project_score = 80
    strengths = '["Python", "SQL"]'
    improvements = '["More details needed"]'
    suggestions = 'Great job.'

try:
    path = generate_pdf_report(DummySession(), [DummySQ(1, 'Q1 <script>', 'A1 <script>', 'F1 &', 10)], DummyUser(), DummyReport())
    print('Success:', path)
except Exception as e:
    import traceback
    traceback.print_exc()
