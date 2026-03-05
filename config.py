from dotenv import load_dotenv
import os

load_dotenv()

TARGET_SENTENCE = "Blue Schwan fliegt von Neuschwanstein nach Schweinfurt."
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MAX_ATTEMPTS = 5
MAX_INPUT_TOKENS = 300
GAME_DURATION_SECONDS = 360  # 6 minutes per player
MODEL = "gpt-4o-mini"
PORT = 8000
HOST_IP = os.getenv("HOST_IP", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "")  # e.g. https://xxxx.ngrok-free.app
