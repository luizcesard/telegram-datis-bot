
import logging
import requests
import asyncio
from telegram import Update, Bot
from quart import Quart, request
from threading import Thread

from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import os


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)



BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE = "https://datis.clowd.io/api"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

application = Application.builder().token(BOT_TOKEN).build()


# --- ATIS Fetcher ---

async def fetch_atis(icao: str):
    url = f"{API_BASE}/{icao}"
    res = requests.get(url)
    logger.info(f"GET {url} => {res.status_code}")
    res.raise_for_status()
    data = res.json()
    logger.info(f"API response: {data}")
    return data

# --- Handlers ---

async def handle_icao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    if len(text) == 4 and text.isalpha():
        try:
            data = await fetch_atis(text)

            if isinstance(data, list) and data:
                atis = data[0].get("datis", "No ATIS text found.")
                await update.message.reply_text(f"{text} ATIS:\n{atis}")
            else:
                await update.message.reply_text(f"No ATIS found for {text}.")
        except Exception as e:
            logger.error(f"Error fetching {text}: {e}")
            await update.message.reply_text(f"Error fetching ATIS for {text}.")

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{API_BASE}/all"
        res = requests.get(url)
        res.raise_for_status()
        stations = res.json()

        messages = []
        for station in stations:
            icao = station.get("airport", "N/A")
            datis = station.get("datis")
            if datis:
                messages.append(f"{icao}:\n{datis}\n")

        if not messages:
            await update.message.reply_text("No ATIS data found.")
            return

        # Split into chunks if too long for Telegram (max ~4096 chars)
        chunk = ""
        for msg in messages:
            if len(chunk) + len(msg) > 4000:
                await update.message.reply_text(chunk)
                chunk = msg
            else:
                chunk += msg
        if chunk:
            await update.message.reply_text(chunk)

    except Exception as e:
        logger.error(f"Error fetching /all: {e}")
        await update.message.reply_text("An error occurred fetching all ATIS data.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to DATIS Bot!\n\n"
        "• Send any 4-letter ICAO code (e.g. KLAX)\n"
        "• Use /all to see active ATIS reports\n"
        "• Use /stations to see supported airports"
    )

async def stations_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get(f"{API_BASE}/stations")
        logger.info(f"GET /stations => {res.status_code}")
        res.raise_for_status()
        stations = res.json()
        
        if stations:
            station_list = ", ".join(sorted(stations))
            await update.message.reply_text(f"Supported stations:\n{station_list}")
        else:
            await update.message.reply_text("No stations available.")
    except Exception as e:
        logger.error(f"Error in /stations: {e}")
        await update.message.reply_text("Error fetching station list.")

def setup_handlers():
    try:
        # Clear any existing handlers
        logging.getLogger().handlers.clear()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("all", handle_all))
        application.add_handler(CommandHandler("stations", stations_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_icao))
        
        # Add error handler
        async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            logger.error(f"Error: {context.error}")
        application.add_error_handler(error_handler)
        
        logger.info("Starting bot...")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        raise

app = Quart(__name__)
# --- Flask Routes ---
@app.route('/webhook', methods=['POST'])
async def webhook():
    data = await request.get_json()
    update = Update.de_json(data, bot)
    await application.process_update(update)
    return 'OK', 200

@app.before_serving
async def startup():
    setup_handlers()
    await application.initialize()
    bot = application.bot
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    
@app.route("/")
def home():
    return "Bot is running."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
