import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

decode_logic = """
    actual_session_id = payload.session_id
    if isinstance(actual_session_id, str):
        try:
            token_data = auth.decode_token(actual_session_id)
            actual_session_id = token_data.get("session_id")
        except Exception:
            pass
"""

# 1. Patch confirm_start
cstart_target = "    session = db.query(models.InterviewSession).filter(\n        models.InterviewSession.id == payload.session_id,"
cstart_replace = decode_logic + "    session = db.query(models.InterviewSession).filter(\n        models.InterviewSession.id == actual_session_id,"
content = content.replace(cstart_target, cstart_replace)

# 2. Patch submit_answer
submit_target = "    session = db.query(models.InterviewSession).filter(\n        models.InterviewSession.id == payload.session_id,"
submit_replace = decode_logic + "    session = db.query(models.InterviewSession).filter(\n        models.InterviewSession.id == actual_session_id,"
content = content.replace(submit_target, submit_replace)

# 3. Patch new end_interview
end_target = "    session = db.query(models.InterviewSession).filter(\n        models.InterviewSession.id == payload.session_id,\n        models.InterviewSession.user_id == current_user.id\n    ).first()"
end_replace = decode_logic + "    session = db.query(models.InterviewSession).filter(\n        models.InterviewSession.id == actual_session_id,\n        models.InterviewSession.user_id == current_user.id\n    ).first()"
content = content.replace(end_target, end_replace)

# 4. Remove old end_interview (lines 1533 to 1561)
old_end_interview = """@app.post("/api/interview/end", response_model=schemas.EndInterviewResponse, summary="Finalize the interview session")
def end_interview(
    payload: schemas.EndInterviewRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    from datetime import datetime

    if payload.userid != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    session = db.query(models.InterviewSession).filter(
        models.InterviewSession.id == payload.session_id,
        models.InterviewSession.user_id == payload.userid
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.ended_at = datetime.utcnow()
    session.status = 'ended'
    db.commit()

    return {
        "success": True,
        "message": "Interview completed successfully."
    }"""
content = content.replace(old_end_interview, '')

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Patched successfully!')
