"""Database models and utilities for fencing tips."""

import os
import json
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from fuzzy_matching import match_opponent as _match_opponent

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


class EliminationRound(Base):
    """Individual bout in the direct elimination bracket."""
    __tablename__ = 'elimination_rounds'

    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, index=True)
    round_name = Column(String(255))
    opponent_name = Column(String(255))
    opponent_club = Column(String(255))
    opponent_seed = Column(Integer)
    score_for = Column(Integer)
    score_against = Column(Integer)
    result = Column(String(10))
    bout_order = Column(Integer)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class DEBracket(Base):
    """Full DE bracket data stored as JSON."""
    __tablename__ = 'de_brackets'

    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, index=True)
    bracket_size = Column(Integer)
    completeness = Column(String(50))
    bracket_json = Column(Text)
    our_fencer_path_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class DESummary(Base):
    """Post-DE performance summary generated from elimination results."""
    __tablename__ = 'de_summaries'

    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, index=True)
    summary_json = Column(Text)
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


class BoutVideo(Base):
    """Video clip attached to a pool bout or elimination bout. Multiple per bout allowed."""
    __tablename__ = 'bout_videos'

    id = Column(Integer, primary_key=True)
    bout_kind = Column(String(10), nullable=False, index=True)  # 'pool' or 'elim'
    bout_id = Column(Integer, nullable=False, index=True)
    r2_key = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Opponent(Base):
    """Represents a known fencing opponent with traits and encounter history."""
    __tablename__ = 'opponents'

    id = Column(Integer, primary_key=True)
    canonical_name = Column(String(255), nullable=False, index=True)
    first_name = Column(String(100))
    last_name = Column(String(100), index=True)
    name_aliases = Column(Text)       # JSON array of alternative spellings
    club = Column(String(255))
    club_aliases = Column(Text)       # JSON array
    division = Column(String(100))
    handedness = Column(String(10))       # left / right / unknown
    height_category = Column(String(20))  # very_tall / tall / average / short / very_short
    build = Column(String(20))            # stocky / average / lean / athletic
    speed_rating = Column(String(20))     # very_fast / fast / average / slow
    primary_style = Column(String(30))
    secondary_style = Column(String(30))
    photo_url = Column(String(500))
    first_encountered = Column(DateTime)
    last_encountered = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OpponentTacticalNote(Base):
    """Per-opponent tactical observation (weakness, favorite action, tell, etc.)."""
    __tablename__ = 'opponent_tactical_notes'

    id = Column(Integer, primary_key=True)
    opponent_id = Column(Integer, nullable=False, index=True)
    category = Column(String(30))
    observation = Column(Text, nullable=False)
    times_validated = Column(Integer, default=0)
    times_invalidated = Column(Integer, default=0)
    source = Column(String(20), default='manual')
    observed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BoutRecord(Base):
    """Opponent-centric bout history (one row per opponent-bout link)."""
    __tablename__ = 'bout_records'

    id = Column(Integer, primary_key=True)
    opponent_id = Column(Integer, nullable=False, index=True)
    tournament_id = Column(Integer, index=True)
    tournament_name = Column(String(255))
    tournament_date = Column(DateTime, index=True)
    bout_type = Column(String(15))                    # pool / elimination
    pool_bout_id = Column(Integer, index=True)
    elimination_round_id = Column(Integer, index=True)
    score_for = Column(Integer)
    score_against = Column(Integer)
    result = Column(String(5))                        # won / lost
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

# Auto-migrate column widths (PostgreSQL enforces VARCHAR limits, SQLite does not)
if 'postgresql' in get_database_url():
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE elimination_rounds ALTER COLUMN round_name TYPE VARCHAR(255)"))
            conn.execute(text("ALTER TABLE de_brackets ALTER COLUMN completeness TYPE VARCHAR(50)"))
            conn.commit()
    except Exception:
        pass  # Already migrated or table doesn't exist yet

# One-shot migration: copy any existing video_r2_key values (from the single-video
# predecessor of this feature) into the new bout_videos table, then null the column.
# The column itself is left in place — SQLite can't DROP COLUMN cleanly before 3.35.
def _migrate_video_r2_key_to_bout_videos():
    for kind, table in (('pool', 'pool_bouts'), ('elim', 'elimination_rounds')):
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(
                    f"SELECT id, video_r2_key FROM {table} WHERE video_r2_key IS NOT NULL"
                )).fetchall()
                for bout_id, r2_key in rows:
                    exists = conn.execute(text(
                        "SELECT 1 FROM bout_videos WHERE bout_kind=:k AND bout_id=:b AND r2_key=:r"
                    ), {'k': kind, 'b': bout_id, 'r': r2_key}).first()
                    if not exists:
                        conn.execute(text(
                            "INSERT INTO bout_videos (bout_kind, bout_id, r2_key, created_at) "
                            "VALUES (:k, :b, :r, :t)"
                        ), {'k': kind, 'b': bout_id, 'r': r2_key, 't': datetime.utcnow()})
                conn.execute(text(f"UPDATE {table} SET video_r2_key = NULL"))
                conn.commit()
        except Exception:
            pass  # Column doesn't exist (fresh install) or migration already complete

