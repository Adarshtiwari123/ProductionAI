from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Render sometimes gives "postgres://", but SQLAlchemy requires "postgresql://"
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Fallback to local SQLite if DATABASE_URL is missing or appears to be an internal Render host
# (Internal hosts like 'dpg-...' don't resolve outside Render's network)
if not DATABASE_URL or "dpg-" in DATABASE_URL:
    print("⚠️  Warning: DATABASE_URL is missing or internal. Falling back to local SQLite: ./interview_ai.db")
    DATABASE_URL = "sqlite:///./interview_ai.db"

# For SQLite, we need 'check_same_thread=False'
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
