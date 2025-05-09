
import logging
import requests
import asyncio
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, Message
from quart import Quart, request
from threading import Thread
from uuid import uuid4
from datetime import datetime

from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler, InlineQueryHandler, CallbackContext
import os

#class FakeMessage:
#    def __init__(self, text, user, chat, bot):
#        self.text = text
#        self.from_user = user
#        self.chat = chat
#        self.bot = bot
#
#    async def reply_text(self, text, **kwargs):
#        await context.bot.send_message(chat_id=self.chat.id, text=text, **kwargs)

bot = None
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
    
# -- Helper ---
async def get_atis_text(icao_code: str):
    try:
        # Fetch the ATIS data from the API
        data = await fetch_atis(icao_code)

        if isinstance(data, list) and data:
            atis = data[0].get("datis", "No ATIS text found.")
            return f"{icao_code} ATIS:\n\n`{atis}`"  # Return the formatted ATIS message
        else:
            return f"No ATIS found for {icao_code}."  # No data found

    except Exception as e:
        logger.error(f"Error fetching ATIS for {icao_code}: {e}")
        return f"Error fetching ATIS for {icao_code}."  # Return an error message if something goes wrong
# --- Handlers ---

async def handle_icao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    icao_code = update.message.text.strip().upper()
    if len(icao_code) == 4 and icao_code.isalpha():
        atis_text = await get_atis_text(icao_code)
        await update.message.reply_text(atis_text, parse_mode="Markdown")

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
        stations = sorted(res.json())

        # Build 2-column keyboard
        keyboard = [
            [
                InlineKeyboardButton(text=code, callback_data=f"STATION_{code}")
                for code in stations[i:i+2]
            ]
            for i in range(0, len(stations), 2)
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select a station:", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error in /stations: {e}")
        await update.message.reply_text("Error fetching station list.")

# --- Callback Handlers ---

async def station_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("STATION_"):
        return

    icao_code = query.data.replace("STATION_", "")

    atis_text = await get_atis_text(icao_code)

    # Send the ATIS information to the user when they click the inline button
    await query.message.reply_text(atis_text, parse_mode="Markdown")

# --- Inline Query Handler ---

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip().upper()
    results = []

    if len(query) == 4 and query.isalpha():
        atis_text = await get_atis_text(query)

        results.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"ATIS for {query}",
                description=f"Tap to get ATIS for {query}",
                input_message_content=InputTextMessageContent(
                    message_text=atis_text,
                    parse_mode="Markdown"
                )
            )
        )

    await update.inline_query.answer(results, cache_time=1)

    
def setup_handlers():
    try:
        # Clear any existing handlers
        logging.getLogger().handlers.clear()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("all", handle_all))
        application.add_handler(CommandHandler("stations", stations_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_icao))
        application.add_handler(CallbackQueryHandler(station_callback_handler, pattern="^STATION_"))
        application.add_handler(InlineQueryHandler(inline_query_handler))

        # Add error handler
        async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            logger.error(f"Error: {context.error}")
        application.add_error_handler(error_handler)
        
        logger.info("Starting bot...")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        raise

app = Quart(__name__)
# --- Flask Routes --
@app.before_serving
async def startup():
    global bot
    setup_handlers()
    await application.initialize()
    bot = application.bot
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    
@app.route('/webhook', methods=['POST'])
async def webhook():
    if bot is None:
        return "Not ready", 503
    data = await request.get_json()
    update = Update.de_json(data, bot)
    await application.process_update(update)
    return 'OK', 200
    
@app.route("/")
def home():
    return "Bot is running."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
