import qrcode
from io import BytesIO
import gspread
import datetime
import asyncio
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from bakong_khqr import KHQR

# === CONFIGURATION ===
BOT_TOKEN = "7722473238:AAGQgesD0-KS7QhjOb3Ra3RfzN2j3rN6xYc"
ADMIN_CHAT_ID = 5549600755
GOOGLE_SHEET_NAME = "Orders"
CREDENTIALS_FILE = "AllGenz/helical-crowbar-393009-121b689f975e.json"

# 🔐 Bakong
BAKONG_JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiNDg4MGE3YmE1NGZmNGQ2OCJ9LCJpYXQiOjE3NDkyODI1NTQsImV4cCI6MTc1NzA1ODU1NH0.c4eAiTwN1duKKD_pyToZwH1uBD2PhbnmWNpTuNKa6P8"
BAKONG_RECEIVER_CODE = "855974871434"
BAKONG_RECEIVER_NAME = "AllGenzStore"
khqr = KHQR(BAKONG_JWT_TOKEN)

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

# === In-memory location store ===
user_locations = {}

# === PAYMENT STATUS CHECK ===
async def check_payment_status(md5_hash: str, user_chat_id: int, sheet_row: int, context: ContextTypes.DEFAULT_TYPE):
    for _ in range(20):  # 1 minute (3s × 20)
        await asyncio.sleep(3)
        try:
            status = khqr.check_payment(md5_hash)
            if status == "PAID":
                paid_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sheet.update_cell(sheet_row, 6, "PAID")
                sheet.update_cell(sheet_row, 7, paid_at)
                await context.bot.send_message(chat_id=user_chat_id, text="✅ អ្នកបានបង់ប្រាក់រួចរាល់។")
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"✅ អតិថិជនបានបង់ប្រាក់ (row {sheet_row})")
                return
        except Exception as e:
            print(f"Error checking payment status: {e}")
    
    sheet.update_cell(sheet_row, 6, "UNPAID")
    await context.bot.send_message(chat_id=user_chat_id, text="❌ អ្នកមិនបានបង់ប្រាក់ក្នុងរយៈពេល 1 នាទី។")
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"❌ អតិថិជនមិនបានបង់ប្រាក់ (row {sheet_row})")

# === START COMMAND ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[KeyboardButton(text=p)] for p in PRODUCTS]
    kb.append([KeyboardButton(text="📍 ផ្ញើទីតាំង", request_location=True)])
    await update.message.reply_text(
        "សូមជ្រើសរើសផលិតផលដែលអ្នកចង់ទិញ៖",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

# === PRODUCT ORDER HANDLER ===
async def handle_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    product = update.message.text
    price = PRODUCTS.get(product)

    if price:
        try:
            # Generate QR
            qr_string = khqr.create_qr(
                bank_account='big_boss@wing',
                merchant_name='YULEANG POVCHOMREOUN',
                merchant_city='Phnom Penh',
                amount=price,
                currency='KHR',
                store_label='AllGenz Store',
                phone_number=BAKONG_RECEIVER_CODE,
                bill_number=f"ORDER-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
                terminal_label='Bot-QR',
                static=False
            )

            # Send QR
            qr = qrcode.make(qr_string)
            bio = BytesIO()
            bio.name = "qr.png"
            qr.save(bio, "PNG")
            bio.seek(0)

            await update.message.reply_photo(
                photo=bio,
                caption=f"🧾 សម្រាប់ {product}\n💰 តម្លៃ: {price}៛\n📱 សូមស្កេន QR ដើម្បីបង់ប្រាក់។"
            )

            # Log to Google Sheet
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            location_str = user_locations.get(user.id, "")
            sheet.append_row([timestamp, user.id, user.username or "", product, price, "", "", location_str])
            sheet_row = len(sheet.get_all_values())

            # Notify admin
            username_link = f"@{user.username}" if user.username else f"tg://user?id={user.id}"
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"📦 បញ្ជាទិញ៖ {product} - {price}៛\n👤 អ្នកប្រើ: {username_link}"
            )

            # Start background payment check
            md5 = khqr.generate_md5(qr_string)
            asyncio.create_task(check_payment_status(md5, update.effective_chat.id, sheet_row, context))

        except Exception as e:
            await update.message.reply_text(f"❌ បរាជ័យក្នុងការបង្កើត QR Code: {str(e)}")

# === LOCATION HANDLER ===
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    location = update.message.location
    maps_url = f"https://maps.google.com/?q={location.latitude},{location.longitude}"
    user_locations[user.id] = maps_url

    await update.message.reply_text(f"🗺️ ទីតាំងបានទទួល: {maps_url}")
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"📍 ទីតាំងពី @{user.username or user.id}: {maps_url}"
    )

# === BOT START ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_product))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    print("🤖 Bot is running...")
    app.run_polling()
