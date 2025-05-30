import os
import json
import logging

import gspread
from fastapi import FastAPI, Request
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("main")

# --- Biến môi trường ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
GOOGLE_SHEET_JSON = os.environ.get("GOOGLE_SHEET_JSON")
SHEET_NAME = os.environ.get("SHEET_NAME", "KeyData")
SHEET_TABS = os.environ.get("SHEET_TABS", "1").split(",")

if not all([BOT_TOKEN, CHANNEL_ID, GOOGLE_SHEET_JSON, SHEET_NAME]):
    raise ValueError("❌ Thiếu biến môi trường: BOT_TOKEN, CHANNEL_ID, GOOGLE_SHEET_JSON, SHEET_NAME")

# --- Google Sheets ---
def get_gsheet_client():
    try:
        with open("temp_key.json", "w", encoding="utf-8") as f:
            f.write(GOOGLE_SHEET_JSON)

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = ServiceAccountCredentials.from_json_keyfile_name("temp_key.json", scope)
        return gspread.authorize(credentials)
    except Exception as e:
        logger.error(f"❌ Không thể khởi tạo Google Sheet: {e}")
        raise

try:
    gc = get_gsheet_client()
    sheet = gc.open(SHEET_NAME)
    worksheet = sheet.worksheet(SHEET_TABS[0].strip())
    logger.info(f"✅ Kết nối Google Sheet thành công: {SHEET_NAME} - Tab: {SHEET_TABS[0]}")
except Exception as e:
    logger.error(f"❌ Lỗi khi kết nối Google Sheets: {e}")
    raise

# --- FastAPI + Bot ---
app = FastAPI()

@app.on_event("startup")
async def startup():
    global bot_app
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    await bot_app.initialize()
    logger.info("✅ Bot đã khởi động thành công.")

@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    if token != BOT_TOKEN:
        logger.warning("⚠️ Webhook nhận sai token.")
        return {"error": "Invalid token"}

    try:
        body = await request.json()
        update = Update.de_json(body, bot_app.bot)
        await bot_app.process_update(update)
        logger.info("📩 Webhook đã xử lý một update.")
    except Exception as e:
        logger.error(f"❌ Webhook xử lý lỗi: {e}")
    return {"ok": True}

# --- Xử lý file RAR từ Channel ---
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message

    if not message or not message.document:
        logger.info("⚠️ Không có message/document hợp lệ.")
        return

    chat_id = update.effective_chat.id
    logger.info(f"📨 Nhận file từ chat_id={chat_id}")

    if chat_id != CHANNEL_ID:
        logger.info(f"❌ Bỏ qua vì không đúng CHANNEL_ID (got {chat_id}, expected {CHANNEL_ID})")
        return

    file_name = message.document.file_name
    message_id = message.message_id

    if not file_name.lower().endswith(".rar"):
        logger.info(f"⚠️ Bỏ qua file không phải .rar: {file_name}")
        return

    try:
        worksheet.append_row([file_name, message_id])
        logger.info(f"✅ Đã lưu file vào Sheet: {file_name}, message_id: {message_id}")
    except Exception as e:
        logger.error(f"❌ Lỗi ghi Google Sheet: {e}")
