import sys

with open('d:/Interview AI new phrase/app/main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if line.strip() == '# Check if questions already exist for this session':
        start_idx = i
    elif line.strip() == '# 5. Build Streamlit redirect URL' and start_idx != -1:
        end_idx = i
        break

if start_idx == -1 or end_idx == -1:
    print("Could not find bounds")
    sys.exit(1)

new_logic = """        # Check if questions already exist for this session
        existing_sqs = db.query(models.SessionQuestion).filter(
            models.SessionQuestion.session_id == session.id
        ).order_by(models.SessionQuestion.question_order).all()
        
        selected_qs = []
        q1_rewritten = False
        q3_rewritten = False

        if len(existing_sqs) > 0:
            selected_qs = [sq.question for sq in existing_sqs if sq.question]
            # Since questions were already generated previously, we just use them.
            # It's possible they were personalized (type='resume'), we can infer flag based on type
            if len(selected_qs) > 0 and selected_qs[0].type == 'resume':
                q1_rewritten = True
            if len(selected_qs) > 2 and selected_qs[2].type == 'resume':
                q3_rewritten = True
        else:
            # Step 2: Fetch question pool & filter
            from sqlalchemy import func
            pool = db.query(models.Question).filter(
                func.lower(models.Question.role) == func.lower(role_from_session),
                func.lower(models.Question.domain) == func.lower(topic_from_session)
            ).all()

            # Step 3: Select exactly 2 easy, 2 medium, 1 hard
            import random
            easy_pool = [q for q in pool if (q.difficulty or '').lower() == 'easy']
            medium_pool = [q for q in pool if (q.difficulty or '').lower() == 'medium']
            hard_pool = [q for q in pool if (q.difficulty or '').lower() == 'hard']

            random.shuffle(easy_pool)
            random.shuffle(medium_pool)
            random.shuffle(hard_pool)

            selected_easy = easy_pool[:2]
            selected_medium = medium_pool[:2]
            selected_hard = hard_pool[:1]

            missing_easy = 2 - len(selected_easy)
            missing_medium = 2 - len(selected_medium)
            missing_hard = 1 - len(selected_hard)

            # Step 4: Generate missing using Groq
            def generate_missing(difficulty, count):
                if count <= 0:
                    return []
                try:
                    import os, json
                    from groq import Groq
                    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
                    prompt = f"You are an expert technical interviewer.\\nGenerate EXACTLY {count} short interview questions for a {difficulty} level {role_from_session} interview.\\nCRITICAL REQUIREMENT: The topic/domain is exclusively {topic_from_session}. Every single question MUST be strictly about {topic_from_session}. DO NOT ask general questions or questions about other topics (e.g. if topic is Python, do NOT ask about SQL).\\nReturn ONLY valid JSON with a key 'questions' containing a list of strings."
                    resp = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "system", "content": prompt}],
                        temperature=0.7,
                        response_format={"type": "json_object"}
                    )
                    gen_data = json.loads(resp.choices[0].message.content)
                    new_texts = gen_data.get("questions", [])
                    generated = []
                    for text in new_texts[:count]:
                        new_q = models.Question(
                            text=text,
                            type='topic',
                            difficulty=difficulty,
                            role=role_from_session,
                            domain=topic_from_session,
                            is_company_question=False,
                            frequency_score=1
                        )
                        db.add(new_q)
                        db.flush() # flush to get id without committing transaction fully
                        generated.append(new_q)
                    return generated
                except Exception as e:
                    print(f"Auto-generate missing {difficulty} questions failed:", e)
                    return []

            selected_easy.extend(generate_missing('easy', missing_easy))
            selected_medium.extend(generate_missing('medium', missing_medium))
            selected_hard.extend(generate_missing('hard', missing_hard))

            # Final fixed order: Easy, Easy, Medium, Medium, Hard
            selected_qs = selected_easy[:2] + selected_medium[:2] + selected_hard[:1]

            # Ensure we have 5 questions
            while len(selected_qs) < 5:
                # Emergency fallback if generation failed
                fallback_q = models.Question(text=f"Can you explain your experience with {topic_from_session}?", type='topic', difficulty='medium', role=role_from_session, domain=topic_from_session, is_company_question=False, frequency_score=1)
                db.add(fallback_q)
                db.flush()
                selected_qs.append(fallback_q)

            # Step 5: Resume Context & Personalization (Q1 & Q3)
            resume_context_is_empty = True
            resume_skills, resume_projects, resume_experience, resume_education = [], [], [], []
            if resume_id:
                profiles = db.query(models.UserProfile).join(models.Attribute).filter(
                    models.UserProfile.user_id == current_user.id,
                    models.UserProfile.resume_id == resume_id,
                    models.Attribute.code.in_([
                        'technical_skills', 'skills', 'projects', 
                        'experience', 'education', 'project_details',
                        'professional_experience', 'achievements', 'key_results'
                    ])
                ).all()
                for p in profiles:
                    if p.value and p.value.strip():
                        if p.attribute.code in ['technical_skills', 'skills']:
                            resume_skills.append(p.value)
                        elif p.attribute.code in ['projects', 'project_details', 'achievements', 'key_results']:
                            resume_projects.append(p.value)
                        elif p.attribute.code in ['experience', 'professional_experience']:
                            resume_experience.append(p.value)
                        elif p.attribute.code in ['education']:
                            resume_education.append(p.value)
            
            class ResumeContext:
                def __init__(self, s, p, e, ed):
                    self.skills = "\\n".join(s) if s else "Not provided"
                    self.projects = "\\n".join(p) if p else "Not provided"
                    self.experience = "\\n".join(e) if e else "Not provided"
                    self.education = "\\n".join(ed) if ed else "Not provided"
                    self.is_empty = not (s or p or e or ed)

            resume_ctx = ResumeContext(resume_skills, resume_projects, resume_experience, resume_education)
            resume_context_is_empty = resume_ctx.is_empty

            def extract_project_names(projects_text):
                lines = projects_text.split('\\n')
                p_names = []
                for line in lines:
                    line = line.strip()
                    if '|' in line:
                        name = line.split('|')[0].strip()
                        if len(name) > 3:
                            p_names.append(name)
                    elif ' - ' in line and len(line) < 60:
                        name = line.split(' - ')[0].strip()
                        if len(name) > 3:
                            p_names.append(name)
                return p_names[:3]

            project_names = extract_project_names(resume_ctx.projects)

            if not resume_context_is_empty:
                try:
                    import os, json
                    from groq import Groq
                    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
                    prompt_sys = "You are an expert interview question personalizer and coach. Return ONLY valid JSON. No markdown formatting, no backticks, no explanation."
                    prompt_user = f\"\"\"Candidate profile:
- Role applying for: {role_from_session}
- Skills: {resume_ctx.skills}
- Projects/Achievements: {', '.join(project_names) if project_names else 'None'}

Questions:
Q1 (Easy): {selected_qs[0].text}
Q3 (Medium): {selected_qs[2].text}

Rules:
1. Rewrite Q1 and Q3 to mention ONE specific project name, achievement, or skill from the profile.
2. Keep the same difficulty and intent as the original questions.
3. Maximum 1 sentence for each rewritten question.
4. Return ONLY this JSON:
{{
  "personalized": {{"q1": "rewritten q1 here", "q3": "rewritten q3 here"}}
}}\"\"\"
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": prompt_sys},
                            {"role": "user", "content": prompt_user}
                        ],
                        temperature=0.3,
                        max_tokens=1000,
                        response_format={"type": "json_object"}
                    )
                    resp_text = response.choices[0].message.content.strip()
                    ai_data = json.loads(resp_text)
                    if "personalized" in ai_data:
                        pers = ai_data["personalized"]
                        if "q1" in pers:
                            new_q1 = models.Question(text=pers["q1"], type='resume', difficulty=selected_qs[0].difficulty, role=role_from_session, domain=topic_from_session, is_company_question=False, frequency_score=1)
                            db.add(new_q1)
                            db.flush()
                            selected_qs[0] = new_q1
                            q1_rewritten = True
                        if "q3" in pers:
                            new_q3 = models.Question(text=pers["q3"], type='resume', difficulty=selected_qs[2].difficulty, role=role_from_session, domain=topic_from_session, is_company_question=False, frequency_score=1)
                            db.add(new_q3)
                            db.flush()
                            selected_qs[2] = new_q3
                            q3_rewritten = True
                except Exception as e:
                    print("AI personalization failed:", e)

            # Step 6: INSERT into session_questions
            for idx, q in enumerate(selected_qs):
                sq = models.SessionQuestion(
                    session_id=session.id,
                    question_id=q.id,
                    question_order=idx + 1,
                    answer_text=None,
                    score=None,
                    ai_feedback=None,
                    is_skipped=False
                )
                db.add(sq)
            db.commit()

        # Build questions_list and ai_greeting
        questions_list = []
        for idx, q in enumerate(selected_qs):
            is_rb = (idx == 0 and q1_rewritten) or (idx == 2 and q3_rewritten)
            questions_list.append({
                "order": idx + 1,
                "question": q.text,
                "difficulty": q.difficulty or "medium",
                "resume_based": is_rb,
                "tip": "Provide a clear explanation."
            })

        first_name = current_user.name.split(' ')[0]
        # Resolve project_names locally for the greeting
        project_names = []
        if resume_id:
            projects_profile = db.query(models.UserProfile).join(models.Attribute).filter(
                models.UserProfile.user_id == current_user.id,
                models.UserProfile.resume_id == resume_id,
                models.Attribute.code.in_(['projects', 'project_details', 'achievements', 'key_results'])
            ).all()
            p_text = "\\n".join([p.value for p in projects_profile if p.value and p.value.strip()])
            if p_text:
                lines = p_text.split('\\n')
                for line in lines:
                    line = line.strip()
                    if '|' in line and len(line.split('|')[0].strip()) > 3:
                        project_names.append(line.split('|')[0].strip())
                    elif ' - ' in line and len(line) < 60 and len(line.split(' - ')[0].strip()) > 3:
                        project_names.append(line.split(' - ')[0].strip())
                project_names = project_names[:3]

        if len(project_names) > 0:
            project_mention = f"I can see you have worked on {' and '.join(project_names[:2])}"
        else:
            project_mention = f"I can see your background in {topic_from_session}"

        ai_greeting = f"Hello {first_name}! Welcome to your {role_from_session} interview. {project_mention} — let us see how deep your knowledge goes today. We will focus on {topic_from_session}. I will ask you {session.total_questions} questions and give you feedback after each answer. Let us begin. {selected_qs[0].text if selected_qs else ''}"

        system_prompt = f"You are a strict MNC technical interviewer at a top company conducting a real {role_from_session} interview.\\nAsk exactly ONE question at a time.\\nTopic focus: {topic_from_session}. Difficulty: {difficulty_from_session}. Total questions: {session.total_questions}."
        conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "assistant", "content": ai_greeting}
        ]

"""

lines = lines[:start_idx] + [new_logic] + lines[end_idx:]

with open('d:/Interview AI new phrase/app/main.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Replacement successful")
