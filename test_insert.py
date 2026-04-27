import psycopg2
import sys

db_url = "postgresql://authdb_wer9_user:H2TDpmuvTuXMI5kMzhOwX7dOkAdbXuvR@dpg-d7eenfbeo5us7388c9rg-a.oregon-postgres.render.com:5432/authdb_wer9"

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    # Try to insert a dummy resume to see if it complains about created_at
    cur.execute("INSERT INTO resumes (user_id, resume_name, path, size, mime_type, skills, domain, created_at, updated_at) VALUES (16, 'test', 'test', 100, 'pdf', 'none', 'none', NOW(), NOW())")
    conn.rollback()
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'conn' in locals():
        conn.close()
