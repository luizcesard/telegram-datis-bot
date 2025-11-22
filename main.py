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

bot = None
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE = "https://atis.info/api"
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
    
# -- Helper (MODIFIED) ---

async def get_atis_text(icao_code: str, atis_type: str = None):
    """
    atis_type can be: None, 'arr', 'dep'
    If None → return all available reports (arr, dep, and combined).
    If type requested but unavailable → fallback to combined.
    """

    try:
        data = await fetch_atis(icao_code)

        # Ensure list format (handling the "matrix of matrix" description)
        # The API seems to return a list of reports or a single report (dict).
        if isinstance(data, dict):
            data = [data]

        # Group reports by type
        atis_by_type = {"arr": [], "dep": [], "combined": []}

        for entry in data:
            # Handle possible nested lists or just ensure we're looking at a dict
            if isinstance(entry, dict):
                t = entry.get("type", "combined").lower()
                text = entry.get("datis", "")
                atis_by_type.setdefault(t, []).append(text)

        # --- If user requested specific type ('arr' or 'dep') (MODIFIED LOGIC) ---
        if atis_type and atis_type.lower() in ['arr', 'dep']:
            atis_lower = atis_type.lower()
            atis_upper = atis_type.upper()

            # 1. Try exact match first (arr or dep)
            if atis_by_type.get(atis_lower):
                atis = "\n\n".join(atis_by_type[atis_lower])
                return f"{icao_code} {atis_upper} ATIS:\n\n`{atis}`"

            # 2. Fallback to combined if only one exists and requested type is not found
            combined = atis_by_type.get("combined")
            if combined:
                # Fallback to combined, but inform the user it's combined
                return f"{icao_code} ATIS (Fallback to COMBINED):\n\n`{combined[0]}`"

            # 3. No requested type and no combined
            return f"No {atis_upper} ATIS available for {icao_code}. (No combined available for fallback)"

        # --- Return ALL ATIS (for KDFW and KSLC-like requests) ---
        output = []
        
        # Priority for the single combined report (KSLC-like)
        if len(data) == 1 and atis_by_type["combined"]:
             # This is the KSLC case: one report, treated as combined.
             output.append(f"{icao_code} ATIS (COMBINED):\n\n`{atis_by_type['combined'][0]}`")
             return "\n".join(output)

        # For KDFW-like case (multiple reports)
        output.append(f"{icao_code} ATIS:")

        if atis_by_type["dep"]:
            output.append("\n[DEPARTURE]\n\n" + "\n\n".join(atis_by_type["dep"]))

        if atis_by_type["arr"]:
            output.append("\n[ARRIVAL]\n\n" + "\n\n".join(atis_by_type["arr"]))
            
        # Include combined reports if they exist alongside arr/dep
        if len(atis_by_type["combined"]) > 1 or (len(atis_by_type["combined"]) == 1 and (atis_by_type["arr"] or atis_by_type["dep"])):
            output.append("\n[OTHER COMBINED REPORTS]\n\n" + "\n\n".join(atis_by_type["combined"]))


        if len(output) <= 1: # Only the header was appended
            return f"No ATIS found for {icao_code}."

        return "\n".join(output)

    except Exception as e:
        logger.error(f"Error fetching ATIS for {icao_code}: {e}")
        return f"Error fetching ATIS for {icao_code}."

# --- Handlers (MODIFIED) ---

# Remove: handle_icao (will be replaced with a simplified version or filtered)
# We will use MessageHandler(filters.TEXT & ~filters.COMMAND, handle_icao_only)
async def handle_icao_only(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    
    # Check if the input is a 4-letter ICAO code only
    if len(text) == 4 and text.isalpha():
        icao = text
        # Calling with atis_type=None triggers the logic for KDFW/KSLC requirement
        result = await get_atis_text(icao, atis_type=None)
        return await update.message.reply_text(result, parse_mode="Markdown")

    # If it's not a 4-letter ICAO code, it's not handled by this, or inform the user
    await update.message.reply_text("Send a 4-letter ICAO code (e.g., 'KDFW') or use a command like /arr KDFW.")


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
        "• Use /arr or /dep followed by ICAO (e.g., /arr KLAX)\n"
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

# Remove: atis_command (per request)
# async def atis_command(update: Update, context: ContextTypes.DEFAULT_TYPE): ...

async def arr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /arr ICAO")
    
    icao = context.args[0].upper()
    text = await get_atis_text(icao, atis_type="arr") # Explicitly request 'arr'
    await update.message.reply_text(text, parse_mode="Markdown")

async def dep_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /dep ICAO")
    
    icao = context.args[0].upper()
    text = await get_atis_text(icao, atis_type="dep") # Explicitly request 'dep'
    await update.message.reply_text(text, parse_mode="Markdown")

# --- Callback Handlers ---

async def station_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("STATION_"):
        return

    icao_code = query.data.replace("STATION_", "")

    # Calls the logic for KDFW/KSLC requirement
    atis_text = await get_atis_text(icao_code)

    # Send the ATIS information to the user when they click the inline button
    await query.message.reply_text(atis_text, parse_mode="Markdown")

# --- Inline Query Handler ---

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip().upper()
    results = []

    if len(query) == 4 and query.isalpha():
        # Calls the logic for KDFW/KSLC requirement
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
        
        # New handler for ICAO code only (KDFW/KSLC behavior)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'^[A-Z]{4}$'), handle_icao_only))
        
        # Remove the previous general handle_icao, and its complexity
        
        application.add_handler(CallbackQueryHandler(station_callback_handler, pattern="^STATION_"))
        application.add_handler(InlineQueryHandler(inline_query_handler))
        
        # Keep /arr and /dep
        # application.add_handler(CommandHandler("atis", atis_command)) # REMOVED
        application.add_handler(CommandHandler("arr", arr_command))
        application.add_handler(CommandHandler("dep", dep_command))

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
    