_migrate_video_r2_key_to_bout_videos()


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
    """Delete a tournament and its pool data, DE data, and tips."""
    db = get_db()
    try:
        # Find all the pool_bout and elimination_round IDs that belong to this
        # tournament so we can purge the matching BoutRecord rows too.
        pool_rounds = db.query(PoolRound).filter_by(tournament_id=tournament_id).all()
        pool_bout_ids = []
        for pr in pool_rounds:
            pool_bout_ids.extend(
                b.id for b in db.query(PoolBout).filter_by(pool_round_id=pr.id).all()
            )
        elim_ids = [
            r.id for r in db.query(EliminationRound).filter_by(tournament_id=tournament_id).all()
        ]

        # Purge BoutRecord rows that point into this tournament. This keeps
        # the opponent-centric view consistent with the tournament-centric view.
        if pool_bout_ids:
            db.query(BoutRecord).filter(
                BoutRecord.pool_bout_id.in_(pool_bout_ids)
            ).delete(synchronize_session=False)
        if elim_ids:
            db.query(BoutRecord).filter(
                BoutRecord.elimination_round_id.in_(elim_ids)
            ).delete(synchronize_session=False)
        db.query(BoutRecord).filter_by(tournament_id=tournament_id).delete()

        for pr in pool_rounds:
            db.query(PoolBout).filter_by(pool_round_id=pr.id).delete()
        db.query(PoolRound).filter_by(tournament_id=tournament_id).delete()
        db.query(DEPrepTips).filter_by(tournament_id=tournament_id).delete()

        # Delete DE data and summaries
        db.query(EliminationRound).filter_by(tournament_id=tournament_id).delete()
        db.query(DEBracket).filter_by(tournament_id=tournament_id).delete()
        db.query(DESummary).filter_by(tournament_id=tournament_id).delete()

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
    """Save extracted pool results to database.

    Returns a dict with:
        {'pool_round_id': int, 'opponent_intel': [ {opponent_name, opponent_club,
            action, tier, opponent_id, known, name_score, club_score}, ... ]}

    Opponent intel entries are aligned to the bouts order in ``pool_data['bouts']``.
    An opponent sync failure never aborts the save — the error is logged and the
    bout still gets persisted.
    """
    db = get_db()
    saved_bouts = []  # list of (bout_dict, pool_bout_id)
    pool_round_id = None
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
            db.flush()
            saved_bouts.append((bout, pool_bout.id))

        db.commit()
        pool_round_id = pool_round.id
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

    # After the bouts are committed, sync each to an Opponent record. This
    # runs outside the main transaction so sync failures can't roll back the
    # bout data that's already safely persisted.
    tournament_context = _build_tournament_context(tournament_id)
    opponent_intel = []
    for bout, pool_bout_id in saved_bouts:
        sync_data = {
            'opponent_name': bout.get('opponent_name'),
            'opponent_club': bout.get('opponent_club'),
            'score_for': bout.get('score_for'),
            'score_against': bout.get('score_against'),
            'result': bout.get('result'),
            'pool_bout_id': pool_bout_id,
        }
        summary = sync_bout_to_opponent('pool', sync_data, tournament_context)
        opponent_intel.append(_sync_summary_to_intel(bout, summary))

    return {
        'pool_round_id': pool_round_id,
        'opponent_intel': opponent_intel,
    }


def get_pool_results(tournament_id):
    """Get pool results for a tournament."""
    db = get_db()
    try:
        pool_round = db.query(PoolRound).filter_by(tournament_id=tournament_id).first()
        if not pool_round:
            return None

        bouts = db.query(PoolBout).filter_by(pool_round_id=pool_round.id).order_by(PoolBout.bout_order).all()

        bout_ids = [b.id for b in bouts]
        videos_by_bout = {}
        if bout_ids:
            vids = db.query(BoutVideo).filter(
                BoutVideo.bout_kind == 'pool', BoutVideo.bout_id.in_(bout_ids)
            ).order_by(BoutVideo.created_at).all()
            for v in vids:
                videos_by_bout.setdefault(v.bout_id, []).append({'id': v.id})

        opponent_id_by_bout = {}
        if bout_ids:
            records = db.query(BoutRecord).filter(
                BoutRecord.pool_bout_id.in_(bout_ids)
            ).all()
            for rec in records:
                # First writer wins; duplicates shouldn't exist but be defensive.
                opponent_id_by_bout.setdefault(rec.pool_bout_id, rec.opponent_id)

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
                    'notes': b.notes,
                    'videos': videos_by_bout.get(b.id, []),
                    'opponent_id': opponent_id_by_bout.get(b.id),
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


# ── DE Bracket helper functions ─────────────────────────────────────

