# Blue Schwan Challenge

A multiplayer **prompt engineering game** where players craft natural language prompts to make an LLM output an exact target sentence — using as few tokens as possible.

Built with FastAPI, SQLite, and the OpenAI API. Designed to run live at events, workshops, and demos. Players join from their own phones via a QR code; the host controls everything from an admin panel and watches the leaderboard on a big screen.

---

## How the Game Works

1. Players scan a QR code and register with their name and organisation
2. They see a target sentence (e.g. *"Blue Schwan fliegt von Neuschwanstein nach Schweinfurt."*)
3. They write a prompt trying to make the LLM output that exact sentence
4. The fewer tokens used, the better the score
5. Exact match on a level unlocks the next level — each level is harder
6. The leaderboard ranks players globally across all completed levels

---

## Features

### Gameplay
- **Multi-level progression** — admin sets 1–N levels, each with its own target sentence and constraints
- **Per-level attempts** — configurable max attempts per level (default 10)
- **Per-level time limit** — silent timer; form disables when time expires, no countdown shown to reduce panic
- **Skip option** — player who gets an exact match can skip remaining attempts and proceed early (with confirmation)
- **Forbidden words** — admin can ban specific words per level; violations don't consume an attempt

### Scoring & Leaderboard
- **Fewest average tokens wins** across all completed levels
- **Tiebreaker** — lowest average time to completion
- **Best combination** — if multiple attempts qualify, the algorithm picks the optimal combination of attempts across levels using `itertools.product`
- **Sectioned leaderboard** — Level 3 Champions at top, then Level 2, then Level 1; single global ranking (no separate 1st/2nd per section)
- **Live refresh** — leaderboard auto-updates every 5 seconds

### Admin Panel (`/admin`)
- Add / remove levels with AJAX (no page reload)
- Edit target sentence per level with live save
- Add / remove forbidden words per level (chip UI)
- Global settings: max attempts, max input tokens, game duration, OpenAI model
- All settings take effect immediately for new sessions

