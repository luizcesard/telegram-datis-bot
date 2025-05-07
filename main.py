
import logging
import requests
from telegram import Update
from flask import Flask, request
from threading import Thread

from webserver import keep_alive
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
application = ApplicationBuilder().token(BOT_TOKEN).build()

API_BASE = "https://datis.clowd.io/api"

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
application = ApplicationBuilder().token(BOT_TOKEN).build()

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

def main():
    try:
        # Clear any existing handlers
        logging.getLogger().handlers.clear()
        
        app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("all", handle_all))
        app.add_handler(CommandHandler("stations", stations_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_icao))
        
        # Add error handler
        async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            logger.error(f"Error: {context.error}")
        app.add_error_handler(error_handler)
        
        logger.info("Starting bot...")
        # Start bot
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Critical error: {e}")
        raise

# --- Flask Routes ---
@app.route('/webhook', methods=["POST", "GET"])
async def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)  # Using await instead of asyncio.run
        return "OK", 200
    return "Webhook is running", 200
    
@app.route("/")
def home():
    return "Bot is running."

if __name__ == "__main__":
    import asyncio

    async def set_webhook():
        await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")

    asyncio.run(set_webhook())
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
