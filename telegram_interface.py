from telegram.ext import ApplicationBuilder, CommandHandler
from config import BOT_TOKEN
from execution import place_trade
from strategy import check_signal

TRADING_ENABLED = False

async def start(update, context):
    global TRADING_ENABLED
    TRADING_ENABLED = True
    await update.message.reply_text("Trading Started.")

async def stop(update, context):
    global TRADING_ENABLED
    TRADING_ENABLED = False
    await update.message.reply_text("Trading Stopped.")

async def status(update, context):
    await update.message.reply_text(f"Trading: {TRADING_ENABLED}")

def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("status", status))
    app.run_polling()