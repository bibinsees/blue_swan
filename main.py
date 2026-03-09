import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import qrcode
import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI

from config import (
    GAME_DURATION_SECONDS, HOST_IP, MAX_ATTEMPTS, MAX_INPUT_TOKENS,
    MODEL, OPENAI_API_KEY, PORT, PUBLIC_URL, TARGET_SENTENCE,
)
from database import (
    add_level, add_level_constraint,
    create_attempt, create_player,
    get_game_duration, get_leaderboard, get_level_constraints,
    get_levels, get_max_attempts, get_max_input_tokens, get_model,
    get_player_attempts_for_level, get_player_by_id, get_player_by_username,
    get_player_current_level, get_player_level_started_at,
    player_has_exact_match_for_level,
    remove_level, remove_level_constraint, update_level_sentence,
    set_game_duration, set_max_attempts, set_max_input_tokens, set_model,
    start_player_level,
    init_db,
)

client = OpenAI(api_key=OPENAI_API_KEY)


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def generate_qr():
    os.makedirs("static", exist_ok=True)
    ip = HOST_IP if HOST_IP else get_local_ip()
    local_base = f"http://{ip}:{PORT}"
    player_url = PUBLIC_URL.rstrip("/") + "/" if PUBLIC_URL else f"{local_base}/"
    img = qrcode.make(player_url)
    img.save("static/qrcode.png")
    print(f"\n  Player URL (QR): {player_url}")
    if PUBLIC_URL:
        print(f"  Tunnel active  : {PUBLIC_URL} → localhost:{PORT}")
    print(f"  Leaderboard    : {local_base}/leaderboard")
    print(f"  Admin          : {local_base}/admin\n")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(default_sentence=TARGET_SENTENCE)
    set_max_attempts(MAX_ATTEMPTS)
    set_max_input_tokens(MAX_INPUT_TOKENS)
    set_game_duration(GAME_DURATION_SECONDS)
    set_model(MODEL)
    generate_qr()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── Registration ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    organisation: str = Form(...),
    email: str = Form(default=""),
):
    if get_player_by_username(username):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "This username is already taken."},
        )
    if not email:
        email = f"{username.lower().replace(' ', '_')}@noemail.local"
    player_id = create_player(username, email, organisation)

    # Start the player on level 1 immediately
    levels = get_levels()
    if levels:
        start_player_level(player_id, levels[0]["id"])

    return RedirectResponse(url=f"/game/{player_id}", status_code=303)


# ── Game ───────────────────────────────────────────────────────────────────────

