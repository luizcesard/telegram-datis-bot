
import logging
import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

API_BASE_URL = "https://datis.clowd.io/api"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the DATIS Bot!\n\n"
        "Available commands:\n"
        "/atis <ICAO> – Get ATIS info for an airport\n"
        "/all – List all current ATIS reports\n"
        "/stations – List all supported ICAO stations"
    )

async def atis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /atis <ICAO>")
        return
    icao = context.args[0].upper()
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
        else:
            await update.message.reply_text("No data found for this ICAO.")
    except Exception as e:
        logging.error(f"Error fetching ATIS for {icao}: {e}")
        await update.message.reply_text("Error fetching ATIS data.")

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

def main():
    app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("atis", atis))
    app.add_handler(CommandHandler("all", all_atis))
    app.add_handler(CommandHandler("stations", stations))
    app.run_polling()

if __name__ == "__main__":
    main()
