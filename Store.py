import qrcode
from io import BytesIO
import gspread
import requests
import datetime

from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# === CONFIGURATION ===
BOT_TOKEN = "7722473238:AAGQgesD0-KS7QhjOb3Ra3RfzN2j3rN6xYc"  # 🔁 Replace this
ADMIN_CHAT_ID = 5549600755
GOOGLE_SHEET_NAME = "Orders"
CREDENTIALS_FILE = "turnkey-axiom-462210-e1-930f4702efad.json"

# 🔐 Bakong API
BAKONG_API_URL = "https://api-open.bakong.nbc.gov.kh/api/v1/khqr/generate"
BAKONG_JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiNDg4MGE3YmE1NGZmNGQ2OCJ9LCJpYXQiOjE3NDkyODI1NTQsImV4cCI6MTc1NzA1ODU1NH0.c4eAiTwN1duKKD_pyToZwH1uBD2PhbnmWNpTuNKa6P8"  # 🔁 Replace with your token
BAKONG_RECEIVER_CODE = "855974871434"
BAKONG_RECEIVER_NAME = "AllGenzStore"

PRODUCTS = {
    "🍚 អង្ករ": 3000,
    "🥤 ទឹកផ្លែឈើ": 2000,
    "🍜 មីកញ្ចប់": 1500
}

# === GOOGLE SHEETS SETUP ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)
sheet = client.open(GOOGLE_SHEET_NAME).sheet1

# === HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[KeyboardButton(text=p)] for p in PRODUCTS]
    kb.append([KeyboardButton(text="📍 ផ្ញើទីតាំង", request_location=True)])
    await update.message.reply_text(
        "សូមជ្រើសរើសផលិតផលដែលអ្នកចង់ទិញ៖",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def handle_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    product = update.message.text
    price = PRODUCTS.get(product)

    if price:
        # Generate KHQR from Bakong API
        headers = {
            "Authorization": f"Bearer {BAKONG_JWT_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "receiverCode": BAKONG_RECEIVER_CODE,
            "receiverName": BAKONG_RECEIVER_NAME,
            "amount": str(price),
            "currency": "KHR"
        }

        try:
            res = requests.post(BAKONG_API_URL, headers=headers, json=payload)
            if res.status_code == 200 and "qrCode" in res.json().get("payload", {}):
                qr_string = res.json()["payload"]["qrCode"]
                qr = qrcode.make(qr_string)
                bio = BytesIO()
                bio.name = "qr.png"
                qr.save(bio, "PNG")
                bio.seek(0)

                await update.message.reply_photo(
                    photo=bio,
                    caption=f"🧾 សម្រាប់ {product}\n💰 តម្លៃ: {price}៛\n📱 សូមស្កេន QR ដើម្បីបង់ប្រាក់។"
                )
            else:
                await update.message.reply_text("❌ បរាជ័យក្នុងការបង្កើត QR Code! សូមព្យាយាមម្ដងទៀត។")
                return

            # Log to Google Sheets
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([timestamp, user.id, user.username or "", product, price])

            # Notify admin
            username_link = f"@{user.username}" if user.username else f"tg://user?id={user.id}"
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"📦 បញ្ជាទិញថ្មី៖ {product} - {price}៛\n👤 អ្នកប្រើ: {username_link}"
            )

        except Exception as e:
            await update.message.reply_text(f"❌ បរាជ័យក្នុងការបង្កើត QR Code:\n{str(e)}")

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = update.message.location
    await update.message.reply_text(
        f"🗺️ ទីតាំងបានទទួល: https://maps.google.com/?q={location.latitude},{location.longitude}"
    )
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"📍 ទីតាំងពី @{update.message.from_user.username or update.message.from_user.id}: "
             f"https://maps.google.com/?q={location.latitude},{location.longitude}"
    )

# === MAIN ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_product))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    print("🤖 Bot is running...")
    app.run_polling()