@app.get("/game/{player_id}", response_class=HTMLResponse)
async def game_page(request: Request, player_id: int):
    player = get_player_by_id(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    current_level = get_player_current_level(player_id)
    if not current_level:
        raise HTTPException(status_code=400, detail="Player has no active level")

    level_id = current_level["level_id"]
    level_number = current_level["level_number"]
    target_sentence = current_level["target_sentence"]
    constraints = get_level_constraints(level_id)
    attempts = get_player_attempts_for_level(player_id, level_id)
    max_attempts = get_max_attempts()
    attempts_used = len(attempts)
    all_levels = get_levels()
    total_levels = len(all_levels)
    has_next_level = level_number < total_levels
    has_exact_match = player_has_exact_match_for_level(player_id, level_id)
    all_attempts_used = attempts_used >= max_attempts

    # Time remaining for this level
    duration = get_game_duration()
    level_started_at = get_player_level_started_at(player_id, level_id) or player["created_at"]
    elapsed = int((datetime.now(timezone.utc) - datetime.fromisoformat(level_started_at)).total_seconds())
    time_remaining = max(0, duration - elapsed)

    return templates.TemplateResponse(
        "game.html",
        {
            "request": request,
            "player": player,
            "level_id": level_id,
            "level_number": level_number,
            "total_levels": total_levels,
            "target_sentence": target_sentence,
            "attempts": attempts,
            "max_attempts": max_attempts,
            "attempts_used": attempts_used,
            "current_model": get_model(),
            "has_exact_match": has_exact_match,
            "all_attempts_used": all_attempts_used,
            "has_next_level": has_next_level,
            "constraints": constraints,
            "max_input_tokens": get_max_input_tokens(),
            "time_remaining_seconds": time_remaining,
            "game_duration_seconds": duration,
            "leaderboard_url": (PUBLIC_URL.rstrip("/") + "/leaderboard") if PUBLIC_URL else "/leaderboard",
        },
    )


@app.post("/game/{player_id}/next-level")
async def next_level(player_id: int):
    player = get_player_by_id(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    current_level = get_player_current_level(player_id)
    if not current_level:
        raise HTTPException(status_code=400, detail="No active level")

    level_id = current_level["level_id"]
    level_number = current_level["level_number"]

    # Must have exact match to proceed
    if not player_has_exact_match_for_level(player_id, level_id):
        raise HTTPException(status_code=400, detail="No exact match in current level")

    # Find next level
    all_levels = get_levels()
    next_lvl = next((l for l in all_levels if l["level_number"] == level_number + 1), None)
    if not next_lvl:
        raise HTTPException(status_code=400, detail="No next level")

    start_player_level(player_id, next_lvl["id"])
    return RedirectResponse(url=f"/game/{player_id}", status_code=303)


@app.post("/attempt")
async def make_attempt(
    player_id: int = Form(...),
    prompt_text: str = Form(...),
):
    player = get_player_by_id(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    current_level = get_player_current_level(player_id)
    if not current_level:
        return JSONResponse({"error": "No active level."}, status_code=400)

    level_id = current_level["level_id"]
    target_sentence = current_level["target_sentence"]

    attempts = get_player_attempts_for_level(player_id, level_id)
    if len(attempts) >= get_max_attempts():
        return JSONResponse({"error": "Maximum attempts reached."}, status_code=400)

    # Time limit check
    duration = get_game_duration()
    level_started_at = get_player_level_started_at(player_id, level_id) or player["created_at"]
    elapsed = int((datetime.now(timezone.utc) - datetime.fromisoformat(level_started_at)).total_seconds())
    if elapsed > duration:
        return JSONResponse({"error": "Time's up! Your game session has ended."}, status_code=400)

    if not prompt_text.strip():
        return JSONResponse({"error": "Prompt cannot be empty."}, status_code=400)

    # Token limit check
    if len(prompt_text.split()) > get_max_input_tokens():
        return JSONResponse({"constraint_violation": "You exceeded token limit, reduce the words and try again"})

    # Constraint check
    constraints = get_level_constraints(level_id)
    prompt_lower = prompt_text.lower()
    for word in constraints:
        if word in prompt_lower.split():
            return JSONResponse({"constraint_violation": "Nice try! Caught you using prohibited words :)"})

    response = client.chat.completions.create(
        model=get_model(),
        messages=[{"role": "user", "content": prompt_text}],
    )

    llm_response = response.choices[0].message.content
    input_tokens = response.usage.prompt_tokens
    is_exact_match = llm_response.strip() == target_sentence
    attempt_number = len(attempts) + 1
    model_used = get_model()
    now = datetime.now(timezone.utc)

    create_attempt(
        player_id=player_id,
        level_id=level_id,
        attempt_number=attempt_number,
        prompt_text=prompt_text,
        input_tokens=input_tokens,
        llm_response=llm_response,
        is_exact_match=is_exact_match,
        model_used=model_used,
    )

    attempts_remaining = get_max_attempts() - attempt_number

    time_seconds = None
    if is_exact_match:
        try:
            start = datetime.fromisoformat(level_started_at)
            time_seconds = max(0, int((now - start).total_seconds()))
        except Exception:
            time_seconds = 0

    return JSONResponse({
        "llm_response": llm_response,
        "input_tokens": input_tokens,
        "is_exact_match": is_exact_match,
        "attempt_number": attempt_number,
        "attempts_remaining": attempts_remaining,
        "model_used": model_used,
        "time_seconds": time_seconds,
    })


# ── Admin ──────────────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    levels = get_levels()
    levels_with_constraints = [
        {**lvl, "constraints": get_level_constraints(lvl["id"])}
        for lvl in levels
    ]
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "levels": levels_with_constraints,
            "current_max_attempts": get_max_attempts(),
            "current_max_input_tokens": get_max_input_tokens(),
            "current_game_duration": get_game_duration(),
            "current_model": get_model(),
            "saved": False,
        },
    )


@app.post("/admin")
async def admin_update(
    request: Request,
    max_attempts: int = Form(...),
    max_input_tokens: int = Form(...),
    game_duration_seconds: int = Form(...),
    model: str = Form(...),
):
    set_max_attempts(max(1, max_attempts))
    set_max_input_tokens(max(1, max_input_tokens))
    set_game_duration(max(30, game_duration_seconds))
    set_model(model.strip())
    levels = get_levels()
    levels_with_constraints = [
        {**lvl, "constraints": get_level_constraints(lvl["id"])}
        for lvl in levels
    ]
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "levels": levels_with_constraints,
            "current_max_attempts": max(1, max_attempts),
            "current_max_input_tokens": max(1, max_input_tokens),
            "current_game_duration": max(30, game_duration_seconds),
            "current_model": model.strip(),
            "saved": True,
        },
    )


