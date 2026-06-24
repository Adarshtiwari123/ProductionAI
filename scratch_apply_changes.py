import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = """            if not resume_context_is_empty:
                try:
                    import os, json
                    from groq import Groq
                    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
                    prompt_sys = "You are an expert interview question personalizer and coach. Return ONLY valid JSON. No markdown formatting, no backticks, no explanation."
                    q_input_str = "\\n".join([f"Q{i+1} ({q.difficulty}): {q.text}" for i, q in enumerate(selected_qs)])
                    rule_str = f"1. Rewrite ALL {len(selected_qs)} questions to mention a specific project name, achievement, or skill from the profile."
                    json_keys = ", ".join([f'"q{i+1}": "rewritten q{i+1} here"' for i in range(len(selected_qs))])
                    json_format = f'{{\\n  "personalized": {{{json_keys}}}\\n}}'

                    prompt_user = f\"\"\"Candidate profile:
- Role applying for: {role_from_session}
- Domain/Topic: {topic_from_session}
- Skills: {resume_ctx.skills}
- Projects/Achievements: {', '.join(project_names) if project_names else 'None'}

Questions:
{q_input_str}

Rules:
{rule_str}
2. Generate a question relevant ONLY to the {role_from_session} skillset. You may reference the candidate's resume project names/skills for context, but do not introduce technical concepts outside {role_from_session}'s domain unless those concepts are explicitly present in the candidate's resume/skills list.
3. Keep the same difficulty and intent as the original questions.
4. Try to pick a DIFFERENT resume skill/project reference for each question where possible to avoid repetition.
5. Maximum 1 sentence for each rewritten question.
6. Return ONLY this JSON:
{json_format}\"\"\"
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
                        for i in range(len(selected_qs)):
                            q_key = f"q{i+1}"
                            if q_key in pers:
                                new_q = models.Question(text=pers[q_key], type='resume', difficulty=selected_qs[i].difficulty, role=role_from_session, domain=topic_from_session, is_company_question=False, frequency_score=1)
                                db.add(new_q)
                                db.flush()
                                selected_qs[i] = new_q
                except Exception as e:
                    print("Personalization failed:", e)"""

replacement = """            if not resume_context_is_empty:
                import os, json
                from groq import Groq
                client = Groq(api_key=os.getenv("GROQ_API_KEY"))
                prompt_sys = "You are an expert interview question personalizer and coach. Return ONLY valid JSON. No markdown formatting, no backticks, no explanation."
                q_input_str = "\\n".join([f"Q{i+1} ({q.difficulty}): {q.text}" for i, q in enumerate(selected_qs)])
                rule_str = f"1. Rewrite ALL {len(selected_qs)} questions to mention a specific project name, achievement, or skill from the profile."
                json_keys = ", ".join([f'"q{i+1}": "rewritten q{i+1} here"' for i in range(len(selected_qs))])
                json_format = f'{{\\n  "personalized": {{{json_keys}}}\\n}}'

                prompt_user = f\"\"\"Candidate profile:
- Role applying for: {role_from_session}
- Domain/Topic: {topic_from_session}
- Skills: {resume_ctx.skills}
- Projects/Achievements: {', '.join(project_names) if project_names else 'None'}

Questions:
{q_input_str}

Rules:
{rule_str}
2. Generate a question relevant ONLY to the {role_from_session} skillset and the candidate's actual listed skills/tools. You may reference the candidate's resume project names for context, but NEVER introduce technical concepts, tools, or terminology outside {role_from_session}'s domain (e.g. do not mention machine learning, supervised/unsupervised learning, deep learning, etc. for a Data Analyst role) unless those exact terms appear in the candidate's resume skills list.
3. Keep the same difficulty and intent as the original questions. Keep questions concise to ensure the candidate can complete the interview within the duration limit.
4. Try to pick a DIFFERENT resume skill/project reference for each question where possible to avoid repetition.
5. Maximum 1 sentence for each rewritten question.
6. Return ONLY this JSON:
{json_format}\"\"\"

                ml_terms = ["supervised learning", "unsupervised learning", "neural network", "deep learning", "machine learning model"]
                resume_text_lower = (resume_ctx.skills + " " + resume_ctx.projects + " " + resume_ctx.experience).lower()

                pers = None
                for attempt in range(3):
                    try:
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
                            temp_pers = ai_data["personalized"]
                            valid = True
                            for q_k, q_text in temp_pers.items():
                                q_lower = q_text.lower()
                                for term in ml_terms:
                                    if term in q_lower and term not in resume_text_lower:
                                        valid = False
                                        break
                                if not valid:
                                    break
                            
                            if valid:
                                pers = temp_pers
                                break
                    except Exception as e:
                        print(f"Personalization attempt {attempt+1} failed:", e)

                if pers:
                    for i in range(len(selected_qs)):
                        q_key = f"q{i+1}"
                        if q_key in pers:
                            generated_text = pers[q_key].strip()
                            existing_q = db.query(models.Question).filter(
                                func.lower(models.Question.text) == func.lower(generated_text),
                                func.lower(models.Question.role) == func.lower(role_from_session),
                                func.lower(models.Question.domain) == func.lower(topic_from_session)
                            ).first()
                            
                            if existing_q:
                                selected_qs[i] = existing_q
                            else:
                                new_q = models.Question(
                                    text=generated_text, 
                                    type='resume', 
                                    difficulty=selected_qs[i].difficulty, 
                                    role=role_from_session, 
                                    domain=topic_from_session, 
                                    is_company_question=False, 
                                    frequency_score=1
                                )
                                db.add(new_q)
                                db.flush()
                                selected_qs[i] = new_q"""

if target in content:
    content = content.replace(target, replacement)
    with open('main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully replaced personalization logic!")
else:
    print("Target block not found in main.py")
