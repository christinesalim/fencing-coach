"""Database models and utilities for fencing tips."""

import os
import json
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
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


class Lesson(Base):
    """Represents a private lesson with video (R2 or legacy YouTube)."""
    __tablename__ = 'lessons'

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)

    # R2 storage fields
    r2_object_key = Column(String(500))
    original_filename = Column(String(255))
    file_size_bytes = Column(Integer)
    duration_seconds = Column(Float)
    mime_type = Column(String(100))

    # Legacy YouTube field (kept for migration)
    youtube_url = Column(String(500))

    # Categorization
    category = Column(String(20))      # 'offense' or 'defense'
    lesson_date = Column(DateTime)

    # Transcription
    transcript = Column(Text)
    transcription_status = Column(String(20), default='pending')

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LessonTag(Base):
    """Represents a tag associated with a lesson."""
    __tablename__ = 'lesson_tags'

    id = Column(Integer, primary_key=True)
    lesson_id = Column(Integer, index=True)
    tag = Column(String(100), nullable=False, index=True)


class Tournament(Base):
    """Represents a fencing tournament."""
    __tablename__ = 'tournaments'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255))
    date = Column(DateTime, nullable=False)
    weapon = Column(String(10), default='epee')
    age_category = Column(String(20), default='Y12')
    level = Column(String(20))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class PoolRound(Base):
    """Tracks performance in a pool round."""
    __tablename__ = 'pool_rounds'

    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, index=True)
    pool_number = Column(Integer)
    position_in_pool = Column(Integer)
    victories = Column(Integer)
    defeats = Column(Integer)
    touches_scored = Column(Integer)
    touches_received = Column(Integer)
    indicator = Column(Integer)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class DEPrepTips(Base):
    """Quick DE prep tips generated from pool results."""
    __tablename__ = 'de_prep_tips'

    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, index=True)
    tips_json = Column(Text)          # JSON array of 5 tip objects
    generated_at = Column(DateTime, default=datetime.utcnow)


class PoolBout(Base):
    """Individual bout within a pool round."""
    __tablename__ = 'pool_bouts'

    id = Column(Integer, primary_key=True)
    pool_round_id = Column(Integer, index=True)
    opponent_name = Column(String(255))
    opponent_club = Column(String(255))
    score_for = Column(Integer)
    score_against = Column(Integer)
    result = Column(String(10))
    bout_order = Column(Integer)
    notes = Column(Text)
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


def get_lessons_from_db():
    """Get all lessons ordered by most recent first."""
    db = get_db()
    try:
        lessons = db.query(Lesson).order_by(Lesson.created_at.desc()).all()
        return [
            {
                'id': l.id,
                'title': l.title,
                'youtube_url': l.youtube_url,
                'description': l.description,
                'created_at': l.created_at.strftime('%B %d, %Y')
            }
            for l in lessons
        ]
    finally:
        db.close()