# ── Levels API ─────────────────────────────────────────────────────────────────

@app.get("/api/levels")
async def api_get_levels():
    levels = get_levels()
    return [
        {**lvl, "constraints": get_level_constraints(lvl["id"])}
        for lvl in levels
    ]


@app.post("/api/levels/add")
async def api_add_level(target_sentence: str = Form(...)):
    if not target_sentence.strip():
        return JSONResponse({"error": "Sentence cannot be empty."}, status_code=400)
    level_id = add_level(target_sentence)
    levels = get_levels()
    return {
        "level_id": level_id,
        "levels": [{**lvl, "constraints": get_level_constraints(lvl["id"])} for lvl in levels],
    }


@app.post("/api/levels/remove")
async def api_remove_level(level_id: int = Form(...)):
    all_levels = get_levels()
    if len(all_levels) <= 1:
        return JSONResponse({"error": "Cannot remove the last level."}, status_code=400)
    remove_level(level_id)
    levels = get_levels()
    return {"levels": [{**lvl, "constraints": get_level_constraints(lvl["id"])} for lvl in levels]}


@app.post("/api/levels/update-sentence")
async def api_update_sentence(level_id: int = Form(...), target_sentence: str = Form(...)):
    if not target_sentence.strip():
        return JSONResponse({"error": "Sentence cannot be empty."}, status_code=400)
    update_level_sentence(level_id, target_sentence)
    return {"ok": True}


@app.post("/api/levels/{level_id}/constraints/add")
async def api_add_level_constraint(level_id: int, word: str = Form(...)):
    word = word.strip().lower()
    if not word or " " in word:
        return JSONResponse({"error": "Enter a single word."}, status_code=400)
    add_level_constraint(level_id, word)
    return {"constraints": get_level_constraints(level_id)}


@app.post("/api/levels/{level_id}/constraints/remove")
async def api_remove_level_constraint(level_id: int, word: str = Form(...)):
    remove_level_constraint(level_id, word.strip().lower())
    return {"constraints": get_level_constraints(level_id)}


# ── Leaderboard ────────────────────────────────────────────────────────────────

@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(request: Request):
    leaderboard = get_leaderboard()
    ip = HOST_IP if HOST_IP else get_local_ip()
    register_url = PUBLIC_URL.rstrip("/") + "/" if PUBLIC_URL else f"http://{ip}:{PORT}/"
    total_levels = len(get_levels())
    return templates.TemplateResponse(
        "leaderboard.html",
        {
            "request": request,
            "leaderboard": leaderboard,
            "register_url": register_url,
            "total_levels": total_levels,
        },
    )


@app.get("/api/leaderboard")
async def leaderboard_api():
    levels = get_levels()
    return {"entries": get_leaderboard(), "total_levels": len(levels)}


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
