from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from app.scoring import calculate_score


UTC = timezone.utc


def utcnow() -> str:
    return datetime.now(tz=UTC).isoformat()


class Database:
    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._init_db()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_user_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    display_name TEXT,
                    age TEXT,
                    role TEXT,
                    industry TEXT,
                    location TEXT,
                    bio TEXT,
                    languages TEXT,
                    company TEXT,
                    skills TEXT,
                    avatar_file_id TEXT,
                    external_links TEXT,
                    external_links_consent INTEGER NOT NULL DEFAULT 0,
                    linkedin_url TEXT,
                    profile_status TEXT NOT NULL DEFAULT 'draft',
                    open_to_intro INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS preferences (
                    user_id INTEGER PRIMARY KEY,
                    contact_types TEXT,
                    industries TEXT,
                    roles TEXT,
                    geography TEXT,
                    interaction_formats TEXT,
                    topics TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS privacy_settings (
                    user_id INTEGER PRIMARY KEY,
                    visibility TEXT NOT NULL DEFAULT 'all',
                    who_can_intro TEXT NOT NULL DEFAULT 'all',
                    show_company INTEGER NOT NULL DEFAULT 1,
                    show_linkedin INTEGER NOT NULL DEFAULT 1,
                    show_location INTEGER NOT NULL DEFAULT 1,
                    messages_after_match INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS linkedin_verifications (
                    user_id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'not_started',
                    profile_url TEXT,
                    verified_name TEXT,
                    verified_title TEXT,
                    verified_company TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS recommendation_events (
                    viewer_user_id INTEGER NOT NULL,
                    candidate_user_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(viewer_user_id, candidate_user_id),
                    FOREIGN KEY(viewer_user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(candidate_user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS intros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_user_id INTEGER NOT NULL,
                    recipient_user_id INTEGER NOT NULL,
                    intro_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(sender_user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(recipient_user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user1_id INTEGER NOT NULL,
                    user2_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user1_id, user2_id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id INTEGER NOT NULL,
                    sender_user_id INTEGER NOT NULL,
                    recipient_user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    telegram_message_id INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(match_id) REFERENCES matches(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS complaints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reporter_user_id INTEGER NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id INTEGER,
                    reason TEXT NOT NULL,
                    comment TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    admin_note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    FOREIGN KEY(reporter_user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_blocks (
                    blocker_user_id INTEGER NOT NULL,
                    blocked_user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(blocker_user_id, blocked_user_id),
                    FOREIGN KEY(blocker_user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(blocked_user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    event_type TEXT NOT NULL,
                    context_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_user_id INTEGER UNIQUE,
                    username TEXT UNIQUE,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    added_by_tg_user_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "complaints", "status", "TEXT NOT NULL DEFAULT 'open'")
            self._ensure_column(conn, "complaints", "admin_note", "TEXT")
            self._ensure_column(conn, "complaints", "updated_at", "TEXT")
            self._ensure_column(conn, "users", "age", "TEXT")
            self._ensure_column(conn, "users", "external_links_consent", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "admins", "tg_user_id", "INTEGER UNIQUE")
            self._ensure_column(conn, "admins", "username", "TEXT UNIQUE")
            self._ensure_column(conn, "admins", "is_active", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "admins", "added_by_tg_user_id", "INTEGER")
            self._ensure_column(conn, "admins", "created_at", "TEXT")
            self._ensure_column(conn, "admins", "updated_at", "TEXT")

    def _ensure_column(self, conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        existing_columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name in existing_columns:
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _get_user_id(self, conn: sqlite3.Connection, tg_user_id: int) -> int | None:
        row = conn.execute(
            "SELECT id FROM users WHERE tg_user_id = ?",
            (tg_user_id,),
        ).fetchone()
        return int(row["id"]) if row else None

    def upsert_telegram_user(self, tg_user_id: int, username: str | None, display_name: str) -> None:
        now = utcnow()
        with self.connection() as conn:
            existing = conn.execute(
                "SELECT id FROM users WHERE tg_user_id = ?",
                (tg_user_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE users
                    SET username = ?, display_name = COALESCE(display_name, ?), updated_at = ?
                    WHERE tg_user_id = ?
                    """,
                    (username, display_name, now, tg_user_id),
                )
                if username:
                    conn.execute(
                        """
                        UPDATE admins
                        SET tg_user_id = ?, updated_at = ?
                        WHERE LOWER(username) = LOWER(?) AND is_active = 1
                        """,
                        (tg_user_id, now, username),
                    )
                return

            conn.execute(
                """
                INSERT INTO users (
                    tg_user_id, username, display_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (tg_user_id, username, display_name, now, now),
            )
            user_id = self._get_user_id(conn, tg_user_id)
            conn.execute(
                "INSERT OR IGNORE INTO preferences (user_id, updated_at) VALUES (?, ?)",
                (user_id, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO privacy_settings (user_id, updated_at) VALUES (?, ?)",
                (user_id, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO linkedin_verifications (user_id, updated_at) VALUES (?, ?)",
                (user_id, now),
            )
            if username:
                conn.execute(
                    """
                    UPDATE admins
                    SET tg_user_id = ?, updated_at = ?
                    WHERE LOWER(username) = LOWER(?) AND is_active = 1
                    """,
                    (tg_user_id, now, username),
                )

    def seed_admin_ids(self, admin_ids: set[int]) -> None:
        now = utcnow()
        with self.connection() as conn:
            for tg_user_id in admin_ids:
                existing_user = conn.execute(
                    "SELECT username FROM users WHERE tg_user_id = ?",
                    (tg_user_id,),
                ).fetchone()
                username = existing_user["username"] if existing_user else None
                conn.execute(
                    """
                    INSERT INTO admins (tg_user_id, username, is_active, created_at, updated_at)
                    VALUES (?, ?, 1, ?, ?)
                    ON CONFLICT(tg_user_id) DO UPDATE SET
                        username = COALESCE(excluded.username, admins.username),
                        is_active = 1,
                        updated_at = excluded.updated_at
                    """,
                    (tg_user_id, username, now, now),
                )

    def get_admin_ids(self) -> set[int]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT tg_user_id FROM admins WHERE is_active = 1 AND tg_user_id IS NOT NULL"
            ).fetchall()
            return {int(row["tg_user_id"]) for row in rows}

    def is_admin_user(self, tg_user_id: int, username: str | None = None) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM admins
                WHERE is_active = 1
                  AND (
                    tg_user_id = ?
                    OR (? IS NOT NULL AND LOWER(username) = LOWER(?))
                  )
                LIMIT 1
                """,
                (tg_user_id, username, username),
            ).fetchone()
            return bool(row)

    def add_admin_by_username(self, username: str, added_by_tg_user_id: int) -> dict:
        normalized = username.strip().lstrip("@").lower()
        if not normalized:
            raise ValueError("Username is empty")

        now = utcnow()
        with self.connection() as conn:
            user = conn.execute(
                "SELECT tg_user_id, username, display_name FROM users WHERE LOWER(username) = LOWER(?)",
                (normalized,),
            ).fetchone()
            tg_user_id = int(user["tg_user_id"]) if user and user["tg_user_id"] is not None else None
            display_name = user["display_name"] if user else None

            existing = conn.execute(
                "SELECT id, tg_user_id, username, is_active FROM admins WHERE LOWER(username) = LOWER(?)",
                (normalized,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE admins
                    SET tg_user_id = COALESCE(?, tg_user_id),
                        is_active = 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (tg_user_id, now, existing["id"]),
                )
                admin_id = int(existing["id"])
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO admins (tg_user_id, username, is_active, added_by_tg_user_id, created_at, updated_at)
                    VALUES (?, ?, 1, ?, ?, ?)
                    """,
                    (tg_user_id, normalized, added_by_tg_user_id, now, now),
                )
                admin_id = int(cursor.lastrowid)

            row = conn.execute(
                "SELECT * FROM admins WHERE id = ?",
                (admin_id,),
            ).fetchone()
            result = dict(row)
            result["display_name"] = display_name
            return result

    def list_admins(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    a.*,
                    u.display_name
                FROM admins a
                LEFT JOIN users u ON u.tg_user_id = a.tg_user_id
                WHERE a.is_active = 1
                ORDER BY a.created_at ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_user_profile(self, tg_user_id: int) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE tg_user_id = ?",
                (tg_user_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_profile_field(self, tg_user_id: int, field: str, value: str | None) -> None:
        allowed_fields = {
            "display_name",
            "age",
            "role",
            "industry",
            "location",
            "bio",
            "languages",
            "company",
            "skills",
            "external_links",
            "avatar_file_id",
            "linkedin_url",
        }
        if field not in allowed_fields:
            raise ValueError(f"Unsupported field: {field}")
        with self.connection() as conn:
            conn.execute(
                f"UPDATE users SET {field} = ?, updated_at = ? WHERE tg_user_id = ?",
                (value, utcnow(), tg_user_id),
            )

    def set_profile_status(self, tg_user_id: int, status: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE users SET profile_status = ?, updated_at = ? WHERE tg_user_id = ?",
                (status, utcnow(), tg_user_id),
            )

    def has_external_links_consent(self, tg_user_id: int) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT external_links_consent FROM users WHERE tg_user_id = ?",
                (tg_user_id,),
            ).fetchone()
            return bool(row and int(row["external_links_consent"]))

    def set_external_links_consent(self, tg_user_id: int, accepted: bool = True) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE users SET external_links_consent = ?, updated_at = ? WHERE tg_user_id = ?",
                (1 if accepted else 0, utcnow(), tg_user_id),
            )

    def cycle_profile_status(self, tg_user_id: int) -> str:
        order = ["draft", "active", "hidden"]
        with self.connection() as conn:
            row = conn.execute(
                "SELECT profile_status FROM users WHERE tg_user_id = ?",
                (tg_user_id,),
            ).fetchone()
            current = row["profile_status"] if row else "draft"
            next_status = order[(order.index(current) + 1) % len(order)]
            conn.execute(
                "UPDATE users SET profile_status = ?, updated_at = ? WHERE tg_user_id = ?",
                (next_status, utcnow(), tg_user_id),
            )
            return next_status

    def minimum_profile_completed(self, tg_user_id: int) -> bool:
        user = self.get_user_profile(tg_user_id)
        if not user:
            return False
        required = ["display_name", "age", "role", "company", "bio", "avatar_file_id"]
        return all((user.get(field) or "").strip() for field in required)

    def get_preferences(self, tg_user_id: int) -> dict | None:
        with self.connection() as conn:
            user_id = self._get_user_id(conn, tg_user_id)
            if not user_id:
                return None
            row = conn.execute(
                "SELECT * FROM preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_preference_field(self, tg_user_id: int, field: str, value: str | int) -> None:
        allowed = {
            "contact_types",
            "industries",
            "roles",
            "geography",
            "interaction_formats",
            "topics",
        }
        if field not in allowed:
            raise ValueError(f"Unsupported preference field: {field}")
        with self.connection() as conn:
            user_id = self._get_user_id(conn, tg_user_id)
            conn.execute(
                f"UPDATE preferences SET {field} = ?, updated_at = ? WHERE user_id = ?",
                (value, utcnow(), user_id),
            )

    def is_registration_complete(self, tg_user_id: int) -> bool:
        with self.connection() as conn:
            user_id = self._get_user_id(conn, tg_user_id)
            if not user_id:
                return False

            completed_event = conn.execute(
                """
                SELECT 1
                FROM events
                WHERE user_id = ? AND event_type = 'onboarding_completed'
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if completed_event:
                return True

            user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            preferences = conn.execute("SELECT * FROM preferences WHERE user_id = ?", (user_id,)).fetchone()
            if not user or not preferences:
                return False

            profile_fields = [
                "display_name",
                "age",
                "role",
                "bio",
                "company",
                "avatar_file_id",
            ]
            preference_fields = [
                "roles",
            ]

            profile_ok = all((user[field] or "").strip() for field in profile_fields)
            preferences_ok = all((preferences[field] or "").strip() for field in preference_fields)
            return profile_ok and preferences_ok and user["profile_status"] in {"active", "hidden"}

    def toggle_open_to_intro(self, tg_user_id: int) -> int:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT open_to_intro FROM users WHERE tg_user_id = ?",
                (tg_user_id,),
            ).fetchone()
            next_value = 0 if row and int(row["open_to_intro"]) else 1
            conn.execute(
                "UPDATE users SET open_to_intro = ?, updated_at = ? WHERE tg_user_id = ?",
                (next_value, utcnow(), tg_user_id),
            )
            return next_value

    def get_privacy(self, tg_user_id: int) -> dict | None:
        with self.connection() as conn:
            user_id = self._get_user_id(conn, tg_user_id)
            if not user_id:
                return None
            row = conn.execute(
                "SELECT * FROM privacy_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def cycle_privacy_value(self, tg_user_id: int, field: str) -> str:
        visibility_values = ["all", "recommendations_only", "intro_only", "hidden"]
        intro_values = ["all", "matching_only", "linkedin_only"]
        with self.connection() as conn:
            user_id = self._get_user_id(conn, tg_user_id)
            row = conn.execute(
                "SELECT visibility, who_can_intro FROM privacy_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if field == "visibility":
                current = row["visibility"]
                next_value = visibility_values[(visibility_values.index(current) + 1) % len(visibility_values)]
                conn.execute(
                    "UPDATE privacy_settings SET visibility = ?, updated_at = ? WHERE user_id = ?",
                    (next_value, utcnow(), user_id),
                )
                return next_value
            if field == "who_can_intro":
                current = row["who_can_intro"]
                next_value = intro_values[(intro_values.index(current) + 1) % len(intro_values)]
                conn.execute(
                    "UPDATE privacy_settings SET who_can_intro = ?, updated_at = ? WHERE user_id = ?",
                    (next_value, utcnow(), user_id),
                )
                return next_value
            raise ValueError(f"Unsupported cycle field: {field}")

    def toggle_privacy_flag(self, tg_user_id: int, field: str) -> int:
        allowed = {
            "show_company",
            "show_linkedin",
            "show_location",
            "messages_after_match",
        }
        if field not in allowed:
            raise ValueError(f"Unsupported privacy field: {field}")
        with self.connection() as conn:
            user_id = self._get_user_id(conn, tg_user_id)
            row = conn.execute(
                f"SELECT {field} FROM privacy_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            next_value = 0 if row and int(row[field]) else 1
            conn.execute(
                f"UPDATE privacy_settings SET {field} = ?, updated_at = ? WHERE user_id = ?",
                (next_value, utcnow(), user_id),
            )
            return next_value

    def get_linkedin(self, tg_user_id: int) -> dict | None:
        with self.connection() as conn:
            user_id = self._get_user_id(conn, tg_user_id)
            if not user_id:
                return None
            row = conn.execute(
                "SELECT * FROM linkedin_verifications WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def submit_linkedin(self, tg_user_id: int, profile_url: str) -> None:
        with self.connection() as conn:
            user_id = self._get_user_id(conn, tg_user_id)
            now = utcnow()
            conn.execute(
                """
                UPDATE linkedin_verifications
                SET status = 'pending', profile_url = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (profile_url, now, user_id),
            )
            conn.execute(
                "UPDATE users SET linkedin_url = ?, updated_at = ? WHERE id = ?",
                (profile_url, now, user_id),
            )

    def set_linkedin_status(self, user_id: int, status: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE linkedin_verifications SET status = ?, updated_at = ? WHERE user_id = ?",
                (status, utcnow(), user_id),
            )

    def pending_linkedin_requests(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT u.id, u.tg_user_id, u.display_name, l.profile_url, l.status, l.updated_at
                FROM linkedin_verifications l
                JOIN users u ON u.id = l.user_id
                WHERE l.status = 'pending'
                ORDER BY l.updated_at ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def list_open_complaints(self, limit: int = 20) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.*,
                    u.tg_user_id AS reporter_tg_user_id,
                    u.display_name AS reporter_name,
                    u.username AS reporter_username
                FROM complaints c
                JOIN users u ON u.id = c.reporter_user_id
                WHERE c.status = 'open'
                ORDER BY c.created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_complaint(self, complaint_id: int) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    c.*,
                    u.tg_user_id AS reporter_tg_user_id,
                    u.display_name AS reporter_name,
                    u.username AS reporter_username
                FROM complaints c
                JOIN users u ON u.id = c.reporter_user_id
                WHERE c.id = ?
                """,
                (complaint_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_complaint_status(self, complaint_id: int, status: str, admin_note: str | None = None) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE complaints
                SET status = ?, admin_note = COALESCE(?, admin_note), updated_at = ?
                WHERE id = ?
                """,
                (status, admin_note, utcnow(), complaint_id),
            )

    def get_user_by_internal_id(self, user_id: int) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def record_event(self, tg_user_id: int | None, event_type: str, context: dict | None = None) -> None:
        with self.connection() as conn:
            user_id = self._get_user_id(conn, tg_user_id) if tg_user_id else None
            conn.execute(
                """
                INSERT INTO events (user_id, event_type, context_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, event_type, json.dumps(context or {}, ensure_ascii=False), utcnow()),
            )

    def get_dashboard_stats(self) -> dict:
        with self.connection() as conn:
            def scalar(query: str) -> int:
                row = conn.execute(query).fetchone()
                return int(next(iter(row))) if row else 0

            return {
                "bot_starts": scalar("SELECT COUNT(*) FROM events WHERE event_type = 'bot_started'"),
                "onboardings_completed": scalar("SELECT COUNT(*) FROM events WHERE event_type = 'onboarding_completed'"),
                "active_profiles": scalar("SELECT COUNT(*) FROM users WHERE profile_status = 'active'"),
                "preferences_completed": scalar("SELECT COUNT(*) FROM preferences WHERE roles IS NOT NULL AND TRIM(roles) != ''"),
                "recommendations_shown": scalar("SELECT COUNT(*) FROM events WHERE event_type = 'recommendation_shown'"),
                "intros_sent": scalar("SELECT COUNT(*) FROM intros"),
                "matches_created": scalar("SELECT COUNT(*) FROM matches"),
                "message_threads_started": scalar("SELECT COUNT(DISTINCT match_id) FROM messages"),
                "complaints": scalar("SELECT COUNT(*) FROM complaints"),
                "linkedin_verified": scalar("SELECT COUNT(*) FROM linkedin_verifications WHERE status = 'verified'"),
            }

    def _is_blocked(self, conn: sqlite3.Connection, user_id: int, candidate_id: int) -> bool:
        row = conn.execute(
            """
            SELECT 1
            FROM user_blocks
            WHERE (blocker_user_id = ? AND blocked_user_id = ?)
               OR (blocker_user_id = ? AND blocked_user_id = ?)
            """,
            (user_id, candidate_id, candidate_id, user_id),
        ).fetchone()
        return bool(row)

    def get_recommendations(self, tg_user_id: int, limit: int = 10) -> list[dict]:
        with self.connection() as conn:
            viewer_id = self._get_user_id(conn, tg_user_id)
            if not viewer_id:
                return []

            viewer = conn.execute("SELECT * FROM users WHERE id = ?", (viewer_id,)).fetchone()
            viewer_pref = conn.execute("SELECT * FROM preferences WHERE user_id = ?", (viewer_id,)).fetchone()
            if not viewer or not viewer_pref:
                return []

            rows = conn.execute(
                """
                SELECT
                    u.*,
                    p.contact_types, p.industries AS pref_industries, p.roles AS pref_roles,
                    p.geography, p.interaction_formats, p.topics,
                    ps.visibility, ps.who_can_intro, ps.show_company, ps.show_linkedin, ps.show_location,
                    lv.status AS linkedin_status
                FROM users u
                JOIN preferences p ON p.user_id = u.id
                JOIN privacy_settings ps ON ps.user_id = u.id
                LEFT JOIN linkedin_verifications lv ON lv.user_id = u.id
                WHERE u.id != ?
                  AND u.profile_status = 'active'
                  AND u.open_to_intro = 1
                  AND ps.visibility IN ('all', 'recommendations_only')
                """,
                (viewer_id,),
            ).fetchall()

            recommendations: list[dict] = []
            for row in rows:
                candidate = dict(row)
                candidate_id = int(candidate["id"])

                if self._is_blocked(conn, viewer_id, candidate_id):
                    continue

                seen = conn.execute(
                    """
                    SELECT status
                    FROM recommendation_events
                    WHERE viewer_user_id = ? AND candidate_user_id = ?
                    """,
                    (viewer_id, candidate_id),
                ).fetchone()
                if seen and seen["status"] in {"shown", "skipped", "reported", "intro_sent"}:
                    continue

                active_match = conn.execute(
                    """
                    SELECT 1
                    FROM matches
                    WHERE ((user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?))
                      AND status IN ('active', 'muted')
                    """,
                    (viewer_id, candidate_id, candidate_id, viewer_id),
                ).fetchone()
                if active_match:
                    continue

                pending_intro = conn.execute(
                    """
                    SELECT 1
                    FROM intros
                    WHERE ((sender_user_id = ? AND recipient_user_id = ?) OR (sender_user_id = ? AND recipient_user_id = ?))
                      AND status = 'pending'
                    """,
                    (viewer_id, candidate_id, candidate_id, viewer_id),
                ).fetchone()
                if pending_intro:
                    continue

                candidate_pref = {
                    "industries": candidate.get("pref_industries"),
                    "roles": candidate.get("pref_roles"),
                    "topics": candidate.get("topics"),
                }

                score = calculate_score(
                    dict(viewer),
                    dict(viewer_pref),
                    candidate,
                    candidate_pref,
                    candidate.get("linkedin_status") == "verified",
                )
                if candidate["who_can_intro"] == "linkedin_only":
                    viewer_linkedin = conn.execute(
                        "SELECT status FROM linkedin_verifications WHERE user_id = ?",
                        (viewer_id,),
                    ).fetchone()
                    if not viewer_linkedin or viewer_linkedin["status"] != "verified":
                        continue
                recommendations.append({**candidate, "score": score})

            recommendations.sort(key=lambda item: (item["score"], item["updated_at"]), reverse=True)
            return recommendations[:limit]

    def mark_recommendation(self, viewer_tg_user_id: int, candidate_id: int, status: str) -> None:
        with self.connection() as conn:
            viewer_id = self._get_user_id(conn, viewer_tg_user_id)
            conn.execute(
                """
                INSERT INTO recommendation_events (viewer_user_id, candidate_user_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(viewer_user_id, candidate_user_id)
                DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
                """,
                (viewer_id, candidate_id, status, utcnow()),
            )

    def can_send_intro(self, sender_tg_user_id: int, recipient_id: int) -> tuple[bool, str]:
        with self.connection() as conn:
            sender_id = self._get_user_id(conn, sender_tg_user_id)
            if not sender_id:
                return False, "Пользователь не найден."

            if self._is_blocked(conn, sender_id, recipient_id):
                return False, "Контакт недоступен."

            profile = conn.execute("SELECT * FROM users WHERE id = ?", (recipient_id,)).fetchone()
            privacy = conn.execute("SELECT * FROM privacy_settings WHERE user_id = ?", (recipient_id,)).fetchone()
            if not profile or not privacy:
                return False, "Контакт не найден."
            if profile["profile_status"] != "active":
                return False, "Профиль недоступен для интро."
            if not int(profile["open_to_intro"]):
                return False, "Пользователь закрыл входящие интро."
            if privacy["visibility"] == "hidden":
                return False, "Профиль скрыт."

            if privacy["who_can_intro"] == "linkedin_only":
                sender_linkedin = conn.execute(
                    "SELECT status FROM linkedin_verifications WHERE user_id = ?",
                    (sender_id,),
                ).fetchone()
                if not sender_linkedin or sender_linkedin["status"] != "verified":
                    return False, "Получатель принимает интро только от LinkedIn verified."
            elif privacy["who_can_intro"] == "matching_only":
                sender = conn.execute("SELECT * FROM users WHERE id = ?", (sender_id,)).fetchone()
                sender_pref = conn.execute("SELECT * FROM preferences WHERE user_id = ?", (sender_id,)).fetchone()
                recipient_pref = conn.execute("SELECT * FROM preferences WHERE user_id = ?", (recipient_id,)).fetchone()
                if not sender or not sender_pref or not recipient_pref:
                    return False, "Недостаточно данных для отправки интро."
                score = calculate_score(
                    dict(sender),
                    dict(sender_pref),
                    dict(profile),
                    dict(recipient_pref),
                    False,
                )
                if score < 25:
                    return False, "Получатель принимает интро только от достаточно релевантных профилей."

            cutoff = (datetime.now(tz=UTC) - timedelta(hours=24)).isoformat()
            recent = conn.execute(
                """
                SELECT 1
                FROM intros
                WHERE sender_user_id = ? AND recipient_user_id = ? AND created_at >= ?
                """,
                (sender_id, recipient_id, cutoff),
            ).fetchone()
            if recent:
                return False, "Этому пользователю уже отправлялось интро за последние 24 часа."

            return True, ""

    def create_intro(self, sender_tg_user_id: int, recipient_id: int, intro_text: str) -> int:
        with self.connection() as conn:
            sender_id = self._get_user_id(conn, sender_tg_user_id)
            now = utcnow()
            cursor = conn.execute(
                """
                INSERT INTO intros (sender_user_id, recipient_user_id, intro_text, status, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', ?, ?)
                """,
                (sender_id, recipient_id, intro_text, now, now),
            )
            return int(cursor.lastrowid)

    def list_incoming_intros(self, tg_user_id: int) -> list[dict]:
        with self.connection() as conn:
            recipient_id = self._get_user_id(conn, tg_user_id)
            rows = conn.execute(
                """
                SELECT
                    i.*,
                    u.display_name AS sender_name,
                    u.role AS sender_role,
                    u.industry AS sender_industry
                FROM intros i
                JOIN users u ON u.id = i.sender_user_id
                WHERE i.recipient_user_id = ?
                ORDER BY CASE WHEN i.status = 'pending' THEN 0 ELSE 1 END, i.created_at DESC
                """,
                (recipient_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_intro(self, intro_id: int) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    i.*,
                    s.display_name AS sender_name,
                    s.username AS sender_username,
                    s.tg_user_id AS sender_tg_user_id,
                    r.display_name AS recipient_name,
                    r.username AS recipient_username,
                    r.tg_user_id AS recipient_tg_user_id
                FROM intros i
                JOIN users s ON s.id = i.sender_user_id
                JOIN users r ON r.id = i.recipient_user_id
                WHERE i.id = ?
                """,
                (intro_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_message_detail(self, message_id: int) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    m.*,
                    s.display_name AS sender_name,
                    s.username AS sender_username,
                    s.tg_user_id AS sender_tg_user_id,
                    r.display_name AS recipient_name,
                    r.username AS recipient_username,
                    r.tg_user_id AS recipient_tg_user_id
                FROM messages m
                JOIN users s ON s.id = m.sender_user_id
                JOIN users r ON r.id = m.recipient_user_id
                WHERE m.id = ?
                """,
                (message_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_intro_status(self, intro_id: int, status: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE intros SET status = ?, updated_at = ? WHERE id = ?",
                (status, utcnow(), intro_id),
            )

    def create_match_from_intro(self, intro_id: int) -> dict:
        with self.connection() as conn:
            intro = conn.execute(
                "SELECT * FROM intros WHERE id = ?",
                (intro_id,),
            ).fetchone()
            if not intro:
                raise ValueError("Intro not found")

            user1_id, user2_id = sorted([int(intro["sender_user_id"]), int(intro["recipient_user_id"])])
            existing = conn.execute(
                "SELECT * FROM matches WHERE user1_id = ? AND user2_id = ?",
                (user1_id, user2_id),
            ).fetchone()
            now = utcnow()
            if existing:
                conn.execute(
                    "UPDATE matches SET status = 'active', updated_at = ? WHERE id = ?",
                    (now, existing["id"]),
                )
                match_id = int(existing["id"])
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO matches (user1_id, user2_id, status, created_at, updated_at)
                    VALUES (?, ?, 'active', ?, ?)
                    """,
                    (user1_id, user2_id, now, now),
                )
                match_id = int(cursor.lastrowid)
            conn.execute(
                "UPDATE intros SET status = 'accepted', updated_at = ? WHERE id = ?",
                (now, intro_id),
            )
            row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
            return dict(row)

    def list_matches(self, tg_user_id: int) -> list[dict]:
        with self.connection() as conn:
            user_id = self._get_user_id(conn, tg_user_id)
            rows = conn.execute(
                """
                SELECT
                    m.*,
                    CASE WHEN m.user1_id = ? THEN u2.display_name ELSE u1.display_name END AS partner_name,
                    CASE WHEN m.user1_id = ? THEN u2.role ELSE u1.role END AS partner_role,
                    CASE WHEN m.user1_id = ? THEN u2.tg_user_id ELSE u1.tg_user_id END AS partner_tg_user_id,
                    CASE WHEN m.user1_id = ? THEN u2.id ELSE u1.id END AS partner_user_id
                FROM matches m
                JOIN users u1 ON u1.id = m.user1_id
                JOIN users u2 ON u2.id = m.user2_id
                WHERE m.user1_id = ? OR m.user2_id = ?
                ORDER BY m.updated_at DESC
                """,
                (user_id, user_id, user_id, user_id, user_id, user_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_match(self, match_id: int) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM matches WHERE id = ?",
                (match_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_match_for_user(self, match_id: int, tg_user_id: int) -> dict | None:
        with self.connection() as conn:
            user_id = self._get_user_id(conn, tg_user_id)
            row = conn.execute(
                """
                SELECT
                    m.*,
                    CASE WHEN m.user1_id = ? THEN u2.display_name ELSE u1.display_name END AS partner_name,
                    CASE WHEN m.user1_id = ? THEN u2.tg_user_id ELSE u1.tg_user_id END AS partner_tg_user_id,
                    CASE WHEN m.user1_id = ? THEN u2.id ELSE u1.id END AS partner_user_id
                FROM matches m
                JOIN users u1 ON u1.id = m.user1_id
                JOIN users u2 ON u2.id = m.user2_id
                WHERE m.id = ? AND (m.user1_id = ? OR m.user2_id = ?)
                """,
                (user_id, user_id, user_id, match_id, user_id, user_id),
            ).fetchone()
            return dict(row) if row else None

    def set_match_status(self, match_id: int, status: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE matches SET status = ?, updated_at = ? WHERE id = ?",
                (status, utcnow(), match_id),
            )

    def block_user_from_match(self, match_id: int, blocker_tg_user_id: int) -> int | None:
        with self.connection() as conn:
            blocker_id = self._get_user_id(conn, blocker_tg_user_id)
            match = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
            if not match:
                return None
            blocked_id = int(match["user2_id"]) if int(match["user1_id"]) == blocker_id else int(match["user1_id"])
            conn.execute(
                """
                INSERT OR IGNORE INTO user_blocks (blocker_user_id, blocked_user_id, created_at)
                VALUES (?, ?, ?)
                """,
                (blocker_id, blocked_id, utcnow()),
            )
            conn.execute(
                "UPDATE matches SET status = 'blocked', updated_at = ? WHERE id = ?",
                (utcnow(), match_id),
            )
            return blocked_id

    def can_send_message(self, sender_tg_user_id: int, match_id: int) -> tuple[bool, str]:
        with self.connection() as conn:
            sender_id = self._get_user_id(conn, sender_tg_user_id)
            match = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
            if not match:
                return False, "Мэтч не найден."
            if int(match["user1_id"]) != sender_id and int(match["user2_id"]) != sender_id:
                return False, "Нет доступа к переписке."
            if match["status"] not in {"active", "muted"}:
                return False, "Этот мэтч уже закрыт."

            cutoff = (datetime.now(tz=UTC) - timedelta(minutes=1)).isoformat()
            recent_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM messages
                WHERE match_id = ? AND sender_user_id = ? AND created_at >= ?
                """,
                (match_id, sender_id, cutoff),
            ).fetchone()[0]
            if recent_count >= 5:
                return False, "Слишком много сообщений. Попробуйте чуть позже."
            return True, ""

    def create_message(self, sender_tg_user_id: int, match_id: int, content: str, telegram_message_id: int | None = None) -> dict:
        with self.connection() as conn:
            sender_id = self._get_user_id(conn, sender_tg_user_id)
            match = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
            if not match:
                raise ValueError("Match not found")
            recipient_id = int(match["user2_id"]) if int(match["user1_id"]) == sender_id else int(match["user1_id"])
            now = utcnow()
            cursor = conn.execute(
                """
                INSERT INTO messages (match_id, sender_user_id, recipient_user_id, content, telegram_message_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (match_id, sender_id, recipient_id, content, telegram_message_id, now),
            )
            message_id = int(cursor.lastrowid)
            sender = conn.execute("SELECT display_name FROM users WHERE id = ?", (sender_id,)).fetchone()
            recipient = conn.execute("SELECT tg_user_id FROM users WHERE id = ?", (recipient_id,)).fetchone()
            return {
                "id": message_id,
                "recipient_tg_user_id": int(recipient["tg_user_id"]),
                "sender_name": sender["display_name"],
                "content": content,
            }

    def create_complaint(self, reporter_tg_user_id: int, target_type: str, reason: str, comment: str | None, target_id: int | None = None) -> int:
        with self.connection() as conn:
            reporter_id = self._get_user_id(conn, reporter_tg_user_id)
            cursor = conn.execute(
                """
                INSERT INTO complaints (reporter_user_id, target_type, target_id, reason, comment, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (reporter_id, target_type, target_id, reason, comment, utcnow(), utcnow()),
            )
            return int(cursor.lastrowid)
