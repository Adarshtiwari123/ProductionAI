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
        # 1. Update 'users' table
        try:
            # Check if is_approved exists and rename it
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='is_approved'")).fetchone()
            if res:
                print("✅ Renaming 'is_approved' to 'is_valid' in 'users' table...")
                conn.execute(text("ALTER TABLE users RENAME COLUMN is_approved TO is_valid"))
            
            # Check if pic exists
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='pic'")).fetchone()
            if not res:
                print("✅ Adding 'pic' column to 'users' table...")
                conn.execute(text("ALTER TABLE users ADD COLUMN pic TEXT"))
        except Exception as e:
            print(f"⚠️ Could not migrate 'users' table: {e}")

        # 2. Update 'attribute' table
        try:
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='attribute' AND column_name='created_at'")).fetchone()
            if not res:
                print("✅ Adding 'created_at' and 'updated_at' to 'attribute' table...")
                conn.execute(text("ALTER TABLE attribute ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                conn.execute(text("ALTER TABLE attribute ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
        except Exception as e:
            print(f"⚠️ Could not migrate 'attribute' table: {e}")

        # 3. Update 'user_profile' table (attribute_value -> values)
        try:
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='user_profile' AND column_name='attribute_value'")).fetchone()
            if res:
                print("✅ Renaming 'attribute_value' to 'values' in 'user_profile' table...")
                conn.execute(text("ALTER TABLE user_profile RENAME COLUMN attribute_value TO \"values\""))
            
            # Remove redundant columns
            for col in ["resume_path", "user_image"]:
                res = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name='user_profile' AND column_name='{col}'")).fetchone()
                if res:
                    print(f"✅ Dropping redundant column '{col}' from 'user_profile' table...")
                    conn.execute(text(f"ALTER TABLE user_profile DROP COLUMN {col}"))

            # Add resume_id FK if missing
            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='user_profile' AND column_name='resume_id'")).fetchone()
            if not res:
                print("✅ Adding 'resume_id' FK to 'user_profile' table...")
                conn.execute(text("ALTER TABLE user_profile ADD COLUMN resume_id INTEGER REFERENCES resumes(id) ON DELETE CASCADE"))

            res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='user_profile' AND column_name='created_at'")).fetchone()
            if not res:
                print("✅ Adding 'created_at' and 'updated_at' to 'user_profile' table...")
                conn.execute(text("ALTER TABLE user_profile ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                conn.execute(text("ALTER TABLE user_profile ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
        except Exception as e:
            print(f"⚠️ Could not migrate 'user_profile' table: {e}")

        # 4. Update 'resumes' table
        try:
            # Rename columns if they exist under old names
            renames = {
                "file_name": "resume_name",
                "file_path": "path",
                "file_size": "size",
                "uploaded_date": "updated_at"
            }
            for old, new in renames.items():
                res = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name='resumes' AND column_name='{old}'")).fetchone()
                if res:
                    print(f"✅ Renaming '{old}' to '{new}' in 'resumes' table...")
                    conn.execute(text(f"ALTER TABLE resumes RENAME COLUMN {old} TO {new}"))

            # Add missing columns
            additions = {
                "domain": "VARCHAR(100)",
                "mime_type": "VARCHAR(50) DEFAULT 'application/pdf'",
                "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            }
            for col, dtype in additions.items():
                res = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name='resumes' AND column_name='{col}'")).fetchone()
                if not res:
                    print(f"✅ Adding '{col}' to 'resumes' table...")
                    conn.execute(text(f"ALTER TABLE resumes ADD COLUMN {col} {dtype}"))
        except Exception as e:
            print(f"⚠️ Could not migrate 'resumes' table: {e}")

        conn.commit()
