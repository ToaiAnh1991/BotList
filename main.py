import os
import json
import logging
import asyncio

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --- Lấy biến môi trường ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))  # bắt buộc phải có, vd: -1001234567890
GSHEETS_JSON = os.getenv("GSHEETS_JSON")
GSHEET_NAME = os.getenv("GSHEET_NAME", "Sheet1")

if not all([BOT_TOKEN, CHANNEL_ID, GSHEETS_JSON]):
    raise ValueError("Bạn phải đặt BOT_TOKEN, CHANNEL_ID, GSHEETS_JSON trong biến môi trường.")

# --- Khởi tạo Google Sheets API ---
def get_sheets_service():
    creds_json = json.loads(GSHEETS_JSON)
    creds = Credentials.from_service_account_info(creds_json, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    service = build('sheets', 'v4', credentials=creds)
    return service.spreadsheets()

sheets_api = get_sheets_service()

# --- Hàm thêm dữ liệu vào Google Sheet ---
def append_row_to_sheet(filename: str, message_id: int):
    spreadsheet_id = sheets_api.spreadsheetId if hasattr(sheets_api, 'spreadsheetId') else None
    # Bạn phải đặt ID spreadsheet của bạn (từ URL của Google Sheets) vào biến môi trường nếu muốn dùng nhiều sheet, 
    # hoặc hardcode ở đây.
    # Ví dụ: SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
    # Ở đây, giả sử biến môi trường chứa spreadsheet id luôn, bạn có thể thêm:
    SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
    if not SPREADSHEET_ID:
        raise ValueError("Bạn phải đặt biến môi trường SPREADSHEET_ID chứa ID bảng tính Google Sheets.")

    body = {
        "values": [[filename, message_id]]
    }
    result = sheets_api.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=GSHEET_NAME,
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()
    logging.info(f"Đã thêm dòng: {filename}, {message_id} vào Google Sheets (Response: {result.get('updates')})")


# --- Hàm xử lý tin nhắn ---
async def handle_rar_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    # Chỉ nhận tin nhắn từ channel đúng id
    if update.effective_chat and update.effective_chat.id != CHANNEL_ID:
        return

    if msg.document and msg.document.file_name.lower().endswith(".rar"):
        filename = msg.document.file_name
        message_id = msg.message_id
        logging.info(f"Nhận file .rar: {filename}, message_id: {message_id}")

        try:
            append_row_to_sheet(filename, message_id)
        except Exception as e:
            logging.error(f"Lỗi khi ghi Google Sheets: {e}")


# --- Hàm chạy bot ---
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.Document.ALL, handle_rar_file))
    logging.info("Bot đã chạy, chờ nhận file .rar từ channel...")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
