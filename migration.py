from sqlalchemy import text

def migrate_schema(engine):
    """
    Manually check for missing columns and add them. 
    This is a lightweight alternative to Alembic for this specific task.
    """
    if engine.dialect.name != "postgresql":
        print(f"ℹ️ Skipping manual migration for dialect: {engine.dialect.name}")
        return

    with engine.connect() as conn:
        print("🔍 Checking schema migrations...")
        
        # 1. Update 'users' table
        try:
            # Check if is_approved exists and rename it to is_valid
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='users' AND column_name='is_approved'")).fetchone()
            if res:
                print("🔹 Renaming 'is_approved' -> 'is_valid' in 'users' table...")
                conn.execute(text("ALTER TABLE users RENAME COLUMN is_approved TO is_valid"))
                conn.commit()
            
            # Check if pic exists
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='users' AND column_name='pic'")).fetchone()
            if not res:
                print("🔹 Adding 'pic' column to 'users' table...")
                conn.execute(text("ALTER TABLE users ADD COLUMN pic TEXT"))
                conn.commit()
            # Check if plan exists and rename it to interview_limit
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='users' AND column_name='plan'")).fetchone()
            if res:
                print("🔹 Renaming 'plan' -> 'interview_limit' in 'users' table...")
                conn.execute(text("ALTER TABLE users RENAME COLUMN plan TO interview_limit"))
                conn.commit()

            # Check if tier exists and its type
            res = conn.execute(text("SELECT data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='users' AND column_name='tier'")).fetchone()
            if not res:
                print("🔹 Adding 'tier' column to 'users' table...")
                conn.execute(text("ALTER TABLE users ADD COLUMN tier VARCHAR(10) DEFAULT 'Free' NOT NULL"))
                conn.commit()
            elif res[0] == 'smallint' or res[0] == 'integer':
                print("🔹 Altering 'tier' column to VARCHAR in 'users' table...")
                # First alter column type to varchar
                conn.execute(text("ALTER TABLE users ALTER COLUMN tier DROP DEFAULT"))
                conn.execute(text("ALTER TABLE users ALTER COLUMN tier TYPE VARCHAR(10) USING CASE WHEN tier::text='1' THEN 'Free' WHEN tier::text='2' THEN 'Paid' ELSE 'Free' END"))
                conn.execute(text("ALTER TABLE users ALTER COLUMN tier SET DEFAULT 'Free'"))
                conn.commit()
        except Exception as e:
            print(f"⚠️ 'users' migration note: {e}")

        # 2. Update 'attribute' table
        try:
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='attribute' AND column_name='created_at'")).fetchone()
            if not res:
                print("🔹 Adding timestamps to 'attribute' table...")
                conn.execute(text("ALTER TABLE attribute ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                conn.execute(text("ALTER TABLE attribute ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                conn.commit()
        except Exception as e:
            print(f"⚠️ 'attribute' migration note: {e}")

        # 3. Update 'user_profile' table
        try:
            # Check if attribute_value exists and rename to value
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='user_profile' AND column_name='attribute_value'")).fetchone()
            if res:
                print("🔹 Renaming 'attribute_value' -> 'value' in 'user_profile' table...")
                conn.execute(text("ALTER TABLE user_profile RENAME COLUMN attribute_value TO \"value\""))
                conn.commit()

            # Check if values exists and rename to value
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='user_profile' AND column_name='values'")).fetchone()
            if res:
                print("🔹 Renaming 'values' -> 'value' in 'user_profile' table...")
                conn.execute(text("ALTER TABLE user_profile RENAME COLUMN \"values\" TO \"value\""))
                conn.commit()

            # Drop user_image if exists
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='user_profile' AND column_name='user_image'")).fetchone()
            if res:
                print("🔹 Dropping 'user_image' from 'user_profile' table...")
                conn.execute(text("ALTER TABLE user_profile DROP COLUMN user_image"))
                conn.commit()

            # Drop resume_path if exists
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='user_profile' AND column_name='resume_path'")).fetchone()
            if res:
                print("🔹 Dropping 'resume_path' from 'user_profile' table...")
                conn.execute(text("ALTER TABLE user_profile DROP COLUMN resume_path"))
                conn.commit()

            # Add resume_id FK if missing
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='user_profile' AND column_name='resume_id'")).fetchone()
            if not res:
                print("🔹 Adding 'resume_id' to 'user_profile'...")
                conn.execute(text("ALTER TABLE user_profile ADD COLUMN resume_id INTEGER REFERENCES resumes(id) ON DELETE CASCADE"))
                conn.commit()

            # Add timestamps if missing
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='user_profile' AND column_name='created_at'")).fetchone()
            if not res:
                print("🔹 Adding timestamps to 'user_profile' table...")
                conn.execute(text("ALTER TABLE user_profile ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                conn.execute(text("ALTER TABLE user_profile ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                conn.commit()
        except Exception as e:
            print(f"⚠️ 'user_profile' migration note: {e}")

        # 4. Update 'resumes' table
        try:
            renames = {
                "file_name": "resume_name", 
                "file_path": "path", 
                "file_size": "size", 
                "uploaded_date": "updated_at"
            }
            for old, new in renames.items():
                res = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='resumes' AND column_name='{old}'")).fetchone()
                if res:
                    print(f"🔹 Renaming '{old}' -> '{new}' in 'resumes' table...")
                    conn.execute(text(f"ALTER TABLE resumes RENAME COLUMN {old} TO {new}"))
                    conn.commit()

            # Add domain if missing
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='resumes' AND column_name='domain'")).fetchone()
            if not res:
                print("🔹 Adding 'domain' to 'resumes' table...")
                conn.execute(text("ALTER TABLE resumes ADD COLUMN domain VARCHAR(100)"))
                conn.commit()

            # Add created_at if missing
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='resumes' AND column_name='created_at'")).fetchone()
            if not res:
                print("🔹 Adding 'created_at' to 'resumes' table...")
                conn.execute(text("ALTER TABLE resumes ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                conn.commit()
        except Exception as e:
            print(f"⚠️ 'resumes' migration note: {e}")

        print("✅ Migration checks complete.")
