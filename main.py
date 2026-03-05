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

from config import HOST_IP, MAX_ATTEMPTS, MAX_INPUT_TOKENS, GAME_DURATION_SECONDS, MODEL, OPENAI_API_KEY, PORT, PUBLIC_URL, TARGET_SENTENCE
from database import (
    create_attempt,
    create_player,
    get_leaderboard,
    get_max_attempts,
    get_max_input_tokens,
    get_game_duration,
    get_model,
    get_player_attempts,
    get_player_by_id,
    get_player_by_email,
    get_player_by_username,
    player_has_exact_match,
    get_target_sentence,
    set_max_attempts,
    set_max_input_tokens,
    set_game_duration,
    set_model,
    set_target_sentence,
    get_constraints,
    add_constraint,
    remove_constraint,
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


# ── Registration ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
):
    if get_player_by_username(username):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "This username is already taken."},
        )
    if get_player_by_email(email):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "This email is already registered."},
        )
    player_id = create_player(username, email)
    return RedirectResponse(url=f"/game/{player_id}", status_code=303)


# ── Game ──────────────────────────────────────────────────────────────────────

@app.get("/game/{player_id}", response_class=HTMLResponse)
async def game_page(request: Request, player_id: int):
    player = get_player_by_id(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    attempts = get_player_attempts(player_id)
    duration = get_game_duration()
    elapsed = int((datetime.now(timezone.utc) - datetime.fromisoformat(player["created_at"])).total_seconds())
    time_remaining = max(0, duration - elapsed)
    return templates.TemplateResponse(
        "game.html",
        {
            "request": request,
            "player": player,
            "target_sentence": get_target_sentence(),
            "attempts": attempts,
            "max_attempts": get_max_attempts(),
            "attempts_used": len(attempts),
            "current_model": get_model(),
            "has_exact_match": player_has_exact_match(player_id),
            "constraints": get_constraints(),
            "max_input_tokens": get_max_input_tokens(),
            "time_remaining_seconds": time_remaining,
            "game_duration_seconds": duration,
        },
    )


@app.post("/attempt")
async def make_attempt(
    player_id: int = Form(...),
    prompt_text: str = Form(...),
):
    player = get_player_by_id(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    attempts = get_player_attempts(player_id)
    if len(attempts) >= get_max_attempts():
        return JSONResponse({"error": "Maximum attempts reached."}, status_code=400)

    # Time limit check
    duration = get_game_duration()
    elapsed = int((datetime.now(timezone.utc) - datetime.fromisoformat(player["created_at"])).total_seconds())
    if elapsed > duration:
        return JSONResponse({"error": "Time's up! Your game session has ended."}, status_code=400)

    if not prompt_text.strip():
        return JSONResponse({"error": "Prompt cannot be empty."}, status_code=400)

    # Token limit check — does not consume an attempt
    estimated_tokens = len(prompt_text.split())
    if estimated_tokens > get_max_input_tokens():
        return JSONResponse({"constraint_violation": "Nice try with all that yapping, You exceeded token limit, You are indeed a rule breaker!"})

    # Constraint check — does not consume an attempt
    constraints = get_constraints()
    prompt_lower = prompt_text.lower()
    for word in constraints:
        if word in prompt_lower.split():
            return JSONResponse({"constraint_violation": f"Nice try! Caught you using the words prohibited :)"})

    response = client.chat.completions.create(
        model=get_model(),
        messages=[{"role": "user", "content": prompt_text}],
    )

    llm_response = response.choices[0].message.content
    input_tokens = response.usage.prompt_tokens
    is_exact_match = llm_response.strip() == get_target_sentence()
    attempt_number = len(attempts) + 1
    model_used = get_model()
    now = datetime.now(timezone.utc)

    create_attempt(
        player_id=player_id,
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
            start = datetime.fromisoformat(player["created_at"])
            time_seconds = max(0, int((now - start).total_seconds()))
        except Exception:
            time_seconds = 0

    return JSONResponse(
        {
            "llm_response": llm_response,
            "input_tokens": input_tokens,
            "is_exact_match": is_exact_match,
            "attempt_number": attempt_number,
            "attempts_remaining": attempts_remaining,
            "model_used": model_used,
            "time_seconds": time_seconds,
        }
    )


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "current_sentence": get_target_sentence(),
            "current_max_attempts": get_max_attempts(),
            "current_max_input_tokens": get_max_input_tokens(),
            "current_game_duration": get_game_duration(),
            "current_model": get_model(),
            "current_constraints": get_constraints(),
            "saved": False,
        },
    )


@app.post("/admin")
async def admin_update(
    request: Request,
    target_sentence: str = Form(...),
    max_attempts: int = Form(...),
    max_input_tokens: int = Form(...),
    game_duration_seconds: int = Form(...),
    model: str = Form(...),
):
    set_target_sentence(target_sentence.strip())
    set_max_attempts(max(1, max_attempts))
    set_max_input_tokens(max(1, max_input_tokens))
    set_game_duration(max(30, game_duration_seconds))
    set_model(model.strip())
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "current_sentence": target_sentence.strip(),
            "current_max_attempts": max(1, max_attempts),
            "current_max_input_tokens": max(1, max_input_tokens),
            "current_game_duration": max(30, game_duration_seconds),
            "current_model": model.strip(),
            "current_constraints": get_constraints(),
            "saved": True,
        },
    )


# ── Constraints API ───────────────────────────────────────────────────────────

@app.get("/api/constraints")
async def api_get_constraints():
    return get_constraints()


@app.post("/api/constraints/add")
async def api_add_constraint(word: str = Form(...)):
    word = word.strip().lower()
    if not word or " " in word:
        return JSONResponse({"error": "Enter a single word."}, status_code=400)
    add_constraint(word)
    return {"constraints": get_constraints()}


@app.post("/api/constraints/remove")
async def api_remove_constraint(word: str = Form(...)):
    remove_constraint(word.strip().lower())
    return {"constraints": get_constraints()}


# ── Leaderboard ───────────────────────────────────────────────────────────────

@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(request: Request):
    leaderboard = get_leaderboard()
    ip = HOST_IP if HOST_IP else get_local_ip()
    register_url = PUBLIC_URL.rstrip("/") + "/" if PUBLIC_URL else f"http://{ip}:{PORT}/"
    return templates.TemplateResponse(
        "leaderboard.html",
        {
            "request": request,
            "leaderboard": leaderboard,
            "register_url": register_url,
        },
    )


@app.get("/api/leaderboard")
async def leaderboard_api():
    return get_leaderboard()


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
