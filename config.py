import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = "7995797587:AAGOt62-BriOTJsvN-gHfKMd6R4_VeGabJg"
PAYMENT_TOKEN = "398062629:TEST:999999999_F91D8F69C042267444B74CC0B3C747757EB0E065"

ADMINS = [7000454062]
ORDER_CHANNEL = -1002770150250
PRODUCT_CHANNEL = -1002385607008
BOT_USERNAME = "TopTovarsBot"
TASDIQID = 7948171315

DB_PATH = "database.sqlite"
DATABASE_FILE = "bot_database.db"
DATABASE_URL = os.getenv("DATABASE_URL", "bot_database.db")
HELPER_ID = 8039363087

MIN_PRODUCT_PRICE = 50000
DEFAULT_PRODUCT_PRICE = 50000
FIXED_PAYMENT_AMOUNT = 50000

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

LOG_LEVEL = "DEBUG"
DEBUG = True

CHANNELS = [
    {
        "id": os.getenv("CHANNEL_1_ID", "-1002785798673"),
        "name": os.getenv("CHANNEL_1_NAME", "Kanal 1"),
        "url": os.getenv("CHANNEL_1_URL", "https://t.me/channel1")
    }
]

GOOGLE_SHEETS_CREDENTIALS_FILE = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "credentials.json")
GOOGLE_SHEETS_URL = os.getenv("GOOGLE_SHEETS_URL", "")

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8443"))
