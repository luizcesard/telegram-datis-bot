
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os

API_URL = "https://datis.clowd.io/api"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /metar, /atis, /stations, or /station <ICAO>.")

async def metar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /metar <ICAO>")
        return
    icao = context.args[0].upper()
    res = requests.get(f"{API_URL}/metar/{icao}")
    if res.ok:
        await update.message.reply_text(res.json().get("metar", "No METAR found."))
    else:
        await update.message.reply_text("Error fetching METAR.")

async def atis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /atis <ICAO>")
        return
    icao = context.args[0].upper()
    res = requests.get(f"{API_URL}/station/{icao}")
    if res.ok:
        station = res.json()
        atis_text = station.get("atis", {}).get("text", "No ATIS available.")
        await update.message.reply_text(atis_text)
    else:
        await update.message.reply_text("Error fetching ATIS.")

async def stations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = requests.get(f"{API_URL}/stations")
    if res.ok:
        station_list = ", ".join(res.json())
        await update.message.reply_text(f"Available stations:\n{station_list}")
    else:
        await update.message.reply_text("Error fetching station list.")

async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /station <ICAO>")
        return
    icao = context.args[0].upper()
    res = requests.get(f"{API_URL}/station/{icao}")
    if res.ok:
        station = res.json()
        name = station.get("name", "N/A")
        atis = station.get("atis", {}).get("text", "No ATIS.")
        await update.message.reply_text(f"{icao} - {name}\nATIS: {atis}")
    else:
        await update.message.reply_text("Error fetching station info.")

def main():
    app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("metar", metar))
    app.add_handler(CommandHandler("atis", atis))
    app.add_handler(CommandHandler("stations", stations))
    app.add_handler(CommandHandler("station", station))
    app.run_polling()

if __name__ == "__main__":
    main()
