import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")

# usernames who can test premium without paying
FREE_PREMIUM_USERS = {"zayniddin_1904", "nilfeyam"}

if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN")
