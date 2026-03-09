import itertools
import sqlite3
from datetime import datetime, timezone

DB_PATH = "game.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(default_sentence: str = ""):
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            organisation TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS levels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level_number INTEGER NOT NULL UNIQUE,
            target_sentence TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS level_constraints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level_id INTEGER NOT NULL,
            word TEXT NOT NULL,
            UNIQUE(level_id, word),
            FOREIGN KEY (level_id) REFERENCES levels(id)
        );

        CREATE TABLE IF NOT EXISTS player_levels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            level_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            UNIQUE(player_id, level_id),
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (level_id) REFERENCES levels(id)
        );

        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            attempt_number INTEGER NOT NULL,
            prompt_text TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            llm_response TEXT NOT NULL,
            is_exact_match INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (player_id) REFERENCES players(id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS constraints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL UNIQUE
        );
    """)

    # Migration: remove phone column
    cols = [row[1] for row in conn.execute("PRAGMA table_info(players)").fetchall()]
    if "phone" in cols:
        conn.executescript("""
            BEGIN;
            CREATE TABLE IF NOT EXISTS players_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                organisation TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            INSERT OR IGNORE INTO players_new (id, username, email, organisation, created_at)
                SELECT id, username, email, COALESCE(organisation,''), created_at FROM players;
            DROP TABLE players;
            ALTER TABLE players_new RENAME TO players;
            COMMIT;
        """)

    # Migration: unique index on username
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_players_username ON players(username)")
        conn.commit()
    except Exception:
        pass

    # Migration: add model_used and level_id to attempts
    attempt_cols = [row[1] for row in conn.execute("PRAGMA table_info(attempts)").fetchall()]
    if "model_used" not in attempt_cols:
        try:
            conn.execute("ALTER TABLE attempts ADD COLUMN model_used TEXT")
            conn.commit()
        except Exception:
            pass
    if "level_id" not in attempt_cols:
        try:
            conn.execute("ALTER TABLE attempts ADD COLUMN level_id INTEGER")
            conn.commit()
        except Exception:
            pass

    # Migration: add organisation to players
    try:
        conn.execute("ALTER TABLE players ADD COLUMN organisation TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except Exception:
        pass

    # Sync default sentence to settings
    if default_sentence:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('target_sentence', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (default_sentence,),
        )
        conn.commit()

    # Migration: seed level 1 from settings if levels table is empty
    level_count = conn.execute("SELECT COUNT(*) FROM levels").fetchone()[0]
    if level_count == 0:
        sentence_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'target_sentence'"
        ).fetchone()
        seed_sentence = sentence_row["value"] if sentence_row else (default_sentence or "")
        if seed_sentence:
            conn.execute(
                "INSERT OR IGNORE INTO levels (level_number, target_sentence) VALUES (1, ?)",
                (seed_sentence,),
            )
            conn.commit()

    # Migration: migrate old constraints table to level_constraints for level 1
    lc_count = conn.execute("SELECT COUNT(*) FROM level_constraints").fetchone()[0]
    old_c_count = conn.execute("SELECT COUNT(*) FROM constraints").fetchone()[0]
    if lc_count == 0 and old_c_count > 0:
        level1 = conn.execute("SELECT id FROM levels WHERE level_number = 1").fetchone()
        if level1:
            old_words = conn.execute("SELECT word FROM constraints").fetchall()
            for row in old_words:
                conn.execute(
                    "INSERT OR IGNORE INTO level_constraints (level_id, word) VALUES (?, ?)",
                    (level1["id"], row["word"]),
                )
            conn.commit()

    # Migration: set level_id on existing attempts that have NULL level_id
    level1 = conn.execute("SELECT id FROM levels WHERE level_number = 1").fetchone()
    if level1:
        conn.execute(
            "UPDATE attempts SET level_id = ? WHERE level_id IS NULL",
            (level1["id"],),
        )
        conn.commit()

        # Migration: create player_levels entries for existing players who don't have one for level 1
        players_without_pl = conn.execute("""
            SELECT p.id, p.created_at FROM players p
            WHERE NOT EXISTS (
                SELECT 1 FROM player_levels pl WHERE pl.player_id = p.id AND pl.level_id = ?
            )
        """, (level1["id"],)).fetchall()
        for p in players_without_pl:
            conn.execute(
                "INSERT OR IGNORE INTO player_levels (player_id, level_id, started_at) VALUES (?, ?, ?)",
                (p["id"], level1["id"], p["created_at"]),
            )
        conn.commit()

    conn.close()


# ── Settings helpers ───────────────────────────────────────────────────────────

def get_max_attempts() -> int:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'max_attempts'").fetchone()
    conn.close()
    return int(row["value"]) if row else 3


def set_max_attempts(value: int):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('max_attempts', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(value),),
    )
    conn.commit()
    conn.close()


def get_max_input_tokens() -> int:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'max_input_tokens'").fetchone()
    conn.close()
    return int(row["value"]) if row else 500


def set_max_input_tokens(value: int):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('max_input_tokens', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(value),),
    )
    conn.commit()
    conn.close()


def get_game_duration() -> int:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'game_duration_seconds'").fetchone()
    conn.close()
    return int(row["value"]) if row else 360


def set_game_duration(value: int):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('game_duration_seconds', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(value),),
    )
    conn.commit()
    conn.close()


def get_model() -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'model'").fetchone()
    conn.close()
    return row["value"] if row else "gpt-4o-mini"


def set_model(model: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('model', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (model,),
    )
    conn.commit()
    conn.close()


def get_target_sentence() -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'target_sentence'").fetchone()
    conn.close()
    return row["value"] if row else ""


def set_target_sentence(sentence: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('target_sentence', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (sentence,),
    )
    conn.commit()
    conn.close()


# ── Levels ─────────────────────────────────────────────────────────────────────

def get_levels() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, level_number, target_sentence FROM levels ORDER BY level_number ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_level(target_sentence: str) -> int:
    conn = get_conn()
    row = conn.execute("SELECT COALESCE(MAX(level_number), 0) + 1 AS n FROM levels").fetchone()
    next_num = row["n"]
    cursor = conn.execute(
        "INSERT INTO levels (level_number, target_sentence) VALUES (?, ?)",
        (next_num, target_sentence.strip()),
    )
    level_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return level_id


def remove_level(level_id: int):
    conn = get_conn()
    row = conn.execute("SELECT level_number FROM levels WHERE id = ?", (level_id,)).fetchone()
    if not row:
        conn.close()
        return
    level_num = row["level_number"]
    conn.execute("DELETE FROM level_constraints WHERE level_id = ?", (level_id,))
    conn.execute("DELETE FROM levels WHERE id = ?", (level_id,))
    conn.execute("UPDATE levels SET level_number = level_number - 1 WHERE level_number > ?", (level_num,))
    conn.commit()
    conn.close()


def update_level_sentence(level_id: int, sentence: str):
    conn = get_conn()
    conn.execute("UPDATE levels SET target_sentence = ? WHERE id = ?", (sentence.strip(), level_id))
    conn.commit()
    conn.close()


# ── Level Constraints ──────────────────────────────────────────────────────────

def get_level_constraints(level_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT word FROM level_constraints WHERE level_id = ? ORDER BY id ASC",
        (level_id,),
    ).fetchall()
    conn.close()
    return [r["word"] for r in rows]


def add_level_constraint(level_id: int, word: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO level_constraints (level_id, word) VALUES (?, ?)",
        (level_id, word.strip().lower()),
    )
    conn.commit()
    conn.close()


def remove_level_constraint(level_id: int, word: str):
    conn = get_conn()
    conn.execute(
        "DELETE FROM level_constraints WHERE level_id = ? AND word = ?",
        (level_id, word.strip().lower()),
    )
    conn.commit()
    conn.close()


# ── Legacy constraints (kept for migration) ───────────────────────────────────

def get_constraints() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT word FROM constraints ORDER BY id ASC").fetchall()
    conn.close()
    return [row["word"] for row in rows]


def add_constraint(word: str):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO constraints (word) VALUES (?)", (word.strip().lower(),))
    conn.commit()
    conn.close()


def remove_constraint(word: str):
    conn = get_conn()
    conn.execute("DELETE FROM constraints WHERE word = ?", (word.strip().lower(),))
    conn.commit()
    conn.close()


# ── Players ────────────────────────────────────────────────────────────────────

def create_player(username, email, organisation=""):
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO players (username, email, organisation, created_at) VALUES (?, ?, ?, ?)",
        (username, email, organisation.strip(), datetime.now(timezone.utc).isoformat()),
    )
    player_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return player_id


def get_player_by_username(username):
    conn = get_conn()
    row = conn.execute("SELECT * FROM players WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_player_by_email(email):
    conn = get_conn()
    row = conn.execute("SELECT * FROM players WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_player_by_id(player_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Player Levels ──────────────────────────────────────────────────────────────

def start_player_level(player_id: int, level_id: int, started_at: str = None):
    conn = get_conn()
    ts = started_at or datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO player_levels (player_id, level_id, started_at) VALUES (?, ?, ?)",
        (player_id, level_id, ts),
    )
    conn.commit()
    conn.close()


def get_player_current_level(player_id: int) -> dict | None:
    """Returns the highest level the player has started."""
    conn = get_conn()
    row = conn.execute("""
        SELECT pl.level_id, pl.started_at, l.level_number, l.target_sentence
        FROM player_levels pl
        JOIN levels l ON pl.level_id = l.id
        WHERE pl.player_id = ?
        ORDER BY l.level_number DESC
        LIMIT 1
    """, (player_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_player_level_started_at(player_id: int, level_id: int) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT started_at FROM player_levels WHERE player_id = ? AND level_id = ?",
        (player_id, level_id),
    ).fetchone()
    conn.close()
    return row["started_at"] if row else None


# ── Attempts ───────────────────────────────────────────────────────────────────

def create_attempt(player_id, level_id, attempt_number, prompt_text, input_tokens,
                   llm_response, is_exact_match, model_used=""):
    conn = get_conn()
    conn.execute(
        """INSERT INTO attempts
           (player_id, level_id, attempt_number, prompt_text, input_tokens,
            llm_response, is_exact_match, created_at, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            player_id, level_id, attempt_number, prompt_text, input_tokens,
            llm_response, int(is_exact_match),
            datetime.now(timezone.utc).isoformat(), model_used,
        ),
    )
    conn.commit()
    conn.close()


