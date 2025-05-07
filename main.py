
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import os

API_BASE = "https://datis.clowd.io/api"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ATIS Fetcher ---

async def fetch_atis(icao: str):
    url = f"{API_BASE}/{icao}"
    res = requests.get(url)
    logger.info(f"GET {url} => {res.status_code}")
    res.raise_for_status()
    return res.json()

# --- Handlers ---

async def handle_icao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    if len(text) == 4 and text.isalpha():
        try:
            data = await fetch_atis(text)
            if "atis" in data and data["atis"]:
                atis_text = data["atis"].get("text", "No ATIS text.")
                await update.message.reply_text(f"{text} ATIS:\n{atis_text}")
            else:
                await update.message.reply_text(f"No ATIS found for {text}.")
        except Exception as e:
            logger.error(f"Error fetching {text}: {e}")
            await update.message.reply_text(f"Error fetching ATIS for {text}.")
    else:
        await update.message.reply_text("Send a valid 4-letter ICAO code (e.g. KLAX).")

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get(f"{API_BASE}/all")
        logger.info(f"GET /all => {res.status_code}")
        res.raise_for_status()
        data = res.json()

        if not isinstance(data, list) or not data:
            await update.message.reply_text("No data returned.")
            return

        message = ""
        for entry in data[:5]:  # Limit to 5 stations
            icao = entry.get("icao", "N/A")
            name = entry.get("name", "Unknown")
            atis = entry.get("atis", {}).get("text", "No ATIS text.")
            freq = entry.get("frequency", "N/A")
            message += f"{icao} – {name}\nFreq: {freq}\n{atis}\n\n"
        
        await update.message.reply_text(message[:4000])  # Telegram message limit
    except Exception as e:
        logger.error(f"Error in /all: {e}")
        await update.message.reply_text("Error fetching all ATIS data.")

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
        app.add_handler(CommandHandler("all", all_command))
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

if __name__ == "__main__":
    main()
