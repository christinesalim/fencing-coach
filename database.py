"""Database models and utilities for fencing tips."""

import os
import json
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()


class Session(Base):
    """Represents a training session with uploaded audio/video."""
    __tablename__ = 'sessions'

    id = Column(Integer, primary_key=True)
    date = Column(DateTime, default=datetime.utcnow)
    filename = Column(String(255))
    transcript = Column(Text)
    advice_json = Column(Text)  # Store advice as JSON string


class Tip(Base):
    """Represents an individual fencing tip."""
    __tablename__ = 'tips'

    id = Column(Integer, primary_key=True)
    category = Column(String(50), index=True)
    text = Column(Text, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# Database setup
def get_database_url():
    """Get database URL from environment or use SQLite for local dev."""
    db_url = os.environ.get('DATABASE_URL')

    if db_url:
        # Render uses postgres://, but SQLAlchemy needs postgresql://
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        return db_url

    # Fall back to SQLite for local development
    return 'sqlite:///fencing_data.db'


engine = create_engine(get_database_url())
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        return db
    except:
        db.close()
        raise


def load_data_from_db():
    """Load all tips from database in the format expected by the app."""
    db = get_db()

    try:
        # Get all tips organized by category
        tips = db.query(Tip).all()

        combined_advice = {
            "patience_and_control": [],
            "distance_management": [],
            "reading_opponent": [],
            "when_ahead": [],
            "attack_execution": [],
            "defense_and_retreat": []
        }

        for tip in tips:
            if tip.category in combined_advice:
                combined_advice[tip.category].append(tip.text)

        # Get all sessions
        sessions = db.query(Session).order_by(Session.date.desc()).all()
        session_list = []

        for session in sessions:
            session_list.append({
                'date': session.date.strftime('%Y-%m-%d %H:%M'),
                'filename': session.filename,
                'transcript': session.transcript,
                'advice': json.loads(session.advice_json) if session.advice_json else {}
            })

        return {
            "sessions": session_list,
            "combined_advice": combined_advice
        }

    finally:
        db.close()


def save_session_to_db(filename, transcript, advice):
    """Save a new session to the database."""
    db = get_db()

    try:
        # Create session record
        session = Session(
            filename=filename,
            transcript=transcript,
            advice_json=json.dumps(advice)
        )
        db.add(session)

        # Add new tips (skip duplicates)
        for category, points in advice.items():
            for point in points:
                # Check if tip already exists
                existing = db.query(Tip).filter_by(
                    category=category,
                    text=point
                ).first()

                if not existing:
                    tip = Tip(category=category, text=point)
                    db.add(tip)

        db.commit()

        return {
            'date': session.date.strftime('%Y-%m-%d %H:%M'),
            'filename': filename,
            'transcript': transcript,
            'advice': advice
        }

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def update_tip_in_db(category, old_text, new_text):
    """Update a tip in the database."""
    db = get_db()

    try:
        tip = db.query(Tip).filter_by(category=category, text=old_text).first()

        if tip:
            tip.text = new_text
            db.commit()
            return True

        return False

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def delete_tip_from_db(category, text):
    """Delete a tip from the database."""
    db = get_db()

    try:
        tip = db.query(Tip).filter_by(category=category, text=text).first()

        if tip:
            db.delete(tip)
            db.commit()
            return True

        return False

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
