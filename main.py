import os
import logging
import gspread
from fastapi import FastAPI, Request, HTTPException
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import pandas as pd

# --- Biến môi trường ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1001234567890"))  # Ví dụ: -100.... (bắt buộc đúng định dạng)
GOOGLE_SHEET_JSON = os.environ.get("GOOGLE_SHEET_JSON")  # Chuỗi JSON (định dạng file key)
SHEET_NAME = os.environ.get("SHEET_NAME", "KeyData")
SHEET_TABS = os.environ.get("SHEET_TABS", "1")  # Có thể nhiều tab, phân tách dấu phẩy

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Load dữ liệu từ Google Sheets ---
def load_key_map_from_sheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        # Tạo file tạm json key (bắt buộc vì gspread dùng file)
        with open("temp_key.json", "w", encoding="utf-8") as f:
            f.write(GOOGLE_SHEET_JSON)

        credentials = ServiceAccountCredentials.from_json_keyfile_name("temp_key.json", scope)
        gc = gspread.authorize(credentials)

        sheet_file = gc.open(SHEET_NAME)
        tabs = [tab.strip() for tab in SHEET_TABS.split(",")]

        combined_df = pd.DataFrame()
        for tab_name in tabs:
            worksheet = sheet_file.worksheet(tab_name)
            df = pd.DataFrame(worksheet.get_all_records())
            if "key" not in df.columns or "name_file" not in df.columns or "message_id" not in df.columns:
                logger.warning(f"Tab {tab_name} không có đủ cột ['key','name_file','message_id']")
                continue
            df["key"] = df["key"].astype(str).str.strip().str.lower()
            combined_df = pd.concat([combined_df, df], ignore_index=True)

        key_map = {
            key: group[["name_file", "message_id"]].to_dict("records")
            for key, group in combined_df.groupby("key")
        }
        logger.info(f"Loaded {len(key_map)} keys from Google Sheets")
        return key_map
    except Exception as e:
        logger.error(f"Failed to load sheet: {e}")
        return {}

KEY_MAP = load_key_map_from_sheet()

# --- FastAPI app ---
app = FastAPI()

@app.on_event("startup")
async def startup():
    global bot_app
    bot_app = Application.builder().token(BOT_TOKEN).build()

    # Đăng ký handler
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_key))

    await bot_app.initialize()
    logger.info("Bot initialized")

@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    if token != BOT_TOKEN:
        logger.warning("Webhook called with invalid token")
        raise HTTPException(status_code=403, detail="Invalid token")

    try:
        body = await request.json()
        update = Update.de_json(body, bot_app.bot)
        await bot_app.process_update(update)
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

    return {"ok": True}

# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("♥️ Please send your KEY to receive the file.")

async def handle_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip().lower()
    chat_id = update.effective_chat.id

    if user_input in KEY_MAP:
        files_info = KEY_MAP[user_input]
        errors = 0

        for file_info in files_info:
            try:
                await context.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=CHANNEL_ID,
                    message_id=int(file_info["message_id"]),
                    protect_content=True
                )
                await update.message.reply_text(f"♥️ Your File \"{file_info['name_file']}\"")
            except Exception as e:
                logger.error(f"File send error: {e}")
                errors += 1

        if errors:
            await update.message.reply_text(
                "⚠️ Một số file bị lỗi khi gửi. Vui lòng liên hệ admin để được hỗ trợ.\n👉 https://t.me/A911Studio"
            )
    else:
        await update.message.reply_text("❌ KEY is incorrect. Please check again.")

