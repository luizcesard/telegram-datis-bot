import logging
import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler

# API base
API_BASE_URL = "https://datis.clowd.io/api"

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to DATIS Bot! Use /atis <ICAO> to get ATIS information.")

async def atis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide an ICAO code. Example: /atis KLAX")
        return

    icao = context.args[0].upper()
    try:
        response = requests.get(f"{API_BASE_URL}/{icao}")
        if response.status_code == 200:
            data = response.json()
            atis_text = data.get('atis', {}).get('text', 'No ATIS available')
            await update.message.reply_text(f"ATIS for {icao}:\n{atis_text}")
        else:
            await update.message.reply_text(f"Could not fetch ATIS for {icao}")
    except Exception as e:
        logger.error(f"Error fetching ATIS: {e}")
        await update.message.reply_text("An error occurred while fetching ATIS information")

def main():
    app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("atis", atis))

    # Start the bot
    app.run_polling()

if __name__ == '__main__':
    main()