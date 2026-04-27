import psycopg2
import sys

db_url = "postgresql://authdb_wer9_user:H2TDpmuvTuXMI5kMzhOwX7dOkAdbXuvR@dpg-d7eenfbeo5us7388c9rg-a.oregon-postgres.render.com:5432/authdb_wer9"

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='user_profile';")
    print("Columns in user_profile:")
    for row in cur.fetchall():
        print(row)
        
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='resumes';")
    print("\nColumns in resumes:")
    for row in cur.fetchall():
        print(row)
        
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'conn' in locals():
        conn.close()
