
import logging
import os
import re
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

API_BASE_URL = "https://datis.clowd.io/api"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the DATIS Bot!\n\n"
        "You can:\n"
        "• Send a 4-letter ICAO code (e.g. KLAX) to get ATIS\n"
        "• Use /all to get all ATIS reports\n"
        "• Use /stations to list all supported ICAOs"
    )

async def fetch_atis_for(update: Update, icao: str):
    try:
        res = requests.get(f"{API_BASE_URL}/{icao}")
        if res.status_code == 200:
            data = res.json()
            name = data.get("name", "Unknown Airport")
            freq = data.get("frequency", "N/A")
            atis_text = data.get("atis", {}).get("text", "No ATIS text.")
            await update.message.reply_text(
                f"{icao} – {name}\nFreq: {freq}\n\nATIS:\n{atis_text}"
            )
        elif res.status_code == 404:
            await update.message.reply_text(f"No ATIS found for {icao}.")
        else:
            await update.message.reply_text(f"Failed to fetch ATIS for {icao}.")
    except Exception as e:
        logging.error(f"Error fetching ATIS for {icao}: {e}")
        await update.message.reply_text("Error fetching ATIS data.")

async def atis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /atis <ICAO>")
        return
    icao = context.args[0].upper()
    await fetch_atis_for(update, icao)

async def all_atis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get(f"{API_BASE_URL}/all")
        if res.status_code == 200:
            data = res.json()
            if not data:
                await update.message.reply_text("No active ATIS reports available.")
                return
            reply = "\n\n".join(
                f"{item['icao']} – {item['name']}\nFreq: {item['frequency']}\nATIS: {item['atis']['text']}"
                for item in data
            )
            await update.message.reply_text(reply[:4000])
        else:
            await update.message.reply_text("Failed to fetch ATIS reports.")
    except Exception as e:
        logging.error(f"Error in /all: {e}")
        await update.message.reply_text("Error fetching all ATIS data.")

async def stations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get(f"{API_BASE_URL}/stations")
        if res.status_code == 200:
            stations = res.json()
            station_list = ", ".join(sorted(stations))
            await update.message.reply_text(f"Supported ICAO stations:\n{station_list}")
        else:
            await update.message.reply_text("Failed to fetch stations.")
    except Exception as e:
        logging.error(f"Error in /stations: {e}")
        await update.message.reply_text("Error fetching station list.")

async def handle_icao_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    if re.fullmatch(r"[A-Z]{4}", text):
        await fetch_atis_for(update, text)

def main():
    app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("atis", atis_command))
    app.add_handler(CommandHandler("all", all_atis))
    app.add_handler(CommandHandler("stations", stations))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_icao_message))
    app.run_polling()

if __name__ == "__main__":
    main()
