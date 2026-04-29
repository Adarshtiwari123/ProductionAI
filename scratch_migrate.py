from sqlalchemy import text
from database import engine

def main():
    with engine.connect() as conn:
        print("Adding 'plan' column to 'users'...")
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN plan SMALLINT DEFAULT 1"))
            conn.commit()
            print("Successfully added 'plan' column.")
        except Exception as e:
            print(f"Error adding 'plan': {e}")
            conn.rollback()

        print("Updating 'status' column in 'subscriptions' to INTEGER...")
        try:
            conn.execute(text("ALTER TABLE subscriptions ALTER COLUMN status TYPE SMALLINT USING status::smallint"))
            conn.execute(text("ALTER TABLE subscriptions ALTER COLUMN status SET DEFAULT 0"))
            conn.commit()
            print("Successfully updated 'status' column.")
        except Exception as e:
            print(f"Error updating 'status': {e}")
            conn.rollback()

if __name__ == "__main__":
    main()
