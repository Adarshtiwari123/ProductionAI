import psycopg2
import sys

from dotenv import load_dotenv
import os

load_dotenv()
db_url = os.getenv("DATABASE_URL")

# Render sometimes gives "postgres://", but psycopg2/sqlalchemy requires "postgresql://"
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

if not db_url:
    print("Error: DATABASE_URL not found in .env")
    sys.exit(1)

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