def add_lesson_to_db(title, youtube_url, description):
    """Add a new lesson."""
    db = get_db()
    try:
        lesson = Lesson(title=title, youtube_url=youtube_url, description=description)
        db.add(lesson)
        db.commit()
        return {
            'id': lesson.id,
            'title': lesson.title,
            'youtube_url': lesson.youtube_url,
            'description': lesson.description,
            'created_at': lesson.created_at.strftime('%B %d, %Y')
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def delete_lesson_from_db(lesson_id):
    """Delete a lesson by id."""
    db = get_db()
    try:
        lesson = db.query(Lesson).filter_by(id=lesson_id).first()
        if lesson:
            db.delete(lesson)
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def restore_data_to_db(data):
    """Restore database from a backup JSON export. Skips duplicates."""
    db = get_db()
    sessions_added = 0
    tips_added = 0

    try:
        # Restore sessions
        for s in data.get('sessions', []):
            existing = db.query(Session).filter_by(
                filename=s['filename'],
                transcript=s.get('transcript', '')
            ).first()
            if not existing:
                session = Session(
                    date=datetime.strptime(s['date'], '%Y-%m-%d %H:%M'),
                    filename=s['filename'],
                    transcript=s.get('transcript', ''),
                    advice_json=json.dumps(s.get('advice', {}))
                )
                db.add(session)
                sessions_added += 1

        # Restore tips
        for category, tips_list in data.get('combined_advice', {}).items():
            for text in tips_list:
                existing = db.query(Tip).filter_by(
                    category=category, text=text
                ).first()
                if not existing:
                    db.add(Tip(category=category, text=text))
                    tips_added += 1

        db.commit()
        return {'sessions_added': sessions_added, 'tips_added': tips_added}

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


def create_tournament(data):
    """Create a new tournament."""
    db = get_db()
    try:
        tournament = Tournament(
            name=data['name'],
            date=datetime.strptime(data['date'], '%Y-%m-%d') if isinstance(data['date'], str) else data['date'],
            location=data.get('location', ''),
            weapon=data.get('weapon', 'epee'),
            age_category=data.get('age_category', 'Y12'),
            level=data.get('level', ''),
            notes=data.get('notes', '')
        )
        db.add(tournament)
        db.commit()
        return {
            'id': tournament.id,
            'name': tournament.name,
            'date': tournament.date.strftime('%Y-%m-%d'),
            'location': tournament.location,
            'weapon': tournament.weapon,
            'age_category': tournament.age_category,
            'level': tournament.level,
            'notes': tournament.notes,
            'created_at': tournament.created_at.strftime('%B %d, %Y')
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_tournaments():
    """Get all tournaments, most recent first."""
    db = get_db()
    try:
        tournaments = db.query(Tournament).order_by(Tournament.date.desc()).all()
        result = []
        for t in tournaments:
            # Check if pool results exist
            pool = db.query(PoolRound).filter_by(tournament_id=t.id).first()
            pool_summary = None
            if pool:
                pool_summary = {
                    'victories': pool.victories,
                    'defeats': pool.defeats,
                    'indicator': pool.indicator,
                    'position_in_pool': pool.position_in_pool
                }
            result.append({
                'id': t.id,
                'name': t.name,
                'date': t.date.strftime('%Y-%m-%d'),
                'location': t.location,
                'weapon': t.weapon,
                'age_category': t.age_category,
                'level': t.level,
                'notes': t.notes,
                'pool_summary': pool_summary,
                'created_at': t.created_at.strftime('%B %d, %Y')
            })
        return result
    finally:
        db.close()


def get_tournament(tournament_id):
    """Get a single tournament by ID."""
    db = get_db()
    try:
        t = db.query(Tournament).filter_by(id=tournament_id).first()
        if not t:
            return None
        return {
            'id': t.id,
            'name': t.name,
            'date': t.date.strftime('%Y-%m-%d'),
            'location': t.location,
            'weapon': t.weapon,
            'age_category': t.age_category,
            'level': t.level,
            'notes': t.notes,
            'created_at': t.created_at.strftime('%B %d, %Y')
        }
    finally:
        db.close()


def update_tournament(tournament_id, data):
    """Update an existing tournament."""
    db = get_db()
    try:
        t = db.query(Tournament).filter_by(id=tournament_id).first()
        if not t:
            return None
        if 'name' in data:
            t.name = data['name']
        if 'date' in data:
            t.date = datetime.strptime(data['date'], '%Y-%m-%d') if isinstance(data['date'], str) else data['date']
        if 'location' in data:
            t.location = data['location']
        if 'weapon' in data:
            t.weapon = data['weapon']
        if 'age_category' in data:
            t.age_category = data['age_category']
        if 'level' in data:
            t.level = data['level']
        if 'notes' in data:
            t.notes = data['notes']
        db.commit()
        return {
            'id': t.id,
            'name': t.name,
            'date': t.date.strftime('%Y-%m-%d'),
            'location': t.location,
            'weapon': t.weapon,
            'age_category': t.age_category,
            'level': t.level,
            'notes': t.notes,
            'created_at': t.created_at.strftime('%B %d, %Y')
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def delete_tournament(tournament_id):
    """Delete a tournament and its pool data and tips."""
    db = get_db()
    try:
        # Delete pool bouts first
        pool_rounds = db.query(PoolRound).filter_by(tournament_id=tournament_id).all()
        for pr in pool_rounds:
            db.query(PoolBout).filter_by(pool_round_id=pr.id).delete()
        db.query(PoolRound).filter_by(tournament_id=tournament_id).delete()
        db.query(DEPrepTips).filter_by(tournament_id=tournament_id).delete()

        t = db.query(Tournament).filter_by(id=tournament_id).first()
        if t:
            db.delete(t)
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def save_pool_results_to_db(tournament_id, pool_data):
    """Save extracted pool results to database."""
    db = get_db()
    try:
        pool_round = PoolRound(
            tournament_id=tournament_id,
            pool_number=pool_data.get('pool_number'),
            position_in_pool=pool_data.get('position_in_pool'),
            victories=pool_data.get('victories'),
            defeats=pool_data.get('defeats'),
            touches_scored=pool_data.get('touches_scored'),
            touches_received=pool_data.get('touches_received'),
            indicator=pool_data.get('indicator'),
            notes=f"Strip {pool_data['strip_number']}" if pool_data.get('strip_number') else None
        )
        db.add(pool_round)
        db.flush()

        for bout in pool_data.get('bouts', []):
            pool_bout = PoolBout(
                pool_round_id=pool_round.id,
                opponent_name=bout.get('opponent_name'),
                opponent_club=bout.get('opponent_club'),
                score_for=bout.get('score_for'),
                score_against=bout.get('score_against'),
                result=bout.get('result'),
                bout_order=bout.get('bout_order')
            )
            db.add(pool_bout)

        db.commit()
        return pool_round.id
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_pool_results(tournament_id):
    """Get pool results for a tournament."""
    db = get_db()
    try:
        pool_round = db.query(PoolRound).filter_by(tournament_id=tournament_id).first()
        if not pool_round:
            return None

        bouts = db.query(PoolBout).filter_by(pool_round_id=pool_round.id).order_by(PoolBout.bout_order).all()

        return {
            'id': pool_round.id,
            'pool_number': pool_round.pool_number,
            'position_in_pool': pool_round.position_in_pool,
            'victories': pool_round.victories,
            'defeats': pool_round.defeats,
            'touches_scored': pool_round.touches_scored,
            'touches_received': pool_round.touches_received,
            'indicator': pool_round.indicator,
            'notes': pool_round.notes,
            'bouts': [
                {
                    'id': b.id,
                    'opponent_name': b.opponent_name,
                    'opponent_club': b.opponent_club,
                    'score_for': b.score_for,
                    'score_against': b.score_against,
                    'result': b.result,
                    'bout_order': b.bout_order,
                    'notes': b.notes
                }
                for b in bouts
            ]
        }
    finally:
        db.close()


# ── Lesson R2 helper functions ─────────────────────────────────────────

def _lesson_to_dict(lesson, tags=None):
    """Convert a Lesson ORM object to a dictionary."""
    d = {
        'id': lesson.id,
        'title': lesson.title,
        'description': lesson.description,
        'r2_object_key': lesson.r2_object_key,
        'original_filename': lesson.original_filename,
        'file_size_bytes': lesson.file_size_bytes,
        'duration_seconds': lesson.duration_seconds,
        'mime_type': lesson.mime_type,
        'youtube_url': lesson.youtube_url,
        'category': lesson.category,
        'lesson_date': lesson.lesson_date.strftime('%Y-%m-%d') if lesson.lesson_date else None,
        'transcript': lesson.transcript,
        'transcription_status': lesson.transcription_status,
        'created_at': lesson.created_at.strftime('%B %d, %Y') if lesson.created_at else None,
        'updated_at': lesson.updated_at.strftime('%B %d, %Y') if lesson.updated_at else None,
    }
    if tags is not None:
        d['tags'] = tags
    return d


def add_lesson_r2(data):
    """Create a lesson with R2 fields, returns dict."""
    db = get_db()
    try:
        lesson = Lesson(
            title=data.get('title', 'Untitled Lesson'),
            description=data.get('description'),
            r2_object_key=data.get('r2_object_key'),
            original_filename=data.get('original_filename'),
            file_size_bytes=data.get('file_size_bytes'),
            duration_seconds=data.get('duration_seconds'),
            mime_type=data.get('mime_type'),
            youtube_url=data.get('youtube_url'),
            category=data.get('category'),
            lesson_date=data.get('lesson_date'),
            transcript=data.get('transcript'),
            transcription_status=data.get('transcription_status', 'pending'),
        )
        db.add(lesson)
        db.commit()

        tags = data.get('tags', [])
        tag_list = []
        if tags:
            for t in tags:
                t_lower = t.strip().lower()
                if not t_lower:
                    continue
                existing = db.query(LessonTag).filter_by(lesson_id=lesson.id, tag=t_lower).first()
                if not existing:
                    db.add(LessonTag(lesson_id=lesson.id, tag=t_lower))
                    tag_list.append(t_lower)
            db.commit()

        return _lesson_to_dict(lesson, tags=tag_list)
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_lessons_filtered(category=None, tag=None, search=None):
    """Get lessons with optional filtering, ordered by lesson_date DESC."""
    db = get_db()
    try:
        query = db.query(Lesson)

        if category:
            query = query.filter(Lesson.category == category)

        if tag:
            tag_lesson_ids = [
                lt.lesson_id for lt in db.query(LessonTag).filter(LessonTag.tag == tag.lower()).all()
            ]
            query = query.filter(Lesson.id.in_(tag_lesson_ids))

        if search:
            search_term = f'%{search}%'
            query = query.filter(
                (Lesson.title.ilike(search_term)) |
                (Lesson.description.ilike(search_term)) |
                (Lesson.transcript.ilike(search_term))
            )

        lessons = query.order_by(Lesson.lesson_date.desc().nullslast(), Lesson.created_at.desc()).all()

        result = []
        for lesson in lessons:
            tags = [lt.tag for lt in db.query(LessonTag).filter_by(lesson_id=lesson.id).all()]
            result.append(_lesson_to_dict(lesson, tags=tags))
        return result
    finally:
        db.close()


def get_lesson(lesson_id):
    """Get a single lesson with tags."""
    db = get_db()
    try:
        lesson = db.query(Lesson).filter_by(id=lesson_id).first()
        if not lesson:
            return None
        tags = [lt.tag for lt in db.query(LessonTag).filter_by(lesson_id=lesson.id).all()]
        return _lesson_to_dict(lesson, tags=tags)
    finally:
        db.close()


def update_lesson(lesson_id, data):
    """Update lesson metadata."""
    db = get_db()
    try:
        lesson = db.query(Lesson).filter_by(id=lesson_id).first()
        if not lesson:
            return None
        if 'title' in data:
            lesson.title = data['title']
        if 'description' in data:
            lesson.description = data['description']
        if 'category' in data:
            lesson.category = data['category']
        if 'lesson_date' in data:
            if isinstance(data['lesson_date'], str) and data['lesson_date']:
                lesson.lesson_date = datetime.strptime(data['lesson_date'], '%Y-%m-%d')
            else:
                lesson.lesson_date = data['lesson_date']
        if 'transcript' in data:
            lesson.transcript = data['transcript']
        if 'transcription_status' in data:
            lesson.transcription_status = data['transcription_status']
        db.commit()
        tags = [lt.tag for lt in db.query(LessonTag).filter_by(lesson_id=lesson.id).all()]
        return _lesson_to_dict(lesson, tags=tags)
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def delete_lesson_r2(lesson_id):
    """Delete a lesson and its tags. Returns the r2_object_key if one existed."""
    db = get_db()
    try:
        lesson = db.query(Lesson).filter_by(id=lesson_id).first()
        if not lesson:
            return None
        r2_key = lesson.r2_object_key
        db.query(LessonTag).filter_by(lesson_id=lesson_id).delete()
        db.delete(lesson)
        db.commit()
        return r2_key
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def add_tags_to_lesson(lesson_id, tags):
    """Add multiple tags to a lesson, skipping duplicates."""
    db = get_db()
    try:
        added = []
        for t in tags:
            t_lower = t.strip().lower()
            if not t_lower:
                continue
            existing = db.query(LessonTag).filter_by(lesson_id=lesson_id, tag=t_lower).first()
            if not existing:
                db.add(LessonTag(lesson_id=lesson_id, tag=t_lower))
                added.append(t_lower)
        db.commit()
        return added
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def remove_tag_from_lesson(lesson_id, tag):
    """Remove a single tag from a lesson."""
    db = get_db()
    try:
        lt = db.query(LessonTag).filter_by(lesson_id=lesson_id, tag=tag.lower()).first()
        if lt:
            db.delete(lt)
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_all_tags():
    """Get all unique tags, ordered alphabetically."""
    db = get_db()
    try:
        tags = db.query(LessonTag.tag).distinct().order_by(LessonTag.tag).all()
        return [t[0] for t in tags]
    finally:
        db.close()


# ── DE Prep Tips helper functions ─────────────────────────────────────

def save_de_prep_tips(tournament_id, tips):
    """Save DE prep tips for a tournament. Replaces any existing tips."""
    db = get_db()
    try:
        # Delete existing tips for this tournament
        db.query(DEPrepTips).filter_by(tournament_id=tournament_id).delete()
        tip_record = DEPrepTips(
            tournament_id=tournament_id,
            tips_json=json.dumps(tips),
            generated_at=datetime.utcnow()
        )
        db.add(tip_record)
        db.commit()
        return {
            'id': tip_record.id,
            'tournament_id': tournament_id,
            'tips': tips,
            'generated_at': tip_record.generated_at.strftime('%b %-d, %-I:%M %p')
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_de_prep_tips(tournament_id):
    """Get saved DE prep tips for a tournament."""
    db = get_db()
    try:
        tip_record = db.query(DEPrepTips).filter_by(tournament_id=tournament_id).first()
        if not tip_record:
            return None
        return {
            'id': tip_record.id,
            'tournament_id': tournament_id,
            'tips': json.loads(tip_record.tips_json),
            'generated_at': tip_record.generated_at.strftime('%b %-d, %-I:%M %p')
        }
    finally:
        db.close()