def save_de_results_to_db(tournament_id, bracket_data):
    """Save DE bracket results to database. Replaces any existing DE data.

    Returns a dict with:
        {'opponent_intel': [ {opponent_name, opponent_club, action, tier,
            opponent_id, known, name_score, club_score}, ... ]}

    Opponent intel entries are aligned to the (non-BYE) bouts order from
    ``bracket_data['our_fencer']['path']``. Sync failures are logged and skipped;
    they never abort the save.
    """
    db = get_db()
    saved_rounds = []  # list of (bout_dict, elimination_round_id)
    try:
        # Delete existing DE data for this tournament. Also delete any
        # BoutRecord rows that were linked to the old EliminationRound rows —
        # otherwise the new sync would duplicate them.
        old_elim_ids = [
            r.id for r in db.query(EliminationRound).filter_by(tournament_id=tournament_id).all()
        ]
        if old_elim_ids:
            db.query(BoutRecord).filter(
                BoutRecord.elimination_round_id.in_(old_elim_ids)
            ).delete(synchronize_session=False)
        db.query(EliminationRound).filter_by(tournament_id=tournament_id).delete()
        db.query(DEBracket).filter_by(tournament_id=tournament_id).delete()

        # Save our fencer's path as elimination_round records
        our_fencer = bracket_data.get('our_fencer', {})
        for i, bout in enumerate(our_fencer.get('path', [])):
            if (bout.get('opponent_name') or '').upper() == 'BYE':
                continue
            elim_round = EliminationRound(
                tournament_id=tournament_id,
                round_name=(bout.get('round_name') or '')[:255],
                opponent_name=(bout.get('opponent_name') or '')[:255],
                opponent_club=(bout.get('opponent_club') or '')[:255],
                opponent_seed=bout.get('opponent_seed'),
                score_for=bout.get('score_for'),
                score_against=bout.get('score_against'),
                result=bout.get('result'),
                bout_order=i + 1,
                notes=None
            )
            db.add(elim_round)
            db.flush()
            saved_rounds.append((bout, elim_round.id))

        # Save full bracket as JSON
        tournament_bracket = bracket_data.get('tournament_bracket', {})
        de_bracket = DEBracket(
            tournament_id=tournament_id,
            bracket_size=tournament_bracket.get('bracket_size'),
            completeness=str(tournament_bracket.get('completeness', ''))[:50],
            bracket_json=json.dumps(tournament_bracket),
            our_fencer_path_json=json.dumps(our_fencer)
        )
        db.add(de_bracket)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

    # After the elimination rounds are committed, sync each to an Opponent.
    tournament_context = _build_tournament_context(tournament_id)
    opponent_intel = []
    for bout, elim_id in saved_rounds:
        sync_data = {
            'opponent_name': bout.get('opponent_name'),
            'opponent_club': bout.get('opponent_club'),
            'score_for': bout.get('score_for'),
            'score_against': bout.get('score_against'),
            'result': bout.get('result'),
            'elimination_round_id': elim_id,
        }
        summary = sync_bout_to_opponent('elim', sync_data, tournament_context)
        opponent_intel.append(_sync_summary_to_intel(bout, summary))

    return {'opponent_intel': opponent_intel}


def get_de_results(tournament_id):
    """Get DE results for a tournament."""
    db = get_db()
    try:
        de_bracket = db.query(DEBracket).filter_by(tournament_id=tournament_id).first()
        if not de_bracket:
            return None

        elim_rounds = db.query(EliminationRound).filter_by(
            tournament_id=tournament_id
        ).order_by(EliminationRound.bout_order).all()

        our_fencer = json.loads(de_bracket.our_fencer_path_json) if de_bracket.our_fencer_path_json else {}

        bout_ids = [r.id for r in elim_rounds]
        videos_by_bout = {}
        if bout_ids:
            vids = db.query(BoutVideo).filter(
                BoutVideo.bout_kind == 'elim', BoutVideo.bout_id.in_(bout_ids)
            ).order_by(BoutVideo.created_at).all()
            for v in vids:
                videos_by_bout.setdefault(v.bout_id, []).append({'id': v.id})

        opponent_id_by_bout = {}
        if bout_ids:
            records = db.query(BoutRecord).filter(
                BoutRecord.elimination_round_id.in_(bout_ids)
            ).all()
            for rec in records:
                opponent_id_by_bout.setdefault(rec.elimination_round_id, rec.opponent_id)

        return {
            'bracket_size': de_bracket.bracket_size,
            'completeness': de_bracket.completeness,
            'our_fencer': our_fencer,
            'bouts': [
                {
                    'id': r.id,
                    'round_name': r.round_name,
                    'opponent_name': r.opponent_name,
                    'opponent_club': r.opponent_club,
                    'opponent_seed': r.opponent_seed,
                    'score_for': r.score_for,
                    'score_against': r.score_against,
                    'result': r.result,
                    'bout_order': r.bout_order,
                    'videos': videos_by_bout.get(r.id, []),
                    'opponent_id': opponent_id_by_bout.get(r.id),
                }
                for r in elim_rounds
            ]
        }
    finally:
        db.close()