### Infrastructure
- **Public access via ngrok** — players use their own mobile data or venue Wi-Fi; admin and leaderboard stay on LAN
- **QR code** auto-generated on startup pointing to the player registration URL
- **SQLite** with automatic schema migrations — no setup required

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | [FastAPI](https://fastapi.tiangolo.com/) |
| Server | [Uvicorn](https://www.uvicorn.org/) (ASGI) |
| Database | SQLite3 (via Python `sqlite3`) |
| LLM | [OpenAI Python SDK](https://github.com/openai/openai-python) |
| Templates | Jinja2 |
| QR Code | `qrcode[pil]` |
| Tunnel | [ngrok](https://ngrok.com/) (optional) |
| Frontend | Vanilla HTML / CSS / JavaScript |

---

## Project Structure

```
blue_swan/
├── main.py               # FastAPI app, routes, game logic
├── database.py           # SQLite schema, migrations, queries
├── config.py             # Default configuration constants
├── .env                  # Secret keys and environment overrides (not committed)
├── game.db               # SQLite database (auto-created)
├── static/
│   ├── qrcode.png        # Auto-generated QR code
│   └── thws.jpg          # Sponsor logo
└── templates/
    ├── register.html     # Player registration page
    ├── game.html         # Main game interface
    ├── admin.html        # Admin control panel
    └── leaderboard.html  # Live leaderboard (big screen)
```

---

## Getting Started

### 1. Install dependencies

```bash
pip install fastapi uvicorn "openai>=1.0" jinja2 "qrcode[pil]" python-dotenv
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-...

# Optional: override the IP used in the QR code (useful on multi-interface machines)
HOST_IP=192.168.1.100

# Optional: set when using ngrok for public access
PUBLIC_URL=https://xxxx.ngrok-free.app
```

### 3. Run the server

```bash
python main.py
```

On startup, the server prints:

```
  Player URL (QR): https://xxxx.ngrok-free.app/
  Tunnel active  : https://xxxx.ngrok-free.app → localhost:8000
  Leaderboard    : http://192.168.1.100:8000/leaderboard
  Admin          : http://192.168.1.100:8000/admin
```

### 4. Access the application

| Page | URL |
|---|---|
| Player registration | `http://localhost:8000/` |
| Admin panel | `http://localhost:8000/admin` |
| Leaderboard | `http://localhost:8000/leaderboard` |

---

## Using ngrok for Public Access

Players can join from their own mobile data or venue Wi-Fi — no hotspot required.

```bash
# Terminal 1 — start the tunnel
ngrok http 8000

# Copy the Forwarding URL, e.g. https://xxxx.ngrok-free.app
# Terminal 2 — start the server with the public URL
PUBLIC_URL=https://xxxx.ngrok-free.app python main.py
```

On Windows PowerShell:

```powershell
$env:PUBLIC_URL="https://xxxx.ngrok-free.app"; python main.py
```

The QR code and all player-facing links will automatically use the public URL. Admin and leaderboard remain accessible on `localhost`.

---

## Database Schema

The database (`game.db`) is created and migrated automatically on startup.

| Table | Purpose |
|---|---|
| `players` | Registered players (username, organisation, created_at) |
| `levels` | Game levels — each has a level number and target sentence |
| `level_constraints` | Forbidden words per level |
| `player_levels` | When each player started each level (used for time scoring) |
| `attempts` | All prompt submissions with tokens, response, and match result |
| `settings` | Key-value store for runtime config (max attempts, model, etc.) |

---

## Configuration Reference

Defaults are set in `config.py` and synced to the database on every startup. They can be overridden live from the admin panel.

| Variable | Default | Description |
|---|---|---|
| `TARGET_SENTENCE` | `"Blue Schwan fliegt…"` | Default Level 1 target sentence |
| `MAX_ATTEMPTS` | `10` | Attempts allowed per level |
| `MAX_INPUT_TOKENS` | `500` | Max word-count of a player's prompt |
| `GAME_DURATION_SECONDS` | `1200` | Time limit per level (20 min) |
| `MODEL` | `gpt-4o-mini` | OpenAI model used for evaluation |
| `PORT` | `8000` | Server port |
| `HOST_IP` | *(auto-detected)* | IP for local QR code |
| `PUBLIC_URL` | *(empty)* | ngrok public URL (set via env var) |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Registration page |
| `POST` | `/register` | Create player and start Level 1 |
| `GET` | `/game/{player_id}` | Game page for a player |
| `POST` | `/attempt` | Submit a prompt attempt |
| `POST` | `/game/{player_id}/next-level` | Advance to next level |
| `GET` | `/leaderboard` | Leaderboard page |
| `GET` | `/api/leaderboard` | Leaderboard data (JSON) |
| `GET` | `/admin` | Admin panel |
| `POST` | `/admin` | Save global settings |
| `GET` | `/api/levels` | All levels with constraints (JSON) |
| `POST` | `/api/levels/add` | Add a new level |
| `POST` | `/api/levels/remove` | Remove a level |
| `POST` | `/api/levels/update-sentence` | Update a level's target sentence |
| `POST` | `/api/levels/{level_id}/constraints/add` | Add a forbidden word |
| `POST` | `/api/levels/{level_id}/constraints/remove` | Remove a forbidden word |

---

## Leaderboard Ranking Logic

Players are ranked by:

1. **Highest consecutive level passed** — a player at Level 3 always ranks above Level 2, regardless of tokens
2. **Lowest average tokens** across all completed levels — the optimal combination of one exact-match attempt per level is selected using `itertools.product`
3. **Lowest average time** — tiebreaker when average tokens are equal

Time per level is measured from when the player started that level (not total session time), so advancing quickly to a higher level doesn't penalise earlier careful play.

---

## Running at an Event

1. Set your OpenAI key in `.env`
2. Start ngrok: `ngrok http 8000`
3. Start the server with the ngrok URL
4. Open `/admin` to configure levels and constraints
5. Display `/leaderboard` on a projector or big screen
6. Players scan the QR code — they're in

The leaderboard refreshes automatically every 5 seconds. No manual intervention needed during the game.

---

## Acknowledgements

Built for live AI education events.
Powered by **CAIRO & TTZ-WUE**.

---

## License

MIT