def get_player_attempts_for_level(player_id: int, level_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM attempts WHERE player_id = ? AND level_id = ? ORDER BY attempt_number ASC",
        (player_id, level_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_player_attempts(player_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM attempts WHERE player_id = ? ORDER BY attempt_number ASC",
        (player_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def player_has_exact_match_for_level(player_id: int, level_id: int) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM attempts WHERE player_id = ? AND level_id = ? AND is_exact_match = 1 LIMIT 1",
        (player_id, level_id),
    ).fetchone()
    conn.close()
    return row is not None


def player_has_exact_match(player_id) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM attempts WHERE player_id = ? AND is_exact_match = 1 LIMIT 1",
        (player_id,),
    ).fetchone()
    conn.close()
    return row is not None


# ── Leaderboard ────────────────────────────────────────────────────────────────

def get_leaderboard():
    conn = get_conn()

    levels = conn.execute(
        "SELECT id, level_number FROM levels ORDER BY level_number ASC"
    ).fetchall()
    if not levels:
        conn.close()
        return []

    players = conn.execute(
        "SELECT id, username, organisation, created_at FROM players"
    ).fetchall()

    results = []
    for player in players:
        pid = player["id"]

        # Find highest consecutive level the player has exact matches for
        highest_level_passed = 0
        for level in levels:
            lid = level["id"]
            has_match = conn.execute(
                "SELECT 1 FROM attempts WHERE player_id = ? AND level_id = ? AND is_exact_match = 1 LIMIT 1",
                (pid, lid),
            ).fetchone()
            if has_match:
                highest_level_passed = level["level_number"]
            else:
                break  # must be consecutive

        if highest_level_passed == 0:
            continue

        # Get exact match attempts per completed level, with time relative to level start
        exact_per_level = []
        valid = True
        for level in levels[:highest_level_passed]:
            lid = level["id"]
            started_at_row = conn.execute(
                "SELECT started_at FROM player_levels WHERE player_id = ? AND level_id = ?",
                (pid, lid),
            ).fetchone()
            start_ts = started_at_row["started_at"] if started_at_row else player["created_at"]
            try:
                start_dt = datetime.fromisoformat(start_ts)
            except Exception:
                start_dt = datetime.fromisoformat(player["created_at"])

            matches = conn.execute(
                "SELECT input_tokens, created_at FROM attempts "
                "WHERE player_id = ? AND level_id = ? AND is_exact_match = 1",
                (pid, lid),
            ).fetchall()
            if not matches:
                valid = False
                break

            level_attempts = []
            for m in matches:
                try:
                    end_dt = datetime.fromisoformat(m["created_at"])
                    t = max(0, int((end_dt - start_dt).total_seconds()))
                except Exception:
                    t = 0
                level_attempts.append((m["input_tokens"], t))
            exact_per_level.append(level_attempts)

        if not valid or not exact_per_level:
            continue

        # Find best combination (one attempt per level) → min avg tokens, then min avg time
        best_avg_tokens = None
        best_avg_time = None
        for combo in itertools.product(*exact_per_level):
            tokens = [c[0] for c in combo]
            times = [c[1] for c in combo]
            avg_tok = sum(tokens) / len(tokens)
            avg_time = sum(times) / len(times)
            if (best_avg_tokens is None
                    or avg_tok < best_avg_tokens
                    or (avg_tok == best_avg_tokens and avg_time < best_avg_time)):
                best_avg_tokens = avg_tok
                best_avg_time = avg_time

        results.append({
            "username": player["username"],
            "organisation": player["organisation"] or "",
            "highest_level": highest_level_passed,
            "best_avg_tokens": round(best_avg_tokens, 1),
            "best_avg_time": round(best_avg_time, 1),
        })

    conn.close()

    # Sort: highest level first, then fewest avg tokens, then least avg time
    results.sort(key=lambda x: (-x["highest_level"], x["best_avg_tokens"], x["best_avg_time"]))
    return [{"rank": i + 1, **r} for i, r in enumerate(results)]
