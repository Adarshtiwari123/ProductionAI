from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path, override=True)

DATABASE_URL = os.getenv("DATABASE_URL")

# Debug print to verify which database is being used
if DATABASE_URL:
    from urllib.parse import urlparse
    parsed = urlparse(DATABASE_URL)
    print(f"[DB] Database connected to: {parsed.hostname} on port {parsed.port}")
else:
    print("[ERROR] No DATABASE_URL found")

# Render sometimes gives "postgres://", but SQLAlchemy requires "postgresql://"
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    raise RuntimeError("[ERROR] DATABASE_URL is not set in the environment or .env file.")

# For SQLite, we need 'check_same_thread=False' (keeping this logic in case of explicit SQLite use)
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
