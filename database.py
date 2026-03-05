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
            created_at TEXT NOT NULL
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
    # Migration: remove phone column if it exists (recreate players table)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(players)").fetchall()]
    if "phone" in cols:
        conn.executescript("""
            BEGIN;
            CREATE TABLE IF NOT EXISTS players_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            INSERT OR IGNORE INTO players_new (id, username, email, created_at)
                SELECT id, username, email, created_at FROM players;
            DROP TABLE players;
            ALTER TABLE players_new RENAME TO players;
            COMMIT;
        """)

    # Migration: add unique index on username if not already present
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_players_username ON players(username)")
        conn.commit()
    except Exception:
        pass

    # Always sync config.py values to DB on startup
    if default_sentence:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('target_sentence', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (default_sentence,),
        )
    # Migration: add model_used column if it doesn't exist yet
    try:
        conn.execute("ALTER TABLE attempts ADD COLUMN model_used TEXT")
        conn.commit()
    except Exception:
        pass  # column already exists
    conn.commit()
    conn.close()


def get_max_attempts() -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'max_attempts'"
    ).fetchone()
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


def create_player(username, email):
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO players (username, email, created_at) VALUES (?, ?, ?)",
        (username, email, datetime.now(timezone.utc).isoformat()),
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


def create_attempt(player_id, attempt_number, prompt_text, input_tokens, llm_response, is_exact_match, model_used=""):
    conn = get_conn()
    conn.execute(
        """INSERT INTO attempts
           (player_id, attempt_number, prompt_text, input_tokens, llm_response, is_exact_match, created_at, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            player_id,
            attempt_number,
            prompt_text,
            input_tokens,
            llm_response,
            int(is_exact_match),
            datetime.now(timezone.utc).isoformat(),
            model_used,
        ),
    )
    conn.commit()
    conn.close()


def player_has_exact_match(player_id) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM attempts WHERE player_id = ? AND is_exact_match = 1 LIMIT 1",
        (player_id,),
    ).fetchone()
    conn.close()
    return row is not None


def get_player_attempts(player_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM attempts WHERE player_id = ? ORDER BY attempt_number ASC",
        (player_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_model() -> str:
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'model'"
    ).fetchone()
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
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'target_sentence'"
    ).fetchone()
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


def get_max_input_tokens() -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'max_input_tokens'"
    ).fetchone()
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


def get_constraints() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT word FROM constraints ORDER BY id ASC").fetchall()
    conn.close()
    return [row["word"] for row in rows]


def add_constraint(word: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO constraints (word) VALUES (?)",
        (word.strip().lower(),),
    )
    conn.commit()
    conn.close()


def remove_constraint(word: str):
    conn = get_conn()
    conn.execute("DELETE FROM constraints WHERE word = ?", (word.strip().lower(),))
    conn.commit()
    conn.close()


def get_leaderboard():
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.id AS player_id, p.username, a.input_tokens,
               p.created_at AS game_started_at, a.created_at AS matched_at
        FROM attempts a
        JOIN players p ON a.player_id = p.id
        WHERE a.is_exact_match = 1
    """).fetchall()
    conn.close()

    # Group by player; compute time for each exact match attempt
    players = {}
    for row in rows:
        try:
            start = datetime.fromisoformat(row["game_started_at"])
            end = datetime.fromisoformat(row["matched_at"])
            time_seconds = max(0, int((end - start).total_seconds()))
        except Exception:
            time_seconds = 0

        pid = row["player_id"]
        if pid not in players:
            players[pid] = {"username": row["username"], "attempts": []}
        players[pid]["attempts"].append((row["input_tokens"], time_seconds))

    # Pick best attempt per player: min tokens, then min time
    results = []
    for data in players.values():
        best_tokens, best_time = min(data["attempts"], key=lambda x: (x[0], x[1]))
        results.append({
            "username": data["username"],
            "best_tokens": best_tokens,
            "time_seconds": best_time,
        })

    results.sort(key=lambda x: (x["best_tokens"], x["time_seconds"]))
    return [{"rank": i + 1, **r} for i, r in enumerate(results)]
