import sqlite3
import time
from datetime import datetime
import requests
import os
import traceback
import logging
import random
import string

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from zoneinfo import ZoneInfo

OWNER_ID = os.getenv('TELEGRAM_OWNER_ID', '')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
PRIVATE_GROUP_ID = os.getenv('TELEGRAM_PRIVATE_GROUP_ID', '')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'users.db')

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

PACKAGES_API_URL = "http://127.0.0.1:5000/api/packages"
BOT_API_KEY = os.getenv('BOT_API_KEY', '')
REFERRAL_SETTINGS_API = "http://127.0.0.1:5000/api/referral_settings"

def get_packages():
    try:
        headers = {'X-Bot-API-Key': BOT_API_KEY}
        resp = requests.get(PACKAGES_API_URL, headers=headers, timeout=10)
        if resp.status_code == 200:
            packages_list = resp.json()
            return {pkg['id']: pkg for pkg in packages_list if 'id' in pkg}
        else:
            logger.error(f"فشل جلب الباقات: {resp.status_code} - {resp.text}")
            return {}
    except Exception as e:
        logger.exception("خطأ في جلب الباقات: %s", e)
        return {}

def get_referral_settings():
    try:
        resp = requests.get(REFERRAL_SETTINGS_API, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning(f"فشل جلب إعدادات الإحالة: {e}")
    return {'first_time_bonus': 10, 'renewal_bonus': 3}

def generate_referral_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        conn = sqlite3.connect(DB_FILE)
        conn.execute('pragma journal_mode=wal')
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE referral_code = ?", (code,))
        if not c.fetchone():
            conn.close()
            return code
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('pragma journal_mode=wal')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    chat_id INTEGER PRIMARY KEY,
                    name TEXT,
                    username TEXT,
                    phone_number TEXT,
                    paid INTEGER DEFAULT 0,
                    subscription_package TEXT,
                    subscription_end TIMESTAMP,
                    first_seen TIMESTAMP,
                    total_paid_amount REAL DEFAULT 0
                )''')

    additions = [
        ("referral_code", "TEXT UNIQUE"),
        ("referred_by_code", "TEXT"),
        ("referral_count", "INTEGER DEFAULT 0"),
        ("is_frozen", "INTEGER DEFAULT 0"),
        ("frozen_days_remaining", "INTEGER DEFAULT NULL"),
        ("salla_order_id", "TEXT"),
        ("client_username", "TEXT"),
        ("client_password", "TEXT"),
        ("referral_wallet_balance", "REAL DEFAULT 0"),
        ("referral_reward_preference", "TEXT DEFAULT 'days'"),
        ("referral_discount_balance", "REAL DEFAULT 0"),
        ("referral_cashout_balance", "REAL DEFAULT 0"),
        ("referral_days_earned", "INTEGER DEFAULT 0")
    ]

    for column_name, column_def in additions:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_def}")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()
    print("✅ قاعدة البيانات جاهزة.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    context.user_data['chat_id'] = user.id
    context.user_data['full_name'] = user.full_name
    context.user_data['username'] = user.username or ''

    conn = sqlite3.connect(DB_FILE)
    conn.execute('pragma journal_mode=wal')
    c = conn.cursor()
    c.execute("SELECT paid FROM users WHERE chat_id = ?", (user.id,))
    row = c.fetchone()
    conn.close()

    is_existing_paid_user = row and row[0] == 1

    if is_existing_paid_user:
        inline_keyboard = [
            [InlineKeyboardButton("⭐ تجديد الاشتراك", callback_data='register')],
            [InlineKeyboardButton("📞 التواصل مع الدعم الفني", callback_data='support')]
        ]
        await update.message.reply_text("👋 أهلاً بعودتك! اختر أحد الخيارات:", reply_markup=InlineKeyboardMarkup(inline_keyboard))
    else:
        keyboard = [
            [InlineKeyboardButton("نعم، لدي كود دعوة", callback_data='ref_yes')],
            [InlineKeyboardButton("لا، أبدأ اشتراك جديد", callback_data='ref_no')]
        ]
        await update.message.reply_text(
            "🤖 مرحباً بك في بوت الاشتراكات!\n\nهل تمت دعوتك من قبل أحد الأعضاء عبر كود دعوة؟",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data.startswith('ref_reward_'):
        reward = query.data.replace('ref_reward_', '', 1)
        labels = {
            'cashout': 'كاش أوت عند الإحالة',
            'discount': 'خصم عند التجديد',
            'days': 'أيام إضافية'
        }
        if reward not in labels:
            await query.message.reply_text("⚠️ اختيار غير معروف.")
            return

        conn = sqlite3.connect(DB_FILE)
        conn.execute('pragma journal_mode=wal')
        c = conn.cursor()
        c.execute("""
            UPDATE users
            SET referral_reward_preference = ?
            WHERE chat_id = ?
        """, (reward, user.id))
        conn.commit()
        conn.close()

        await query.message.reply_text(
            f"✅ تم حفظ اختيارك لمكافآت الإحالة: {labels[reward]}\n"
            "يمكنك مشاركة كودك الآن، وسيتم تطبيق هذا الاختيار تلقائياً عند كل إحالة ناجحة."
        )

    elif query.data == 'ref_yes':
        context.user_data['waiting_for_ref_code'] = True
        await query.message.reply_text("🔑 من فضلك أدخل كود الدعوة (مثال: AB12XY):")

    elif query.data in ('ref_no', 'register'):
        if query.data == 'ref_no':
            context.user_data['referred_by_code'] = None
        keyboard = [[KeyboardButton("📱 شارك رقم هاتفك للمتابعة", request_contact=True)]]
        await query.message.reply_text(
            "قبل اختيار الباقة، يرجى مشاركة رقم هاتفك للتعرف عليك عند الدفع.",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )

    elif query.data.startswith('sub_'):
        package_id = query.data.split('_', 1)[1]
        packages = get_packages()
        
        if package_id not in packages:
            await query.message.reply_text("⚠️ عفواً، هذه الباقة غير متوفرة حالياً.")
            return

        subscription = packages[package_id]
        phone_number = context.user_data.get('phone_number')

        if not phone_number:
            await query.message.reply_text("⚠️ يرجى مشاركة رقم هاتفك أولاً.")
            return

        # 1. حفظ بيانات العميل في قاعدة البيانات مبكراً ليتعرف عليه سلة لاحقاً
        conn = sqlite3.connect(DB_FILE)
        conn.execute('pragma journal_mode=wal')
        c = conn.cursor()
        c.execute("""
            INSERT INTO users (chat_id, name, username, phone_number, referred_by_code, first_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                phone_number=excluded.phone_number,
                name=excluded.name,
                username=excluded.username,
                referred_by_code=COALESCE(users.referred_by_code, excluded.referred_by_code)
        """, (user.id, user.full_name, user.username, phone_number, context.user_data.get('referred_by_code'), datetime.now().isoformat()))
        conn.commit()
        conn.close()

        # 2. استخراج رابط الباقة في سلة (من إعدادات الداش بورد)
        # ملاحظة: في لوحة التحكم عند إضافة باقة استخدم حقل 'zid_product_url' أو 'product_url' لوضع رابط سلة
        product_url = subscription.get('zid_product_url') or subscription.get('product_url') or "تواصل مع الدعم للحصول على الرابط"

        msg = (
            f"📦 **{subscription['name']}**\n"
            f"💰 السعر: {subscription['price']} ريال\n"
            f"⏳ المدة: {subscription['duration_days']} يوم\n\n"
            f"🛒 **لإتمام الاشتراك، يرجى الدفع عبر متجرنا في سلة من خلال الرابط التالي:**\n"
            f"🔗 {product_url}\n\n"
            f"⚠️ **ملاحظة هامة جداً:**\n"
            f"يرجى التأكد من إدخال رقم جوالك `{(phone_number)}` أثناء عملية الدفع في سلة لكي يتعرف عليك النظام.\n\n"
            f"✅ **بمجرد الدفع، سيصلك رابط القناة الخاصة هنا تلقائياً خلال ثوانٍ معدودة.**"
        )
        await query.message.reply_text(msg, disable_web_page_preview=True)

    elif query.data == 'support':
        support_keyboard = [
            [InlineKeyboardButton("💬 التواصل مع بوت المساعدة", callback_data='support_contact_bot')]
        ]
        reply_markup = InlineKeyboardMarkup(support_keyboard)
        await query.message.edit_text("اختر أحد خيارات الدعم الفني:", reply_markup=reply_markup)

    elif query.data == 'support_contact_bot':
        support_text = (
            "🗯️ الرجاء إرسال صورة من المحادثة مع البوت ورقم جوالك مع توضيح المشكلة "
            "إلى الدعم الفني من خلال التواصل مع 👈 @Camel_spx"
        )
        await query.message.reply_text(support_text)

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if contact.user_id != update.effective_user.id:
        await update.message.reply_text("⚠️ يرجى مشاركة رقم هاتفك الخاص فقط.")
        return

    # تنظيف رقم الهاتف وتوحيده
    phone = contact.phone_number.replace('+', '').replace(' ', '')
    context.user_data['phone_number'] = phone

    await update.message.reply_text("✅ تم استلام رقم الهاتف بنجاح!", reply_markup=ReplyKeyboardRemove())

    packages = get_packages()
    if not packages:
        await update.message.reply_text("😔 عذراً، لا توجد باقات متاحة حالياً.")
        return

    sorted_packages = sorted(packages.values(), key=lambda p: int(p.get('duration_days', 0)))
    packages_keyboard = [
        [InlineKeyboardButton(
            f"{pkg['name']} - {pkg['price']} ريال ({pkg['duration_days']} يوم)",
            callback_data=f"sub_{pkg['id']}"
        )]
        for pkg in sorted_packages
    ]

    await update.message.reply_text("🔹 الآن اختر باقة الاشتراك:", reply_markup=InlineKeyboardMarkup(packages_keyboard))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_ref_code'):
        code = update.message.text.strip().upper()
        if len(code) != 6 or not code.isalnum():
            await update.message.reply_text("❌ الكود غير صالح. يجب أن يكون 6 أحرف/أرقام.")
            return

        conn = sqlite3.connect(DB_FILE)
        conn.execute('pragma journal_mode=wal')
        c = conn.cursor()
        c.execute("SELECT chat_id FROM users WHERE referral_code = ?", (code,))
        row = c.fetchone()
        conn.close()

        if row:
            context.user_data['referred_by_code'] = code
            await update.message.reply_text(f"✅ تم قبول كود الدعوة: `{code}`\nالآن شارك رقم هاتفك...", parse_mode='Markdown')
            keyboard = [[KeyboardButton("📱 شارك رقم هاتفك للمتابعة", request_contact=True)]]
            await update.message.reply_text("...", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))
        else:
            await update.message.reply_text("❌ الكود غير صحيح أو غير موجود. حاول مرة أخرى أو اضغط /start واختر 'لا'.")

        context.user_data.pop('waiting_for_ref_code', None)
        return

async def check_and_notify_expiring_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    ksa_tz = ZoneInfo("Asia/Riyadh")
    now_ksa = datetime.now(ksa_tz)

    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute('pragma journal_mode=wal')
        c = conn.cursor()
        c.execute("""
            SELECT chat_id, subscription_end, name 
            FROM users 
            WHERE paid = 1 AND (is_frozen IS NULL OR is_frozen = 0)
        """)
        users = c.fetchall()
        conn.close()

        for user in users:
            if not user[1]:
                continue
            try:
                end_dt = datetime.fromisoformat(user[1])
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=ksa_tz)
                
                time_left = end_dt - now_ksa
                hours_left = time_left.total_seconds() / 3600

                if 0 < hours_left <= 10:
                    chat_id = user[0]
                    user_name = user[2] or "عزيزي"
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"⚠️ تحذير مهم يا {user_name}!\n\n"
                             f"اشتراكك سينتهي بعد حوالي "
                             f"**{int(hours_left)} ساعة و {int((hours_left % 1) * 60)} دقيقة** ⏳\n\n"
                             f"جدد اشتراكك الآن عبر المتجر لتجنب الإزالة التلقائية!\n"
                             f"اضغط /start للتجديد 🚀",
                        parse_mode='Markdown'
                    )
            except Exception:
                continue

    except Exception as e:
        print("خطأ في فحص الإشعارات القريبة من الانتهاء:", e)
async def kick_expired_users(context: ContextTypes.DEFAULT_TYPE):
    """دالة تفحص الاشتراكات المنتهية وتطرد أصحابها من القناة"""
    from zoneinfo import ZoneInfo
    ksa_tz = ZoneInfo("Asia/Riyadh")
    now_ksa = datetime.now(ksa_tz)

    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute('pragma journal_mode=wal')
        c = conn.cursor()
        
        # جلب المستخدمين الذين انتهى اشتراكهم (الوقت الحالي أكبر من وقت الانتهاء)
        c.execute("""
            SELECT chat_id, name 
            FROM users 
            WHERE paid = 1 AND subscription_end IS NOT NULL AND (is_frozen IS NULL OR is_frozen = 0)
        """)
        users = c.fetchall()

        for user in users:
            chat_id = user[0]
            
            # التأكد مجدداً من الوقت
            c.execute("SELECT subscription_end FROM users WHERE chat_id = ?", (chat_id,))
            end_date_str = c.fetchone()[0]
            
            if end_date_str:
                end_dt = datetime.fromisoformat(end_date_str)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=ksa_tz)

                # إذا انتهى الوقت فعلياً
                if now_ksa >= end_dt:
                    try:
                        # 1. طرد العميل من القناة الخاصة (ban ثم unban لكي يستطيع العودة لاحقاً إذا جدد)
                        await context.bot.ban_chat_member(chat_id=PRIVATE_GROUP_ID, user_id=chat_id)
                        await context.bot.unban_chat_member(chat_id=PRIVATE_GROUP_ID, user_id=chat_id)
                        
                        # 2. تحديث حالة العميل في قاعدة البيانات إلى "غير مدفوع"
                        c.execute("UPDATE users SET paid = 0 WHERE chat_id = ?", (chat_id,))
                        
                        # 3. إرسال رسالة له
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="انتهى اشتراكك في القناة الخاصة 😔.\nلقد تم إخراجك تلقائياً.\n\nنتمنى رؤيتك مجدداً! لتجديد الاشتراك اضغط /start",
                        )
                        print(f"تم طرد العميل {chat_id} لانتهاء اشتراكه.")
                    except Exception as e:
                        print(f"حدث خطأ أثناء طرد العميل {chat_id}: {e}")

        conn.commit()
        conn.close()

    except Exception as e:
        print("خطأ في دالة الطرد التلقائي:", e)
def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    job_queue = application.job_queue

    job_queue.run_repeating(
        check_and_notify_expiring_subscriptions,
        interval=3600,
        first=30
    )
    # فحص وطرد المنتهية اشتراكاتهم كل 30 دقيقة
    

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 Salla Payment Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
