from dotenv import load_dotenv
import os

load_dotenv()

TARGET_SENTENCE = "Blue Schwan fliegt von Neuschwanstein nach Schweinfurt."
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MAX_ATTEMPTS = 10
MAX_INPUT_TOKENS = 500
GAME_DURATION_SECONDS = 1200  # 10 minutes per player
MODEL = "gpt-4o-mini"
PORT = 8000
HOST_IP = os.getenv("HOST_IP", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "")  # e.g. https://xxxx.ngrok-free.app