def delete_de_results(tournament_id):
    """Delete DE results for a tournament, including any linked BoutRecord rows."""
    db = get_db()
    try:
        elim_ids = [
            r.id for r in db.query(EliminationRound).filter_by(tournament_id=tournament_id).all()
        ]
        if elim_ids:
            db.query(BoutRecord).filter(
                BoutRecord.elimination_round_id.in_(elim_ids)
            ).delete(synchronize_session=False)
        db.query(EliminationRound).filter_by(tournament_id=tournament_id).delete()
        db.query(DEBracket).filter_by(tournament_id=tournament_id).delete()
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


# ── DE Summary helper functions ─────────────────────────────────────

def save_de_summary(tournament_id, summary):
    """Save DE performance summary for a tournament. Replaces any existing summary."""
    db = get_db()
    try:
        db.query(DESummary).filter_by(tournament_id=tournament_id).delete()
        record = DESummary(
            tournament_id=tournament_id,
            summary_json=json.dumps(summary),
            generated_at=datetime.utcnow()
        )
        db.add(record)
        db.commit()
        return {
            'id': record.id,
            'tournament_id': tournament_id,
            'summary': summary,
            'generated_at': record.generated_at.strftime('%b %-d, %-I:%M %p')
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_de_summary(tournament_id):
    """Get saved DE performance summary for a tournament."""
    db = get_db()
    try:
        record = db.query(DESummary).filter_by(tournament_id=tournament_id).first()
        if not record:
            return None
        return {
            'id': record.id,
            'tournament_id': tournament_id,
            'summary': json.loads(record.summary_json),
            'generated_at': record.generated_at.strftime('%b %-d, %-I:%M %p')
        }
    finally:
        db.close()


# ── Bout video helper functions ─────────────────────────────────────

def bout_exists(bout_kind, bout_id):
    db = get_db()
    try:
        model = PoolBout if bout_kind == 'pool' else EliminationRound
        return db.query(model).filter_by(id=bout_id).first() is not None
    finally:
        db.close()


def add_bout_video(bout_kind, bout_id, r2_key):
    """Create a BoutVideo row; return the new video id."""
    db = get_db()
    try:
        v = BoutVideo(bout_kind=bout_kind, bout_id=bout_id, r2_key=r2_key)
        db.add(v)
        db.commit()
        return v.id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_bout_video(video_id):
    """Return {id, bout_kind, bout_id, r2_key} or None."""
    db = get_db()
    try:
        v = db.query(BoutVideo).filter_by(id=video_id).first()
        if not v:
            return None
        return {'id': v.id, 'bout_kind': v.bout_kind, 'bout_id': v.bout_id, 'r2_key': v.r2_key}
    finally:
        db.close()


def delete_bout_video(video_id):
    """Delete the BoutVideo row; return its r2_key so the caller can purge R2, or None if missing."""
    db = get_db()
    try:
        v = db.query(BoutVideo).filter_by(id=video_id).first()
        if not v:
            return None
        r2_key = v.r2_key
        db.delete(v)
        db.commit()
        return r2_key
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Opponent Intelligence helper functions ─────────────────────────────

def _parse_json_list(value):
    """Deserialize a JSON-encoded list column; tolerate None/empty/invalid."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
        return []
    except (ValueError, TypeError):
        return []


def _serialize_json_list(value):
    """Serialize a list (or None) to JSON text; None stays None for nullable cols."""
    if value is None:
        return None
    if not isinstance(value, list):
        return json.dumps([])
    return json.dumps(value)


def _parse_dt(value):
    """Parse a datetime-like value: pass through datetime, accept ISO / YYYY-MM-DD."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Try full ISO first, then YYYY-MM-DD
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
        try:
            return datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            pass
    return None


def _parse_usfa_name(canonical):
    """Split 'LASTNAME Firstname' (USFA convention) into (first_name, last_name).

    Leading all-uppercase tokens are the surname, the rest is the given name.
    Falls back to natural-order 'First Last' when no caps leader is present.
    Returns (None, None) when canonical is empty or can't be split confidently.
    """
    if not canonical:
        return (None, None)
    tokens = canonical.replace(',', ' ').split()
    if not tokens:
        return (None, None)
    if len(tokens) == 1:
        return (None, tokens[0])
    caps_lead = 0
    for t in tokens:
        if len(t) > 1 and t.isupper():
            caps_lead += 1
        else:
            break
    if caps_lead == 0:
        return (' '.join(tokens[:-1]), tokens[-1])
    if caps_lead == len(tokens):
        return (None, ' '.join(tokens))
    return (' '.join(tokens[caps_lead:]), ' '.join(tokens[:caps_lead]))


def _synthesize_canonical_name(data):
    """If first_name + last_name supplied but no canonical_name, build 'LASTNAME Firstname'."""
    canonical = data.get('canonical_name')
    if canonical:
        return canonical
    first = data.get('first_name')
    last = data.get('last_name')
    if first and last:
        return f'{str(last).upper()} {first}'
    # Fall back to whatever we do have so NOT NULL isn't violated.
    if last:
        return str(last).upper()
    if first:
        return first
    return None


def _opponent_to_dict(opp):
    """Convert an Opponent ORM object to a plain dict with deserialized JSON fields."""
    return {
        'id': opp.id,
        'canonical_name': opp.canonical_name,
        'first_name': opp.first_name,
        'last_name': opp.last_name,
        'name_aliases': _parse_json_list(opp.name_aliases),
        'club': opp.club,
        'club_aliases': _parse_json_list(opp.club_aliases),
        'division': opp.division,
        'handedness': opp.handedness,
        'height_category': opp.height_category,
        'build': opp.build,
        'speed_rating': opp.speed_rating,
        'primary_style': opp.primary_style,
        'secondary_style': opp.secondary_style,
        'photo_url': opp.photo_url,
        'first_encountered': opp.first_encountered.strftime('%Y-%m-%d') if opp.first_encountered else None,
        'last_encountered': opp.last_encountered.strftime('%Y-%m-%d') if opp.last_encountered else None,
        'created_at': opp.created_at.strftime('%Y-%m-%d %H:%M') if opp.created_at else None,
        'updated_at': opp.updated_at.strftime('%Y-%m-%d %H:%M') if opp.updated_at else None,
    }


def _note_to_dict(note):
    """Convert an OpponentTacticalNote to a dict including computed confidence."""
    validated = note.times_validated or 0
    invalidated = note.times_invalidated or 0
    total = validated + invalidated
    confidence = (validated / total) if total > 0 else None
    return {
        'id': note.id,
        'opponent_id': note.opponent_id,
        'category': note.category,
        'observation': note.observation,
        'times_validated': validated,
        'times_invalidated': invalidated,
        'confidence': confidence,
        'source': note.source,
        'observed_at': note.observed_at.strftime('%Y-%m-%d') if note.observed_at else None,
        'created_at': note.created_at.strftime('%Y-%m-%d %H:%M') if note.created_at else None,
        'updated_at': note.updated_at.strftime('%Y-%m-%d %H:%M') if note.updated_at else None,
    }


def _bout_record_to_dict(bout):
    """Convert a BoutRecord to a dict."""
    return {
        'id': bout.id,
        'opponent_id': bout.opponent_id,
        'tournament_id': bout.tournament_id,
        'tournament_name': bout.tournament_name,
        'tournament_date': bout.tournament_date.strftime('%Y-%m-%d') if bout.tournament_date else None,
        'bout_type': bout.bout_type,
        'pool_bout_id': bout.pool_bout_id,
        'elimination_round_id': bout.elimination_round_id,
        'score_for': bout.score_for,
        'score_against': bout.score_against,
        'result': bout.result,
        'notes': bout.notes,
        'created_at': bout.created_at.strftime('%Y-%m-%d %H:%M') if bout.created_at else None,
    }


def create_opponent(data):
    """Create a new opponent. Returns the serialized opponent dict."""
    db = get_db()
    canonical = _synthesize_canonical_name(data)
    first = data.get('first_name')
    last = data.get('last_name')
    if not first and not last and canonical:
        first, last = _parse_usfa_name(canonical)
    try:
        opp = Opponent(
            canonical_name=canonical,
            first_name=first,
            last_name=last,
            name_aliases=_serialize_json_list(data.get('name_aliases')),
            club=data.get('club'),
            club_aliases=_serialize_json_list(data.get('club_aliases')),
            division=data.get('division'),
            handedness=data.get('handedness'),
            height_category=data.get('height_category'),
            build=data.get('build'),
            speed_rating=data.get('speed_rating'),
            primary_style=data.get('primary_style'),
            secondary_style=data.get('secondary_style'),
            photo_url=data.get('photo_url'),
            first_encountered=_parse_dt(data.get('first_encountered')),
            last_encountered=_parse_dt(data.get('last_encountered')),
        )
        db.add(opp)
        db.commit()
        return _opponent_to_dict(opp)
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_opponent(opponent_id):
    """Get a single opponent with its tactical notes populated."""
    db = get_db()
    try:
        opp = db.query(Opponent).filter_by(id=opponent_id).first()
        if not opp:
            return None
        result = _opponent_to_dict(opp)
        notes = db.query(OpponentTacticalNote).filter_by(opponent_id=opp.id).order_by(
            OpponentTacticalNote.created_at.desc()
        ).all()
        result['tactical_notes'] = [_note_to_dict(n) for n in notes]
        return result
    finally:
        db.close()


def update_opponent(opponent_id, data):
    """Update opponent fields. Returns the updated dict, or None if not found."""
    db = get_db()
    try:
        opp = db.query(Opponent).filter_by(id=opponent_id).first()
        if not opp:
            return None

        simple_fields = (
            'first_name', 'last_name', 'club', 'division', 'handedness',
            'height_category', 'build', 'speed_rating', 'primary_style',
            'secondary_style', 'photo_url',
        )
        for field in simple_fields:
            if field in data:
                setattr(opp, field, data[field])

        if 'canonical_name' in data:
            opp.canonical_name = data['canonical_name']
        elif ('first_name' in data or 'last_name' in data):
            # Resynthesize when names change and caller didn't pass a canonical form.
            new_canonical = _synthesize_canonical_name({
                'canonical_name': None,
                'first_name': opp.first_name,
                'last_name': opp.last_name,
            })
            if new_canonical:
                opp.canonical_name = new_canonical

        if 'name_aliases' in data:
            opp.name_aliases = _serialize_json_list(data['name_aliases'])
        if 'club_aliases' in data:
            opp.club_aliases = _serialize_json_list(data['club_aliases'])
        if 'first_encountered' in data:
            opp.first_encountered = _parse_dt(data['first_encountered'])
        if 'last_encountered' in data:
            opp.last_encountered = _parse_dt(data['last_encountered'])

        db.commit()
        return _opponent_to_dict(opp)
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def delete_opponent(opponent_id):
    """Delete an opponent and cascade-delete its tactical notes and bout records."""
    db = get_db()
    try:
        opp = db.query(Opponent).filter_by(id=opponent_id).first()
        if not opp:
            return False
        db.query(OpponentTacticalNote).filter_by(opponent_id=opponent_id).delete()
        db.query(BoutRecord).filter_by(opponent_id=opponent_id).delete()
        db.delete(opp)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_all_opponents():
    """List every opponent as a dict, ordered by canonical_name."""
    db = get_db()
    try:
        opps = db.query(Opponent).order_by(Opponent.canonical_name).all()
        return [_opponent_to_dict(o) for o in opps]
    finally:
        db.close()


def search_opponents_by_name(query):
    """Fuzzy search by name. Returns list of (opponent_dict, score) tuples sorted desc.

    Score is the max of fuzz.ratio / token_sort_ratio / partial_ratio against the
    opponent's canonical_name and any name_aliases. Only entries with score >= 70
    are returned.
    """
    from fuzzy_matching import name_score as _name_score

    if not query or not str(query).strip():
        return []

    opponents = get_all_opponents()
    results = []
    for opp in opponents:
        candidates = [opp['canonical_name']]
        if opp['first_name'] and opp['last_name']:
            candidates.append(f"{opp['first_name']} {opp['last_name']}")
        candidates.extend(opp.get('name_aliases') or [])
        score = _name_score(query, candidates)
        if score >= 70:
            results.append((opp, score))

    results.sort(key=lambda pair: pair[1], reverse=True)
    return results


def search_opponents_by_traits(filters):
    """Filter opponents by trait fields (handedness, height_category, build,
    speed_rating, primary_style, secondary_style, division).
    """
    db = get_db()
    try:
        query = db.query(Opponent)
        filterable = (
            'handedness', 'height_category', 'build', 'speed_rating',
            'primary_style', 'secondary_style', 'division',
        )
        for field in filterable:
            value = filters.get(field) if filters else None
            if value:
                query = query.filter(getattr(Opponent, field) == value)
        opps = query.order_by(Opponent.canonical_name).all()
        return [_opponent_to_dict(o) for o in opps]
    finally:
        db.close()


def add_tactical_note(opponent_id, data):
    """Add a tactical note for an opponent. Returns the note dict."""
    db = get_db()
    try:
        note = OpponentTacticalNote(
            opponent_id=opponent_id,
            category=data.get('category'),
            observation=data.get('observation', ''),
            times_validated=data.get('times_validated', 0) or 0,
            times_invalidated=data.get('times_invalidated', 0) or 0,
            source=data.get('source', 'manual'),
            observed_at=_parse_dt(data.get('observed_at')),
        )
        db.add(note)
        db.commit()
        return _note_to_dict(note)
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def update_tactical_note(note_id, data):
    """Update an existing tactical note. Returns the updated dict or None."""
    db = get_db()
    try:
        note = db.query(OpponentTacticalNote).filter_by(id=note_id).first()
        if not note:
            return None
        if 'category' in data:
            note.category = data['category']
        if 'observation' in data:
            note.observation = data['observation']
        if 'times_validated' in data:
            note.times_validated = data['times_validated'] or 0
        if 'times_invalidated' in data:
            note.times_invalidated = data['times_invalidated'] or 0
        if 'source' in data:
            note.source = data['source']
        if 'observed_at' in data:
            note.observed_at = _parse_dt(data['observed_at'])
        db.commit()
        return _note_to_dict(note)
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def delete_tactical_note(note_id):
    """Delete a tactical note by id."""
    db = get_db()
    try:
        note = db.query(OpponentTacticalNote).filter_by(id=note_id).first()
        if not note:
            return False
        db.delete(note)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def increment_note_validated(note_id):
    """Increment times_validated on a tactical note. Returns the updated note dict or None."""
    db = get_db()
    try:
        note = db.query(OpponentTacticalNote).filter_by(id=note_id).first()
        if not note:
            return None
        note.times_validated = (note.times_validated or 0) + 1
        db.commit()
        return _note_to_dict(note)
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def increment_note_invalidated(note_id):
    """Increment times_invalidated on a tactical note. Returns the updated note dict or None."""
    db = get_db()
    try:
        note = db.query(OpponentTacticalNote).filter_by(id=note_id).first()
        if not note:
            return None
        note.times_invalidated = (note.times_invalidated or 0) + 1
        db.commit()
        return _note_to_dict(note)
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_tactical_notes(opponent_id):
    """Return all tactical notes for an opponent, newest first."""
    db = get_db()
    try:
        notes = db.query(OpponentTacticalNote).filter_by(
            opponent_id=opponent_id
        ).order_by(OpponentTacticalNote.created_at.desc()).all()
        return [_note_to_dict(n) for n in notes]
    finally:
        db.close()


def add_bout_record(opponent_id, data):
    """Add a bout record for an opponent. Returns the record dict."""
    db = get_db()
    try:
        bout = BoutRecord(
            opponent_id=opponent_id,
            tournament_id=data.get('tournament_id'),
            tournament_name=data.get('tournament_name'),
            tournament_date=_parse_dt(data.get('tournament_date')),
            bout_type=data.get('bout_type'),
            pool_bout_id=data.get('pool_bout_id'),
            elimination_round_id=data.get('elimination_round_id'),
            score_for=data.get('score_for'),
            score_against=data.get('score_against'),
            result=data.get('result'),
            notes=data.get('notes'),
        )
        db.add(bout)
        db.commit()
        return _bout_record_to_dict(bout)
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_head_to_head(opponent_id):
    """Aggregate head-to-head record from bout_records.

    Returns {wins, losses, touches_for, touches_against, bouts: [...]}.
    Bouts are sorted newest-first by tournament_date (NULLs last).
    """
    db = get_db()
    try:
        bouts = db.query(BoutRecord).filter_by(opponent_id=opponent_id).all()

        wins = 0
        losses = 0
        touches_for = 0
        touches_against = 0
        for b in bouts:
            touches_for += b.score_for or 0
            touches_against += b.score_against or 0
            if (b.result or '').lower() == 'won':
                wins += 1
            elif (b.result or '').lower() == 'lost':
                losses += 1

        # Sort newest first; NULLs (unknown dates) go last.
        def sort_key(b):
            dt = b.tournament_date
            # Tuple: (has_date flag inverted so dates come before Nones, negative ordinal)
            if dt is None:
                return (1, 0)
            return (0, -dt.toordinal() * 86400 - (dt.hour * 3600 + dt.minute * 60 + dt.second))

        sorted_bouts = sorted(bouts, key=sort_key)

        return {
            'wins': wins,
            'losses': losses,
            'touches_for': touches_for,
            'touches_against': touches_against,
            'bouts': [_bout_record_to_dict(b) for b in sorted_bouts],
        }
    finally:
        db.close()


def lookup_opponents_by_names(name_list):
    """Batch fuzzy-match a list of names against the opponent directory.

    Each `name_list` entry may be either a plain string (name only) or a dict
    with `name` / `club` keys. Returns a list of `{query_name, match}` dicts
    where `match` is the result of `fuzzy_matching.match_opponent`.
    """
    opponents = get_all_opponents()
    results = []
    for entry in name_list or []:
        if isinstance(entry, dict):
            name = entry.get('name') or entry.get('query_name') or ''
            club = entry.get('club') or ''
        else:
            name = entry or ''
            club = ''
        match = _match_opponent(name, club, opponents)
        results.append({'query_name': name, 'match': match})
    return results


# Re-export match_opponent so callers can `from database import match_opponent`.
match_opponent = _match_opponent


# ── Opponent auto-sync (Phase 3) ──────────────────────────────────────

def _build_tournament_context(tournament_id):
    """Assemble the tournament-context dict used by sync_bout_to_opponent.

    Returns {'tournament_id', 'tournament_name', 'tournament_date'} with None
    for any field that can't be resolved.
    """
    if not tournament_id:
        return {'tournament_id': None, 'tournament_name': None, 'tournament_date': None}
    db = get_db()
    try:
        t = db.query(Tournament).filter_by(id=tournament_id).first()
        if not t:
            return {'tournament_id': tournament_id, 'tournament_name': None, 'tournament_date': None}
        return {
            'tournament_id': t.id,
            'tournament_name': t.name,
            'tournament_date': t.date,
        }
    finally:
        db.close()


def _sync_summary_to_intel(bout, summary):
    """Translate a sync_bout_to_opponent summary into the opponent_intel entry
    shape expected by the upload endpoints + tests.
    """
    summary = summary or {}
    action = summary.get('action') or 'skipped'
    return {
        'opponent_name': bout.get('opponent_name'),
        'opponent_club': bout.get('opponent_club'),
        'action': action,
        'tier': summary.get('tier'),
        'opponent_id': summary.get('opponent_id'),
        'known': action == 'auto_link',
        'name_score': summary.get('name_score', 0) or 0,
        'club_score': summary.get('club_score', 0) or 0,
    }


def sync_bout_to_opponent(bout_kind, bout_data, tournament_context):
    """Link a just-saved pool or DE bout to an Opponent record.

    Parameters
    ----------
    bout_kind : str
        ``'pool'`` or ``'elim'``.
    bout_data : dict
        Must contain ``opponent_name`` and ``opponent_club``; plus
        ``score_for`` / ``score_against`` / ``result`` and either
        ``pool_bout_id`` or ``elimination_round_id``.
    tournament_context : dict
        ``{tournament_id, tournament_name, tournament_date}``; any can be ``None``.

    Returns a summary dict:
        {
            'action': 'auto_link' | 'stub_created' | 'skipped',
            'opponent_id': int | None,
            'bout_record_id': int | None,
            'tier': 1-4 | None,
            'name_score': int,
            'club_score': int,
            'error': str (only if action == 'skipped' due to exception),
        }

    Never raises — a sync failure must not break the calling save path.
    """
    try:
        opponent_name = (bout_data or {}).get('opponent_name')
        opponent_club = (bout_data or {}).get('opponent_club')
        if not opponent_name or not str(opponent_name).strip():
            return {
                'action': 'skipped',
                'opponent_id': None,
                'bout_record_id': None,
                'tier': None,
                'name_score': 0,
                'club_score': 0,
            }

        tournament_context = tournament_context or {}
        tournament_id = tournament_context.get('tournament_id')
        tournament_name = tournament_context.get('tournament_name')
        tournament_date = tournament_context.get('tournament_date')
        parsed_date = _parse_dt(tournament_date)

        all_opponents = get_all_opponents()
        match = _match_opponent(opponent_name, opponent_club, all_opponents)

        tier = match.get('tier')
        name_score = int(match.get('name_score') or 0)
        club_score = int(match.get('club_score') or 0)

        opponent_id = None
        action = None

        if tier in (1, 2) and match.get('opponent'):
            # Auto-link to the matched opponent; bump encounter dates.
            opponent_id = match['opponent']['id']
            _touch_opponent_encounter(opponent_id, parsed_date)
            action = 'auto_link'
        else:
            # Tier 3, 4, or None — create a silent stub. A later phase will
            # add a "confirm fuzzy match" UI for Tier 3/4.
            stub = create_opponent({
                'canonical_name': opponent_name,
                'club': opponent_club or None,
                'first_encountered': parsed_date,
                'last_encountered': parsed_date,
            })
            opponent_id = stub['id']
            action = 'stub_created'

        bout_type = 'pool' if bout_kind == 'pool' else 'elimination'
        record_payload = {
            'tournament_id': tournament_id,
            'tournament_name': tournament_name,
            'tournament_date': parsed_date,
            'bout_type': bout_type,
            'pool_bout_id': bout_data.get('pool_bout_id') if bout_kind == 'pool' else None,
            'elimination_round_id': bout_data.get('elimination_round_id') if bout_kind == 'elim' else None,
            'score_for': bout_data.get('score_for'),
            'score_against': bout_data.get('score_against'),
            'result': bout_data.get('result'),
        }
        bout_record = add_bout_record(opponent_id, record_payload)

        return {
            'action': action,
            'opponent_id': opponent_id,
            'bout_record_id': bout_record.get('id') if bout_record else None,
            'tier': tier,
            'name_score': name_score,
            'club_score': club_score,
        }
    except Exception as e:
        # Sync failures never propagate — log and move on.
        print(f"[opponent-sync] failure for bout_kind={bout_kind} "
              f"name={(bout_data or {}).get('opponent_name')!r}: {e}")
        return {
            'action': 'skipped',
            'opponent_id': None,
            'bout_record_id': None,
            'tier': None,
            'name_score': 0,
            'club_score': 0,
            'error': str(e),
        }


def _touch_opponent_encounter(opponent_id, encounter_date):
    """Bump last_encountered (and fill first_encountered if null) on an opponent.

    No-op if ``encounter_date`` is None. Swallows its own errors because it's
    a convenience side-effect of the sync; the sync caller will still record
    the bout.
    """
    if not encounter_date:
        return
    db = get_db()
    try:
        opp = db.query(Opponent).filter_by(id=opponent_id).first()
        if not opp:
            return
        changed = False
        if opp.first_encountered is None or encounter_date < opp.first_encountered:
            opp.first_encountered = encounter_date
            changed = True
        if opp.last_encountered is None or encounter_date > opp.last_encountered:
            opp.last_encountered = encounter_date
            changed = True
        if changed:
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"[opponent-sync] touch_encounter failed for opponent {opponent_id}: {e}")
    finally:
        db.close()
