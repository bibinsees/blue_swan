import os
import socket
from contextlib import asynccontextmanager

import qrcode
import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI

from config import HOST_IP, MAX_ATTEMPTS, MODEL, OPENAI_API_KEY, PORT, TARGET_SENTENCE
from database import (
    create_attempt,
    create_player,
    get_leaderboard,
    get_max_attempts,
    get_model,
    get_player_attempts,
    get_player_by_id,
    get_player_by_email,
    get_target_sentence,
    set_max_attempts,
    set_model,
    set_target_sentence,
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
    url = f"http://{ip}:{PORT}/"
    img = qrcode.make(url)
    img.save("static/qrcode.png")
    print(f"\n  Game URL: {url}")
    print(f"  Leaderboard: http://{ip}:{PORT}/leaderboard\n")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(default_sentence=TARGET_SENTENCE)
    set_max_attempts(MAX_ATTEMPTS)
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
    existing = get_player_by_email(email)
    if existing:
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

    if not prompt_text.strip():
        return JSONResponse({"error": "Prompt cannot be empty."}, status_code=400)

    response = client.chat.completions.create(
        model=get_model(),
        messages=[{"role": "user", "content": prompt_text}],
    )

    llm_response = response.choices[0].message.content
    input_tokens = response.usage.prompt_tokens
    is_exact_match = llm_response.strip() == get_target_sentence()
    attempt_number = len(attempts) + 1
    model_used = get_model()

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

    return JSONResponse(
        {
            "llm_response": llm_response,
            "input_tokens": input_tokens,
            "is_exact_match": is_exact_match,
            "attempt_number": attempt_number,
            "attempts_remaining": attempts_remaining,
            "model_used": model_used,
        }
    )


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "current_sentence": get_target_sentence(),
            "current_max_attempts": get_max_attempts(),
            "current_model": get_model(),
            "saved": False,
        },
    )


@app.post("/admin")
async def admin_update(
    request: Request,
    target_sentence: str = Form(...),
    max_attempts: int = Form(...),
    model: str = Form(...),
):
    set_target_sentence(target_sentence.strip())
    set_max_attempts(max(1, max_attempts))
    set_model(model.strip())
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "current_sentence": target_sentence.strip(),
            "current_max_attempts": max(1, max_attempts),
            "current_model": model.strip(),
            "saved": True,
        },
    )


# ── Leaderboard ───────────────────────────────────────────────────────────────

@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(request: Request):
    leaderboard = get_leaderboard()
    ip = HOST_IP if HOST_IP else get_local_ip()
    return templates.TemplateResponse(
        "leaderboard.html",
        {
            "request": request,
            "leaderboard": leaderboard,
            "register_url": f"http://{ip}:{PORT}/",
        },
    )


@app.get("/api/leaderboard")
async def leaderboard_api():
    return get_leaderboard()


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
