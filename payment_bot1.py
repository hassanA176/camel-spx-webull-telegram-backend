# indicator_bot.py (بوت اشتراك المؤشر - محدث بالكامل حسب طلبك)

import sqlite3
from datetime import datetime, timedelta
import requests
import os
import base64
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
STREAM_BASE_URL = "https://stream-app-service.streampay.sa"
STREAM_API_KEY = os.getenv('STREAM_API_KEY', '')
STREAM_API_SECRET = os.getenv('STREAM_API_SECRET', '')
SUCCESS_REDIRECT_URL = "https://t.me/CAMELSPX_INDICATORBOT?start=paid_success"
FAILURE_REDIRECT_URL = "https://t.me/CAMELSPX_INDICATORBOT?start=paid_failed"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'indicator_users.db')

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

PACKAGES_API_URL = "http://127.0.0.1:5000/api/indicator_packages"
BOT_API_KEY = os.getenv('BOT_API_KEY', '')
NOTIFICATION_CHAT_ID = os.getenv('TELEGRAM_NOTIFICATION_CHAT_ID', '')

def get_packages():
    try:
        headers = {'X-Bot-API-Key': BOT_API_KEY}
        resp = requests.get(PACKAGES_API_URL, headers=headers, timeout=10)
        if resp.status_code == 200:
            return {pkg['id']: pkg for pkg in resp.json() if 'id' in pkg}
        else:
            logger.error(f"فشل جلب باقات المؤشر: {resp.status_code}")
            return {}
    except Exception as e:
        logger.exception("خطأ في جلب باقات المؤشر: %s", e)
        return {}

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    chat_id INTEGER PRIMARY KEY,
                    name TEXT,
                    username TEXT,
                    phone_number TEXT,
                    tradingview_username TEXT,
                    paid INTEGER DEFAULT 0,
                    subscription_package TEXT,
                    subscription_end TIMESTAMP,
                    first_seen TIMESTAMP,
                    package_price REAL DEFAULT 0
                )''')
    conn.commit()
    conn.close()
    print("✅ قاعدة بيانات المؤشر جاهزة.")

def _get_stream_headers() -> dict:
    token = base64.b64encode(f"{STREAM_API_KEY}:{STREAM_API_SECRET}".encode()).decode()
    return {
        "x-api-key": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def create_payment_link(package_id: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    packages = get_packages()
    if package_id not in packages:
        return None
    pkg = packages[package_id]

    url = f"{STREAM_BASE_URL}/api/v2/payment_links"
    payload = {
        "name": pkg["name"],
        "description": f"اشتراك مؤشر {pkg['name']}",
        "items": [{"product_id": pkg["product_id"], "quantity": 1}],
        "contact_information_type": "PHONE",
        "currency": "SAR",
        "max_number_of_payments": 1,
        "success_redirect_url": SUCCESS_REDIRECT_URL,
        "failure_redirect_url": FAILURE_REDIRECT_URL,
        "metadata": {
            "chat_id": str(chat_id),
            "package_id": package_id,
            "full_name": context.user_data.get('full_name', 'غير معروف'),
            "username": context.user_data.get('username', ''),
            "phone_number": context.user_data.get('phone_number', '')
        }
    }

    headers = _get_stream_headers()
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("url") or data.get("data", {}).get("url")
    except Exception as e:
        logger.exception("Error creating payment link: %s", e)
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    context.user_data.clear()  # تنظيف البيانات عند كل /start
    context.user_data['chat_id'] = user.id
    context.user_data['full_name'] = user.full_name
    context.user_data['username'] = user.username or ''

    if args and args[0] == "paid_success":
        package_id = context.user_data.get('selected_package_id')
        phone = context.user_data.get('phone_number')
        tv_user = context.user_data.get('tradingview_username')

        if not all([package_id, phone, tv_user]):
            await update.message.reply_text("⚠️ خطأ: بيانات ناقصة. ابدأ من جديد بكتابة /start")
            return

        packages = get_packages()
        if package_id not in packages:
            await update.message.reply_text("❌ الباقة غير متوفرة حالياً.")
            return

        pkg = packages[package_id]
        end_date = (datetime.now() + timedelta(days=int(pkg['duration_days']))).isoformat()

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO users 
                     (chat_id, name, username, phone_number, tradingview_username, paid, 
                      subscription_package, subscription_end, first_seen, package_price)
                     VALUES (?, ?, ?, ?, ?, 1, ?, ?, 
                             COALESCE((SELECT first_seen FROM users WHERE chat_id = ?), ?), ?)""",
                  (user.id, user.full_name, user.username, phone, tv_user,
                   pkg['name'], end_date, user.id, datetime.now().isoformat(), float(pkg['price'])))
        conn.commit()
        conn.close()

        # إشعار للأدمن
        try:
            await context.bot.send_message(
                chat_id=NOTIFICATION_CHAT_ID,
                text=f"🔔 دفع ناجح - بوت المؤشر\n\n"
                     f"الاسم: {user.full_name}\n"
                     f"يوزر: @{user.username or 'لا يوجد'}\n"
                     f"رقم الهاتف: {phone}\n"
                     f"TradingView Username: {tv_user}\n"
                     f"الباقة: {pkg['name']} ({pkg['price']} ريال - {pkg['duration_days']} يوم)"
            )
        except Exception as e:
            logger.warning(f"فشل إرسال الإشعار للأدمن: {e}")

        await update.message.reply_text(
            f"🎉 تهانينا يا {user.first_name}!\n\n"
            f"تم تفعيل اشتراك المؤشر **{pkg['name']}** بنجاح ✅\n"
            f"مدة الاشتراك: {pkg['duration_days']} يوم\n\n"
            f"اسم TradingView الخاص بك: `{tv_user}`\n"
            f"سيتم إضافته يدويًا قريبًا إن شاء الله.\n"
            f"شكرًا لثقتك بنا! 🚀",
            parse_mode='Markdown'
        )
        return

    elif args and args[0] == "paid_failed":
        await update.message.reply_text("❌ فشل الدفع. حاول مرة أخرى بكتابة /start")
        return

    # القائمة الرئيسية
    keyboard = [
        [InlineKeyboardButton("⭐ التسجيل والاشتراك في المؤشر", callback_data='register')],
        [InlineKeyboardButton("📞 الدعم الفني والمساعدة", callback_data='support')]
    ]
    await update.message.reply_text(
        "👋 أهلاً وسهلاً بك في بوت اشتراك المؤشر!\n\nاختر من القائمة التالية:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)  # إزالة الكيبورد القديم

    if query.data == 'register':
        keyboard = [[KeyboardButton("شارك رقم هاتفك للمتابعة", request_contact=True)]]
        await query.message.reply_text(
            "للمتابعة في التسجيل، يرجى مشاركة رقم هاتفك أولاً:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )

    elif query.data.startswith('sub_'):
        package_id = query.data.split('_', 1)[1]
        context.user_data['selected_package_id'] = package_id

        packages = get_packages()
        if package_id not in packages:
            await query.message.reply_text("⚠️ عفواً، هذه الباقة غير متوفرة حالياً.")
            return

        pkg = packages[package_id]

        # تحقق من وجود الرقم واسم TradingView
        if not context.user_data.get('phone_number'):
            await query.message.reply_text("⚠️ يرجى مشاركة رقم هاتفك أولاً.")
            return
        if not context.user_data.get('tradingview_username'):
            await query.message.reply_text("⚠️ يرجى إرسال اسم مستخدم TradingView أولاً.")
            return

        payment_url = create_payment_link(package_id, query.from_user.id, context)
        if payment_url:
            await query.message.reply_text(
                f"📦 **{pkg['name']}**\n"
                f"💰 السعر: {pkg['price']} ريال\n"
                f"⏳ المدة: {pkg['duration_days']} يوم\n\n"
                f"اضغط على الرابط لإتمام الدفع:\n{payment_url}\n\n"
                f"بعد الدفع الناجح، سيتم تفعيل اشتراكك تلقائيًا 🎉",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        else:
            await query.message.reply_text("❌ حدث خطأ في إنشاء رابط الدفع، حاول لاحقًا.")

    elif query.data == 'support':
        await query.message.reply_text("📞 للدعم الفني أو أي استفسار، تواصل مع: @Camel_spx")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if contact.user_id != update.effective_user.id:
        await update.message.reply_text("⚠️ يرجى مشاركة رقم هاتفك الشخصي فقط.")
        return

    context.user_data['phone_number'] = contact.phone_number

    await update.message.reply_text(
        "✅ تم استلام رقم هاتفك بنجاح!\n\n"
        "🔹 الآن أرسل اسم مستخدم TradingView الخاص بك (وليس الإيميل)\n"
        "مثال: AhmedTrader2025",
        reply_markup=ReplyKeyboardRemove()
    )
    # ننتظر النص التالي ليكون اسم TradingView
    context.user_data['waiting_for_tv_username'] = True

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # إذا كان ينتظر اسم TradingView
    if context.user_data.get('waiting_for_tv_username'):
        if len(text) < 3 or text.startswith('@'):
            await update.message.reply_text("❌ اسم المستخدم غير صالح. أعد إرساله بدون @ ويجب أن يكون 3 أحرف على الأقل.")
            return

        context.user_data['tradingview_username'] = text
        context.user_data.pop('waiting_for_tv_username', None)

        await update.message.reply_text(f"✅ تم استلام اسم TradingView بنجاح: `{text}`\n\nالآن اختر باقة الاشتراك:", parse_mode='Markdown')

        packages = get_packages()
        if not packages:
            await update.message.reply_text("😔 لا توجد باقات متاحة حالياً.")
            return

        kb = [
            [InlineKeyboardButton(
                f"{p['name']} - {p['price']} ريال ({p['duration_days']} يوم)",
                callback_data=f"sub_{p['id']}"
            )]
            for p in sorted(packages.values(), key=lambda x: x.get('duration_days', 0))
        ]
        await update.message.reply_text("🔹 اختر مدة الاشتراك المطلوبة:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # إذا أرسل نص عشوائي
    await update.message.reply_text("⚠️ يرجى اتباع الخطوات. ابدأ من جديد بكتابة /start")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Indicator Bot جاهز ويعمل...")
    app.run_polling()

if __name__ == '__main__':
    main()