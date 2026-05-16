from database import SessionLocal, engine
from migration import migrate_schema
from seed import seed_packages

def run():
    print("--- Starting Migration ---")
    migrate_schema(engine)
    print("--- Migration Finished ---")
    
    print("--- Starting Seeding ---")
    db = SessionLocal()
    try:
        seed_packages(db)
    finally:
        db.close()
    print("--- Seeding Finished ---")

if __name__ == "__main__":
    run()
