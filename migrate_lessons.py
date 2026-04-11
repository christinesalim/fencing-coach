"""One-time migration: add new columns to lessons table for R2 support."""
from database import engine
from sqlalchemy import text

with engine.connect() as conn:
    columns = [
        "ALTER TABLE lessons ADD COLUMN r2_object_key VARCHAR(500)",
        "ALTER TABLE lessons ADD COLUMN original_filename VARCHAR(255)",
        "ALTER TABLE lessons ADD COLUMN file_size_bytes INTEGER",
        "ALTER TABLE lessons ADD COLUMN duration_seconds FLOAT",
        "ALTER TABLE lessons ADD COLUMN mime_type VARCHAR(100)",
        "ALTER TABLE lessons ADD COLUMN category VARCHAR(20)",
        "ALTER TABLE lessons ADD COLUMN lesson_date TIMESTAMP",
        "ALTER TABLE lessons ADD COLUMN transcript TEXT",
        "ALTER TABLE lessons ADD COLUMN transcription_status VARCHAR(20) DEFAULT 'pending'",
        "ALTER TABLE lessons ADD COLUMN updated_at TIMESTAMP",
    ]
    for sql in columns:
        try:
            conn.execute(text(sql))
            print(f"OK: {sql}")
        except Exception as e:
            print(f"Skipping (may already exist): {e}")
    conn.commit()
    print("Migration complete.")
