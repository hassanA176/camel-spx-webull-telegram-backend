# app.py
import threading
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, send_from_directory
import os, traceback, requests, base64, io, json, sqlite3, uuid, shutil
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps, ImageFilter, ImageDraw, ImageFont
from datetime import datetime, timedelta
import time
import requests
import traceback
from zoneinfo import ZoneInfo

import os
import base64
# أضف هذه السطرين مع باقي استيرادات flask
from flask import session, flash
app = Flask(__name__)
last_daily_date = None
last_weekly_date = None           # تاريخ آخر جمعة تم إرسال تقرير أسبوعي لها
last_monthly_period = None        # (السنة, الشهر) لآخر شهر تم إرساله

crt = os.getenv("TLS_CERT_PATH", "")
key = os.getenv("TLS_KEY_PATH", "")

if not os.path.exists(crt) or not os.path.exists(key):
    print("❌ الشهادة غير موجودة في المسار المحدد.")
else:
    print("✅ الشهادة تم العثور عليها.")


app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-me-in-production')

# --- إعدادات أساسية ومسارات موحدة ---
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
PUBLIC_GROUP_ID = os.getenv('TELEGRAM_PUBLIC_GROUP_ID', '')
PRIVATE_GROUP_ID = os.getenv('TELEGRAM_PRIVATE_GROUP_ID', '')
PRIVATE_CHANNEL_ID = os.getenv('TELEGRAM_PRIVATE_CHANNEL_ID', '')
    "PRIVATE_CHANNEL_ID",
    "-1003703182738"
)
PAYMENT_BOT_TOKEN = os.getenv('PAYMENT_BOT_TOKEN', '')
    "PAYMENT_BOT_TOKEN",
    "YOUR_TELEGRAM_BOT_TOKEN"
)
PUBLIC_SITE_URL = os.getenv("PUBLIC_SITE_URL", "https://camelspx.com").rstrip("/")
BOT_API_KEY = os.getenv('BOT_API_KEY', '')
ZID_WEBHOOK_USERNAME = os.getenv('ZID_WEBHOOK_USERNAME', '')
ZID_WEBHOOK_PASSWORD = os.getenv('ZID_WEBHOOK_PASSWORD', '')
MOYASAR_API_KEY = os.getenv('MOYASAR_API_KEY', '')
TREAM_BASE_URL = "https://stream-app-service.streampay.sa"
STREAM_API_KEY = os.getenv('STREAM_API_KEY', '')
STREAM_API_SECRET = os.getenv('STREAM_API_SECRET', '')
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', '')
GROUP_CHAT_ID = os.getenv('TELEGRAM_GROUP_CHAT_ID', '')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE_PATH = os.path.join(BASE_DIR, 'trades.csv')
JSON_FILE_PATH = os.path.join(BASE_DIR, 'trades.json') # <-- أضف هذا السطر
INDEX_TRADE_FILES = {
    "SPX": {"csv": "trades.csv", "json": "trades.json"},
    "SPY": {"csv": "spy_trades.csv", "json": "spy_trades.json"},
    "QQQ": {"csv": "qqq_trades.csv", "json": "qqq_trades.json"},
    "NDX": {"csv": "ndx_trades.csv", "json": "ndx_trades.json"},
}
COMPANY_TRADE_FILES = {"csv": "company_trades.csv", "json": "company_trades.json"}
COMPANY_SYMBOLS = ["NVDA", "MSTR", "TSLA", "AVGO", "META", "AAPL", "SMCI", "GOOG", "MSFT"]
TRADE_TIMEFRAMES = {"daily": "", "weekly": "weekly_", "monthly": "monthly_"}
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
SETTINGS_FILE = os.path.join(BASE_DIR, 'settings.json')
DATABASE_PATH = os.path.join(BASE_DIR, 'users.db') # مسار قاعدة البيانات

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
SCHEDULED_IMAGES_FOLDER = os.path.join(BASE_DIR, 'static', 'scheduled')
os.makedirs(SCHEDULED_IMAGES_FOLDER, exist_ok=True)
TRADE_TEMPLATE_FOLDER = os.path.join(BASE_DIR, 'static', 'trade_templates')
TRADE_TEMPLATE_ARCHIVE_FOLDER = os.path.join(TRADE_TEMPLATE_FOLDER, 'archive')
TRADE_TEMPLATE_PENDING_FOLDER = os.path.join(TRADE_TEMPLATE_FOLDER, 'pending')
for folder in (TRADE_TEMPLATE_FOLDER, TRADE_TEMPLATE_ARCHIVE_FOLDER, TRADE_TEMPLATE_PENDING_FOLDER):
    os.makedirs(folder, exist_ok=True)

# ---------------------------------
import json
import math
from datetime import date, datetime
from decimal import Decimal

try:
    import numpy as np
except Exception:
    np = None

try:
    import pandas as pd
except Exception:
    pd = None

def make_json_safe(obj):
    if obj is None:
        return None

    if isinstance(obj, dict):
        return {str(k): make_json_safe(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [make_json_safe(v) for v in obj]

    if pd is not None:
        try:
            if pd.isna(obj):
                return None
        except Exception:
            pass

    if np is not None:
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            value = float(obj)
            if math.isnan(value) or math.isinf(value):
                return None
            return value

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    if isinstance(obj, Decimal):
        return float(obj)

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    return obj


def _rel_path(path):
    if not path:
        return ''
    try:
        return os.path.relpath(path, BASE_DIR).replace('\\', '/')
    except Exception:
        return str(path).replace('\\', '/')


def _abs_path(path):
    if not path:
        return ''
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path.replace('/', os.sep))


def _first_existing_relative(*paths):
    for path in paths:
        full = _abs_path(path)
        if full and os.path.exists(full):
            return _rel_path(full)
    return _rel_path(_abs_path(paths[0])) if paths else ''


def _image_size(path):
    try:
        with Image.open(_abs_path(path)) as img:
            return [int(img.width), int(img.height)]
    except Exception:
        return [1536, 1024]


def _default_trade_image_templates():
    indicator_normal = _first_existing_relative('camel_spx_normal.png', 'camel_spx_normal.jpeg')
    indicator_right = _first_existing_relative('camel_spx_with_right.png', 'camel_spx_with_right_.png', 'camel_spx_with_right.jpeg')
    return {
        'indicator_normal': {'label': 'صورة المؤشرات بدون اليمين', 'active_path': indicator_normal, 'expected_size': _image_size(indicator_normal), 'archive': []},
        'indicator_right': {'label': 'صورة المؤشرات مع اليمين', 'active_path': indicator_right, 'expected_size': _image_size(indicator_right), 'archive': []},
        'company_normal': {'label': 'صورة الشركات بدون اليمين', 'active_path': indicator_normal, 'expected_size': _image_size(indicator_normal), 'archive': []},
        'company_right': {'label': 'صورة الشركات مع اليمين', 'active_path': indicator_right, 'expected_size': _image_size(indicator_right), 'archive': []},
    }


def _merge_trade_image_templates(settings):
    defaults = _default_trade_image_templates()
    saved = settings.get('trade_image_templates') or {}
    merged = {}
    for slot, default in defaults.items():
        item = dict(default)
        item.update(saved.get(slot) or {})
        item.setdefault('archive', [])
        item.setdefault('expected_size', default.get('expected_size') or [1536, 1024])
        merged[slot] = item
    return merged


def _static_url(path):
    rel = _rel_path(_abs_path(path))
    return '/' + rel if rel.startswith('static/') else ''


def _trade_template_payload(settings=None):
    settings = settings or get_settings()
    templates = _merge_trade_image_templates(settings)
    payload = {}
    for slot, item in templates.items():
        active_path = item.get('active_path') or ''
        pending_path = item.get('pending_path') or ''
        active_size = _image_size(active_path)
        payload[slot] = {
            **item,
            'active_url': _static_url(active_path) or ('/' + active_path.replace('\\', '/') if active_path else ''),
            'pending_url': _static_url(pending_path),
            'active_size': active_size,
            'preview_url': f'/api/trade_image_templates/preview/{slot}?v={int(time.time())}',
        }
    return payload


def _save_trade_templates(templates):
    save_settings({'trade_image_templates': templates})


def _trade_template_slot(slot):
    templates = _merge_trade_image_templates(get_settings())
    if slot not in templates:
        return None, templates
    return templates[slot], templates


def _draw_trade_template_preview(path, use_right_panel=False):
    try:
        img = Image.open(_abs_path(path)).convert('RGBA')
    except Exception:
        img = Image.new('RGBA', (1536, 1024), (8, 12, 24, 255))

    draw = ImageDraw.Draw(img)
    try:
        font_big = ImageFont.truetype('arialbd.ttf', 120)
        font_mid = ImageFont.truetype('arialbd.ttf', 42)
        font_small = ImageFont.truetype('arialbd.ttf', 34)
    except Exception:
        font_big = font_mid = font_small = ImageFont.load_default()

    header = 'SPX 7420 19 JUL 26 Call'
    draw.text((110, 70), header, font=font_mid, fill=(0, 0, 0))
    draw.text((95, 145), '3.50', font=font_big, fill=(12, 175, 130))
    metrics = ['2.80', '3.15', '1,240', '7423.50']
    y = 330
    for value in metrics:
        draw.text((440, y), value, font=font_small, fill=(87, 93, 108))
        y += 96

    if use_right_panel:
        x_right = img.width - 310
        draw.text((x_right, 425), '2.80', font=font_small, fill=(69, 83, 94))
        draw.text((x_right, 710), 'USD 70', font=font_mid, fill=(255, 147, 0))
        draw.text((x_right, 785), 'SAR 263', font=font_mid, fill=(0, 0, 0))
        draw.text((x_right, 220), '+25.0%', font=font_mid, fill=(12, 175, 130))

    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    return bio
# --- دوال إدارة الإعدادات ---
# --- إدارإعدادات ---


def get_settings():
    defaults = {
            'opacity': 10,
            'schedule_time': '23:59',
            'allowed_user_ids': [],
            'monitor_increase': 0.10,
            'closing_messages': {
                'list': ["اغلاق موفق للجميع"],
                'selected': "اغلاق موفق للجميع"
            },
            'scheduled_messages': [],
            'referral_settings': {
                'first_time_bonus': 10,
                'renewal_bonus': 3,
                'reward_type': 'days',
                'first_time_amount': 0,
                'renewal_amount': 0,
                'first_time_discount': 0,
                'renewal_discount': 0,
                'cashout_minimum': 150,
                'package_rewards': {}
            },
            'trade_image_templates': _default_trade_image_templates()
        }
    if not os.path.exists(SETTINGS_FILE):
        return defaults

    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content:
                return defaults
            settings = json.loads(content)
            defaults.update(settings)
            defaults['trade_image_templates'] = _merge_trade_image_templates(defaults)
            return defaults
    except (json.JSONDecodeError, IOError):
        return defaults

# ====================== Helpers for Zid Payment Webhook ======================

def ensure_column(cursor, table_name: str, column_name: str, column_def: str):
    try:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
        print(f"✅ تم إضافة العمود {column_name}")
    except sqlite3.OperationalError:
        pass


def ensure_zid_columns():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    additions = [
        ("referral_code", "TEXT UNIQUE"),
        ("referred_by_code", "TEXT"),
        ("referral_count", "INTEGER DEFAULT 0"),
        ("is_frozen", "INTEGER DEFAULT 0"),
        ("frozen_days_remaining", "INTEGER DEFAULT NULL"),
        ("client_username", "TEXT"),
        ("client_password", "TEXT"),
        ("referral_wallet_balance", "REAL DEFAULT 0"),
        ("referral_reward_preference", "TEXT DEFAULT 'days'"),
        ("referral_discount_balance", "REAL DEFAULT 0"),
        ("referral_cashout_balance", "REAL DEFAULT 0"),
        ("referral_days_earned", "INTEGER DEFAULT 0"),

        # أعمدة انتظار دفع زد
        ("pending_package_id", "TEXT"),
        ("pending_payment_provider", "TEXT"),
        ("pending_created_at", "TEXT"),
        ("pending_zid_product_url", "TEXT"),
        ("pending_full_name", "TEXT"),
        ("pending_username", "TEXT"),
        ("pending_phone_number", "TEXT"),
        ("pending_referred_by_code", "TEXT"),

        # أعمدة طلبات زد
        ("zid_order_id", "TEXT"),
        ("zid_payment_status", "TEXT"),
        ("zid_last_event_at", "TEXT"),
    ]

    for col_name, col_def in additions:
        ensure_column(c, "users", col_name, col_def)

    conn.commit()
    conn.close()


def ensure_client_trade_tables():
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS client_trades (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                date TEXT,
                symbol TEXT,
                contract TEXT,
                type TEXT,
                strike TEXT,
                entry REAL DEFAULT 0,
                exit REAL DEFAULT 0,
                quantity INTEGER DEFAULT 1,
                pnl REAL DEFAULT 0,
                status TEXT DEFAULT 'open',
                note TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""

    phone = str(phone).strip()
    phone = (
        phone.replace("+", "")
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    if phone.startswith("00966"):
        phone = phone[2:]

    if phone.startswith("05") and len(phone) == 10:
        phone = "966" + phone[1:]

    elif phone.startswith("5") and len(phone) == 9:
        phone = "966" + phone

    return phone


def verify_zid_basic_auth():
    """
    زد يمكنه إرسال Basic Auth إذا وضعت username/password عند إنشاء الـ webhook.
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Basic "):
        return False

    try:
        encoded = auth_header.split(" ", 1)[1].strip()
        decoded = base64.b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":", 1)

        return (
            username == ZID_WEBHOOK_USERNAME
            and password == ZID_WEBHOOK_PASSWORD
        )

    except Exception:
        return False


def get_nested(data, paths, default=None):
    """
    يجرب أكثر من مسار لأن Payload زد قد يختلف حسب نوع الحدث.
    """
    for path in paths:
        cur = data
        ok = True

        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur.get(part)
            else:
                ok = False
                break

        if ok and cur not in (None, ""):
            return cur

    return default


def extract_zid_order_id(payload: dict) -> str:
    return str(get_nested(payload, [
        "id",
        "order.id",
        "order_id",
        "data.id",
        "data.order.id",
        "data.order_id",
        "message.id",
        "message.order.id",
        "resource.id",
    ], "") or "")


def extract_zid_status(payload: dict) -> str:
    status = get_nested(payload, [
        "status",
        "order.status",
        "order.payment_status",
        "payment_status",
        "data.status",
        "data.order.status",
        "data.order.payment_status",
        "message.status",
        "message.order.status",
        "message.order.payment_status",
    ], "")

    return str(status or "").lower().strip()


def is_zid_paid_event(payload: dict) -> bool:
    """
    نحاول نكون مرنين لأن أحداث زد قد تأتي بصيغ مختلفة.
    """
    event_name = str(get_nested(payload, [
        "event",
        "event_name",
        "type",
        "name",
        "message.event",
    ], "") or "").lower()

    status = extract_zid_status(payload)

    paid_words = [
        "paid",
        "payment.paid",
        "order.paid",
        "completed",
        "complete",
        "success",
        "succeeded",
        "captured",
    ]

    if any(word in event_name for word in paid_words):
        return True

    if any(word == status or word in status for word in paid_words):
        return True

    # بعض الطلبات في زد قد يكون فيها is_paid
    is_paid = get_nested(payload, [
        "is_paid",
        "order.is_paid",
        "data.is_paid",
        "data.order.is_paid",
        "message.order.is_paid",
    ], None)

    if is_paid is True or str(is_paid).lower() in ("true", "1", "yes"):
        return True

    return False


def extract_zid_customer_phone(payload: dict) -> str:
    phone = get_nested(payload, [
        "customer.mobile",
        "customer.phone",
        "customer.phone_number",
        "customer.mobile_number",

        "order.customer.mobile",
        "order.customer.phone",
        "order.customer.phone_number",
        "order.customer.mobile_number",

        "data.customer.mobile",
        "data.customer.phone",
        "data.customer.phone_number",
        "data.customer.mobile_number",

        "data.order.customer.mobile",
        "data.order.customer.phone",
        "data.order.customer.phone_number",
        "data.order.customer.mobile_number",

        "message.customer.mobile",
        "message.customer.phone",
        "message.order.customer.mobile",
        "message.order.customer.phone",

        "shipping_address.phone",
        "data.shipping_address.phone",
        "order.shipping_address.phone",
        "data.order.shipping_address.phone",
    ], "")

    return normalize_phone(phone)


def extract_zid_customer_name(payload: dict) -> str:
    return str(get_nested(payload, [
        "customer.name",
        "order.customer.name",
        "data.customer.name",
        "data.order.customer.name",
        "message.customer.name",
        "message.order.customer.name",
        "billing_address.name",
        "shipping_address.name",
    ], "") or "")


def extract_zid_total_amount(payload: dict) -> float:
    amount = get_nested(payload, [
        "total",
        "amount",
        "order.total",
        "order.amount",
        "order.order_total",
        "data.total",
        "data.amount",
        "data.order.total",
        "data.order.amount",
        "message.order.total",
        "message.order.amount",
    ], 0)

    try:
        if isinstance(amount, dict):
            amount = amount.get("amount") or amount.get("value") or 0

        return float(str(amount).replace(",", "").strip() or 0)

    except Exception:
        return 0.0


def generate_unique_referral_code(cursor) -> str:
    import random
    import string

    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        cursor.execute("SELECT 1 FROM users WHERE referral_code = ?", (code,))
        if not cursor.fetchone():
            return code

def generate_client_credentials(cursor, chat_id):
    import random
    import string

    base_username = f"client_{chat_id}"
    username = base_username
    suffix = 1

    while True:
        cursor.execute(
            "SELECT 1 FROM users WHERE client_username = ? AND chat_id != ?",
            (username, chat_id)
        )
        if not cursor.fetchone():
            break
        suffix += 1
        username = f"{base_username}_{suffix}"

    password = "".join(random.choices(string.ascii_letters + string.digits, k=10))
    return username, password


def create_private_channel_invite_link() -> str | None:
    try:
        invite_url = f"https://api.telegram.org/bot{PAYMENT_BOT_TOKEN}/createChatInviteLink"

        payload = {
            "chat_id": PRIVATE_CHANNEL_ID,
            "expire_date": int(time.time()) + 60,
            "member_limit": 1
        }

        resp = requests.post(invite_url, json=payload, timeout=15)
        data = resp.json()

        if data.get("ok"):
            return data["result"]["invite_link"]

        print("❌ فشل إنشاء رابط الدعوة:", data)
        return None

    except Exception:
        print(traceback.format_exc())
        return None


def send_telegram_message(chat_id: int, text: str):
    try:
        url = f"https://api.telegram.org/bot{PAYMENT_BOT_TOKEN}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        resp = requests.post(url, json=payload, timeout=15)
        print("Telegram sendMessage:", resp.status_code, resp.text[:300])

        return resp.status_code == 200

    except Exception:
        print(traceback.format_exc())
        return False


def remove_user_from_private_channel(chat_id: int | str) -> tuple[bool, str]:
    try:
        user_id = int(chat_id)
    except (TypeError, ValueError):
        return False, "Invalid chat_id"

    try:
        ban_url = f"https://api.telegram.org/bot{PAYMENT_BOT_TOKEN}/banChatMember"
        unban_url = f"https://api.telegram.org/bot{PAYMENT_BOT_TOKEN}/unbanChatMember"
        payload = {"chat_id": PRIVATE_CHANNEL_ID, "user_id": user_id}

        ban_resp = requests.post(ban_url, json=payload, timeout=15).json()
        if not ban_resp.get("ok"):
            return False, ban_resp.get("description", "Telegram ban failed")

        unban_resp = requests.post(
            unban_url,
            json={**payload, "only_if_banned": True},
            timeout=15
        ).json()
        if not unban_resp.get("ok"):
            return False, unban_resp.get("description", "Telegram unban failed")

        return True, "removed"
    except Exception as exc:
        print(traceback.format_exc())
        return False, str(exc)


def find_pending_user_by_phone(cursor, phone: str):
    """
    نبحث عن آخر مستخدم دفعه معلق عبر زد بنفس رقم الجوال.
    """
    normalized = normalize_phone(phone)

    if not normalized:
        return None

    cursor.execute("""
        SELECT
            chat_id,
            name,
            username,
            phone_number,
            paid,
            subscription_package,
            subscription_end,
            referral_code,
            referred_by_code,
            referral_count,
            pending_package_id,
            pending_referred_by_code
        FROM users
        WHERE
            pending_payment_provider = 'zid'
            AND (
                phone_number = ?
                OR pending_phone_number = ?
            )
        ORDER BY pending_created_at DESC
        LIMIT 1
    """, (normalized, normalized))

    return cursor.fetchone()


def get_package_by_id(package_id: str):
    settings = get_settings()
    packages = settings.get("packages", [])

    for package in packages:
        if str(package.get("id")) == str(package_id):
            return package

    return None
def save_settings(settings_data: dict):
    current_settings = get_settings()
    current_settings.update(settings_data)
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_settings, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"خطأ في حفظ الإعدادات: {e}")
# ---------------------------------

def _get_stream_headers() -> dict:
    if not STREAM_API_KEY or not STREAM_API_SECRET:
        raise RuntimeError("STREAM_API_KEY or STREAM_API_SECRET not set correctly")
    token = base64.b64encode(f"{STREAM_API_KEY}:{STREAM_API_SECRET}".encode()).decode()
    return {
        "x-api-key": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

# --- دوال تحميل ومعالجة بيانات الصفقات ---
def load_df(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt"): return pd.read_csv(path, encoding="utf-8-sig", sep=None, engine="python")
    elif ext in (".xlsx", ".xls"): return pd.read_excel(path, engine="openpyxl")
    else: raise ValueError(f"امتداد غير مدعوم: {ext}")
# app.py
# app.py
def format_arabic_time(dt):
    if pd.isna(dt):
        return '---'
    suffix = 'صباحاً' if dt.hour < 12 else 'مساءً'
    # حذف الصفر في البداية + دقائق فقط
    time_str = dt.strftime('%I:%M').lstrip('0')
    return f"{time_str} {suffix}"

from datetime import datetime
import time

def get_data_from_excel(start_date=None, end_date=None):
    # 1. قراءة البيانات الأساسية من ملف CSV
    df_csv = load_df(DATA_FILE_PATH)
    df_csv.columns = df_csv.columns.str.strip()

    # 2. قراءة بيانات الوقت التفصيلية من ملف JSON
    try:
        df_json = pd.read_json(JSON_FILE_PATH, orient='records')
        df_json.columns = df_json.columns.str.strip()
        df_json_times = df_json[['Trade ID', 'created_at', 'closed_at']].copy()
        df = pd.merge(df_csv, df_json_times, on='Trade ID', how='left')
    except (FileNotFoundError, ValueError) as e:
        print(f"!!! تحذير: لم يتم العثور على ملف trades.json أو حدث خطأ في قراءته: {e}")
        df = df_csv
        df['created_at'] = pd.NaT
        df['closed_at'] = pd.NaT

    # 4. التعامل مع التاريخ-10
    df['date_obj'] = pd.to_datetime(df['created_at'], errors='coerce')

    mask_no_created = df['date_obj'].isna()
    if 'Date' in df.columns:
        df.loc[mask_no_created, 'date_obj'] = pd.to_datetime(
            df.loc[mask_no_created, 'Date'], errors='coerce'
        )

    still_missing = df['date_obj'].isna()
    df.loc[still_missing, 'date_obj'] = pd.to_datetime('today').normalize()

    # 5. التاريخ ووقت الدخول (بدون ثواني، صباحاً/مساءً)
    df['date'] = df['date_obj'].dt.strftime('%Y-%m-%d')
    df['entry_time'] = df['date_obj'].apply(format_arabic_time)  # فقط ساعات + دقائق

    # حساب وقت الإغلاق ومدة الهدف
    df['closed_at_obj'] = pd.to_datetime(df['closed_at'], errors='coerce')
    duration = df['closed_at_obj'] - df['date_obj']

    def format_timedelta(td):
        if pd.isna(td):
            return '---'
        total_seconds = int(td.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        # بدون ثواني فقط HH:MM
        return f'{hours:02}:{minutes:02}'

    df['duration'] = duration.apply(format_timedelta)

    # 6. الأعمدة الأساسية
    if 'Number' in df.columns:
        df['number'] = df['Number']
    else:
        df['number'] = pd.RangeIndex(start=1, stop=len(df) + 1)

    if 'Type Contract' in df.columns:
        df['type'] = df['Type Contract'].astype(str).str.upper().str.strip()
    elif 'Type' in df.columns:
        df['type'] = df['Type'].astype(str).str.upper().str.strip()
    else:
        df['type'] = pd.NA

    if 'SPX Strike' in df.columns:
        df['strike'] = df['SPX Strike']
    elif 'Strike' in df.columns:
        df['strike'] = df['Strike']
    else:
        df['strike'] = pd.NA

    if 'Open' in df.columns:
        df['open'] = df['Open']
    elif 'Entry Price' in df.columns:
        df['open'] = df['Entry Price']
    else:
        df['open'] = pd.NA

    if 'السعر المحقق' in df.columns:
        df['close_price'] = df['السعر المحقق']
    elif 'High' in df.columns:
        df['close_price'] = df['High']
    else:
        df['close_price'] = pd.NA

    if 'الربح بالعقد' in df.columns:
        df['profit'] = df['الربح بالعقد']
    elif 'Profit' in df.columns:
        df['profit'] = df['Profit']
    else:
        df['profit'] = 0

    if 'الخسارة بالعقد' in df.columns:
        df['loss'] = df['الخسارة بالعقد']
    elif 'Loss' in df.columns:
        df['loss'] = df['Loss']
    else:
        df['loss'] = 0

    # تحويل قيم الربح والخسارة إلى أرقام
    for col in ['profit', 'loss']:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(r'[\$,]', '', regex=True).str.strip(),
            errors='coerce'
        ).fillna(0)

    # تحويل سعر الدخول إلى رقم لاستخدامه في نسبة الربح
    df['open_numeric'] = pd.to_numeric(
        df['open'].astype(str).str.replace(r'[\$,]', '', regex=True).str.strip(),
        errors='coerce'
    ).fillna(0)

    # تحويل السعر المحقق إلى رقم لاستخدامه في نسبة الربح
    df['close_numeric'] = pd.to_numeric(
        df['close_price'].astype(str).str.replace(r'[\$,]', '', regex=True).str.strip(),
        errors='coerce'
    ).fillna(0)

    # فلترة حسب التاريخ
    if start_date:
        start_dt = pd.to_datetime(start_date)
        df = df[df['date_obj'] >= start_dt]
    if end_date:
        end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        df = df[df['date_obj'] <= end_dt]

    # PnL
    df['pnl'] = df['profit'] - df['loss']

    # نسبة الربح:
    # (السعر المحقق - سعر الطرح) / سعر الطرح * 100
    def calc_profit_pct(row):
        if row['open_numeric'] > 0 and row['close_numeric'] > 0:
            return ((row['close_numeric'] - row['open_numeric']) / row['open_numeric']) * 100.0
        return 0.0

    df['profit_pct'] = df.apply(calc_profit_pct, axis=1)

    # الأعمدة المعروضة في الجدول
    display_cols = [
        'number', 'date', 'entry_time',
        'duration',
        'type', 'strike', 'open', 'close_price',
        'profit', 'profit_pct', 'loss', 'pnl'
    ]

    for c in display_cols:
        if c not in df.columns:
            df[c] = pd.NA

    return df[display_cols + ['date_obj']]

def _normalize_asset_class(value):
    value = str(value or 'index').strip().lower()
    if value in ('company', 'companies', 'stock', 'stocks', 'الشركات', 'شركات'):
        return 'company'
    if value in ('all', 'both', '*'):
        return 'all'
    return 'index'


def _normalize_timeframe(value):
    value = str(value or 'daily').strip().lower()
    return value if value in TRADE_TIMEFRAMES else 'daily'


def _normalize_symbol(value):
    value = str(value or '').strip().upper()
    return '' if value in ('', 'ALL', '*') else value


def _trade_file_configs(asset_class='index', symbol='SPX', timeframe='daily'):
    asset_class = _normalize_asset_class(asset_class)
    raw_symbol = str(symbol or '').strip().upper()
    symbol = _normalize_symbol(symbol)
    timeframe = _normalize_timeframe(timeframe)
    prefix = TRADE_TIMEFRAMES[timeframe]
    configs = []

    if asset_class in ('index', 'all'):
        selected = list(INDEX_TRADE_FILES.keys()) if raw_symbol in ('ALL', '*') else (
            [symbol] if symbol in INDEX_TRADE_FILES else list(INDEX_TRADE_FILES.keys())
        )
        if asset_class == 'index' and not symbol and raw_symbol not in ('ALL', '*'):
            selected = ['SPX']
        for ticker in selected:
            data = INDEX_TRADE_FILES[ticker]
            configs.append({
                'asset_class': 'index',
                'symbol': ticker,
                'ticker': ticker,
                'timeframe': timeframe,
                'csv_path': os.path.join(BASE_DIR, prefix + data['csv']),
                'json_path': os.path.join(BASE_DIR, prefix + data['json']),
            })

    if asset_class in ('company', 'all'):
        configs.append({
            'asset_class': 'company',
            'symbol': symbol,
            'ticker': symbol,
            'timeframe': timeframe,
            'csv_path': os.path.join(BASE_DIR, prefix + COMPANY_TRADE_FILES['csv']),
            'json_path': os.path.join(BASE_DIR, prefix + COMPANY_TRADE_FILES['json']),
        })

    return configs


def _existing_col(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _numeric_series(series):
    return pd.to_numeric(
        series.astype(str).str.replace(r'[\$,]', '', regex=True).str.strip(),
        errors='coerce'
    ).fillna(0)


def _read_json_meta(path):
    try:
        if not os.path.exists(path):
            return pd.DataFrame(columns=['Trade ID', 'created_at', 'closed_at', 'ticker_name'])
        df_json = pd.read_json(path, orient='records')
        df_json.columns = df_json.columns.str.strip()
        keep = [c for c in ['Trade ID', 'created_at', 'closed_at', 'ticker_name', 'timeframe'] if c in df_json.columns]
        if 'Trade ID' not in keep:
            return pd.DataFrame(columns=['Trade ID', 'created_at', 'closed_at', 'ticker_name'])
        return df_json[keep].copy()
    except Exception as e:
        print(f"!!! تحذير: تعذرت قراءة ملف JSON {path}: {e}")
        return pd.DataFrame(columns=['Trade ID', 'created_at', 'closed_at', 'ticker_name'])


def _format_duration(td):
    if pd.isna(td):
        return '---'
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f'{hours:02}:{minutes:02}'


def get_data_from_excel(start_date=None, end_date=None, asset_class='index', symbol='SPX', timeframe='daily'):
    frames = []
    requested_symbol = _normalize_symbol(symbol)

    for cfg in _trade_file_configs(asset_class, symbol, timeframe):
        csv_path = cfg['csv_path']
        if not os.path.exists(csv_path):
            continue

        try:
            df_csv = load_df(csv_path)
        except Exception as e:
            print(f"!!! تحذير: تعذرت قراءة ملف CSV {csv_path}: {e}")
            continue

        df_csv.columns = df_csv.columns.str.strip()
        df_json = _read_json_meta(cfg['json_path'])

        if 'Trade ID' in df_csv.columns and not df_json.empty:
            df = pd.merge(df_csv, df_json, on='Trade ID', how='left')
        else:
            df = df_csv.copy()
            df['created_at'] = pd.NaT
            df['closed_at'] = pd.NaT

        df['asset_class'] = cfg['asset_class']
        df['timeframe'] = cfg['timeframe']
        df['source_file'] = os.path.basename(csv_path)

        ticker_col = _existing_col(df, ['Ticker', 'ticker', 'ticker_name'])
        if cfg['asset_class'] == 'company':
            df['ticker'] = df[ticker_col].astype(str).str.upper().str.strip() if ticker_col else cfg['ticker']
            df['symbol'] = df['ticker']
            if requested_symbol:
                df = df[df['ticker'].astype(str).str.upper().str.strip() == requested_symbol]
        else:
            df['ticker'] = cfg['symbol']
            df['symbol'] = cfg['symbol']
        df['asset_symbol'] = df['ticker']

        frames.append(df)

    display_cols = [
        'number', 'date', 'entry_time', 'duration', 'type', 'strike', 'open',
        'close_price', 'profit', 'profit_pct', 'loss', 'pnl', 'asset_class',
        'symbol', 'ticker', 'asset_symbol', 'timeframe', 'source_file', 'trade_id'
    ]

    if not frames:
        return pd.DataFrame(columns=display_cols + ['date_obj'])

    df = pd.concat(frames, ignore_index=True, sort=False)
    df.columns = df.columns.str.strip()

    df['date_obj'] = pd.to_datetime(df.get('created_at'), errors='coerce')
    mask_no_created = df['date_obj'].isna()
    if 'Date' in df.columns:
        df.loc[mask_no_created, 'date_obj'] = pd.to_datetime(df.loc[mask_no_created, 'Date'], errors='coerce')
    df.loc[df['date_obj'].isna(), 'date_obj'] = pd.to_datetime('today').normalize()

    df['date'] = df['date_obj'].dt.strftime('%Y-%m-%d')
    df['entry_time'] = df['date_obj'].apply(format_arabic_time)

    df['closed_at_obj'] = pd.to_datetime(df.get('closed_at'), errors='coerce')
    df['duration'] = (df['closed_at_obj'] - df['date_obj']).apply(_format_duration)
    duration_col = _existing_col(df, ['مدة التحقيق', 'Ù…Ø¯Ø© Ø§Ù„ØªØ­Ù‚ÙŠÙ‚'])
    if duration_col:
        df['duration'] = df['duration'].where(df['duration'] != '---', df[duration_col].fillna('---'))

    df['number'] = df['Number'] if 'Number' in df.columns else pd.RangeIndex(start=1, stop=len(df) + 1)
    type_col = _existing_col(df, ['Type Contract', 'Type'])
    df['type'] = df[type_col].astype(str).str.upper().str.strip() if type_col else pd.NA
    strike_col = _existing_col(df, ['SPX Strike', 'Strike'])
    df['strike'] = df[strike_col] if strike_col else pd.NA
    open_col = _existing_col(df, ['Open', 'Entry Price'])
    df['open'] = df[open_col] if open_col else pd.NA
    close_col = _existing_col(df, ['السعر المحقق', 'Ø§Ù„Ø³Ø¹Ø± Ø§Ù„Ù…Ø­Ù‚Ù‚', 'High'])
    df['close_price'] = df[close_col] if close_col else pd.NA
    profit_col = _existing_col(df, ['الربح بالعقد', 'Ø§Ù„Ø±Ø¨Ø­ Ø¨Ø§Ù„Ø¹Ù‚Ø¯', 'Profit'])
    loss_col = _existing_col(df, ['الخسارة بالعقد', 'Ø§Ù„Ø®Ø³Ø§Ø±Ø© Ø¨Ø§Ù„Ø¹Ù‚Ø¯', 'Loss'])
    df['profit'] = df[profit_col] if profit_col else 0
    df['loss'] = df[loss_col] if loss_col else 0

    for col in ['profit', 'loss']:
        df[col] = _numeric_series(df[col])

    df['open_numeric'] = _numeric_series(df['open'])
    df['close_numeric'] = _numeric_series(df['close_price'])

    if start_date:
        start_dt = pd.to_datetime(start_date)
        df = df[df['date_obj'] >= start_dt]
    if end_date:
        end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        df = df[df['date_obj'] <= end_dt]

    df['pnl'] = df['profit'] - df['loss']

    def calc_profit_pct(row):
        if row['open_numeric'] > 0 and row['close_numeric'] > 0:
            return ((row['close_numeric'] - row['open_numeric']) / row['open_numeric']) * 100.0
        return 0.0

    df['profit_pct'] = df.apply(calc_profit_pct, axis=1)
    df['trade_id'] = df['Trade ID'] if 'Trade ID' in df.columns else ''

    for c in display_cols:
        if c not in df.columns:
            df[c] = pd.NA

    return df[display_cols + ['date_obj']]

def format_currency(value):
    if pd.isna(value) or not isinstance(value, (int, float)): return "$0.00"
    return f"${value:,.2f}"

@app.context_processor
def utility_processor(): return dict(format_currency=format_currency)
# ---------------------------------

# --- المسارات (Routes) ---
def _require_admin_json():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    return None

def _period_date_range(period):
    today = datetime.now().date()
    period = (period or '').lower()
    if period in ('daily', 'day', 'today'):
        return today.isoformat(), today.isoformat()
    if period in ('weekly', 'week'):
        return (today - timedelta(days=6)).isoformat(), today.isoformat()
    if period in ('monthly', 'month'):
        return today.replace(day=1).isoformat(), today.isoformat()
    return None, None

def _duration_to_minutes(value):
    try:
        parts = str(value or '').split(':')
        if len(parts) >= 2:
            return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        pass
    return 0

def _to_float(value, default=0.0):
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    try:
        cleaned = str(value).replace('$', '').replace(',', '').strip()
        if not cleaned:
            return default
        return float(cleaned)
    except Exception:
        return default


def _trade_filter_args():
    asset_class = request.args.get('asset_class') or request.args.get('asset') or 'index'
    symbol = request.args.get('symbol') or request.args.get('ticker')
    if not symbol:
        symbol = 'ALL' if _normalize_asset_class(asset_class) == 'company' else 'SPX'
    return {
        'asset_class': asset_class,
        'symbol': symbol,
        'timeframe': request.args.get('timeframe') or 'daily',
    }


def _load_dashboard_trades(start_date=None, end_date=None, asset_class='index', symbol='SPX', timeframe='daily'):
    df = get_data_from_excel(start_date, end_date, asset_class=asset_class, symbol=symbol, timeframe=timeframe).copy()
    trades = []
    if df.empty:
        return trades
    for _, row in df.iterrows():
        date_obj = row.get('date_obj')
        hour = int(date_obj.hour) if not pd.isna(date_obj) else 0
        minute = int(date_obj.minute) if not pd.isna(date_obj) else 0
        trade_type = str(row.get('type') or '').upper()
        date_value = str(row.get('date') or '')
        try:
            day_of_week = datetime.fromisoformat(date_value).weekday()
        except Exception:
            day_of_week = 0
        trades.append({
            'id': str(row.get('number') or len(trades) + 1),
            'date': date_value,
            'entry_time': str(row.get('entry_time') or ''),
            'duration': str(row.get('duration') or '---'),
            'duration_minutes': _duration_to_minutes(row.get('duration')),
            'side': 'call' if trade_type == 'CALL' else 'put',
            'type': trade_type,
            'strike': None if pd.isna(row.get('strike')) else str(row.get('strike')),
            'entry': _to_float(row.get('open')),
            'open': _to_float(row.get('open')),
            'peak': _to_float(row.get('close_price')),
            'close_price': _to_float(row.get('close_price')),
            'profit': _to_float(row.get('profit')),
            'loss': _to_float(row.get('loss')),
            'raw_profit': _to_float(row.get('profit')),
            'raw_loss': _to_float(row.get('loss')),
            'pnl': _to_float(row.get('pnl')),
            'hour': hour,
            'minute': minute,
            'dayOfWeek': day_of_week,
            'status': 'closed',
            'asset_class': str(row.get('asset_class') or ''),
            'symbol': str(row.get('symbol') or ''),
            'ticker': str(row.get('ticker') or ''),
            'asset_symbol': str(row.get('asset_symbol') or row.get('ticker') or row.get('symbol') or ''),
            'timeframe': str(row.get('timeframe') or ''),
            'source_file': str(row.get('source_file') or ''),
            'trade_id': str(row.get('trade_id') or ''),
        })
    return trades

def _user_status(user):
    if int(user.get('is_frozen') or 0) == 1:
        return 'frozen'
    sub_end = user.get('subscription_end')
    if not sub_end:
        return 'inactive'
    try:
        return 'active' if datetime.fromisoformat(str(sub_end)) > datetime.now() else 'expired'
    except Exception:
        return 'inactive'

def _fetch_users():
    ensure_zid_columns()
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT chat_id, name, username, phone_number, paid, subscription_package,
               subscription_end, first_seen, total_paid_amount, referral_code,
               referred_by_code, referral_count, is_frozen, frozen_days_remaining,
               client_username, client_password, referral_wallet_balance,
               referral_reward_preference, referral_discount_balance,
               referral_cashout_balance, referral_days_earned
        FROM users
        ORDER BY first_seen DESC
    """)
    rows = []
    for r in cur.fetchall():
        row = dict(r)
        side = (row.get('type') or '').upper() or 'CALL'
        entry_time = row.get('created_at') or row.get('date')
        exit_time = row.get('updated_at') or entry_time
        symbol = row.get('symbol') or row.get('contract') or ''
        rows.append({
            **row,
            'side': side,
            'qty': int(row.get('quantity') or 1),
            'entry_price': float(row.get('entry') or 0),
            'exit_price': float(row.get('exit') or 0),
            'entry_time': entry_time,
            'exit_time': exit_time,
            'symbol': symbol,
        })
    conn.close()
    return rows

def _referral_settings():
    settings = get_settings().get('referral_settings', {})
    defaults = {
        'first_time_bonus': 10,
        'renewal_bonus': 3,
        'first_time_amount': 0,
        'renewal_amount': 0,
        'first_time_discount': 0,
        'renewal_discount': 0,
        'cashout_minimum': 150,
        'package_rewards': {}
    }
    defaults.update(settings or {})
    return defaults

def _reward_amount(settings, key, fallback_key=None):
    value = settings.get(key)
    if value in (None, '') and fallback_key:
        value = settings.get(fallback_key)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _referral_package_reward(referral_settings, package_name, reward_type, fallback):
    rewards = referral_settings.get('package_rewards') or {}
    package_key = str(package_name or '').strip().lower()
    reward_row = None
    for key, value in rewards.items():
        if str(key or '').strip().lower() == package_key:
            reward_row = value or {}
            break
    if not reward_row:
        return fallback
    try:
        value = reward_row.get(reward_type)
        value = float(value or 0)
        return fallback if value <= 0 else value
    except (TypeError, ValueError):
        return fallback

def _cashout_withdrawal_id(chat_id):
    return f"cashout_{chat_id}"

def _sync_cashout_withdrawal(settings, user_row, amount):
    threshold = _reward_amount(_referral_settings(), 'cashout_minimum')
    if amount < threshold or threshold <= 0:
        return

    withdrawals = settings.setdefault('withdrawals', [])
    wid = _cashout_withdrawal_id(user_row['chat_id'])
    existing = next((w for w in withdrawals if str(w.get('id')) == wid), None)
    if existing and existing.get('status', 'pending') == 'pending':
        existing['amount'] = round(amount, 2)
        existing['updated_at'] = datetime.now().isoformat()
        return
    if existing and existing.get('status') == 'approved':
        return

    withdrawals.append({
        'id': wid,
        'chat_id': user_row['chat_id'],
        'name': user_row['name'] or user_row['username'] or f"عميل {user_row['chat_id']}",
        'username': user_row['username'] or '',
        'phone_number': user_row['phone_number'] or '',
        'amount': round(amount, 2),
        'status': 'pending',
        'source': 'referral_cashout',
        'requested_at': datetime.now().isoformat(),
        'note': 'تم إنشاء الطلب تلقائياً بعد وصول رصيد كاش أوت إلى حد السحب.'
    })

def _apply_referral_reward(cursor, referrer_code, referred_name, was_paid_before, settings, package_name=''):
    cursor.execute("""
        SELECT chat_id, name, username, phone_number, subscription_end,
               referral_reward_preference, referral_cashout_balance,
               referral_discount_balance
        FROM users
        WHERE referral_code = ?
        LIMIT 1
    """, (referrer_code,))
    referrer = cursor.fetchone()
    if not referrer:
        return None

    prefs = {'cashout', 'discount', 'days'}
    reward_type = (referrer['referral_reward_preference'] or 'days').lower()
    if reward_type not in prefs:
        reward_type = 'days'

    referral_settings = settings.get('referral_settings') or _referral_settings()
    is_renewal = bool(was_paid_before)

    if reward_type == 'cashout':
        amount = _referral_package_reward(referral_settings, package_name, 'cashout', _reward_amount(
            referral_settings,
            'renewal_amount' if is_renewal else 'first_time_amount'
        ))
        cursor.execute("""
            UPDATE users
            SET referral_count = COALESCE(referral_count, 0) + 1,
                referral_wallet_balance = COALESCE(referral_wallet_balance, 0) + ?,
                referral_cashout_balance = COALESCE(referral_cashout_balance, 0) + ?
            WHERE chat_id = ?
        """, (amount, amount, referrer['chat_id']))
        return {'chat_id': referrer['chat_id'], 'type': 'cashout', 'value': amount, 'unit': 'ر.س'}

    if reward_type == 'discount':
        amount = _referral_package_reward(referral_settings, package_name, 'discount', _reward_amount(
            referral_settings,
            'renewal_discount' if is_renewal else 'first_time_discount',
            'renewal_amount' if is_renewal else 'first_time_amount'
        ))
        cursor.execute("""
            UPDATE users
            SET referral_count = COALESCE(referral_count, 0) + 1,
                referral_discount_balance = COALESCE(referral_discount_balance, 0) + ?
            WHERE chat_id = ?
        """, (amount, referrer['chat_id']))
        return {'chat_id': referrer['chat_id'], 'type': 'discount', 'value': amount, 'unit': 'ر.س'}

    fallback_days = int(referral_settings.get('renewal_bonus', 3) if is_renewal else referral_settings.get('first_time_bonus', 10))
    days = int(_referral_package_reward(referral_settings, package_name, 'days', fallback_days))
    cursor.execute("""
        UPDATE users
        SET subscription_end = CASE
                WHEN subscription_end IS NULL OR subscription_end = ''
                THEN datetime('now', ? || ' days')
                ELSE datetime(subscription_end, ? || ' days')
            END,
            referral_count = COALESCE(referral_count, 0) + 1,
            referral_days_earned = COALESCE(referral_days_earned, 0) + ?
        WHERE chat_id = ?
    """, (f'+{days}', f'+{days}', days, referrer['chat_id']))
    return {'chat_id': referrer['chat_id'], 'type': 'days', 'value': days, 'unit': 'يوم'}

def _client_payload(user, idx=0):
    package_name = user.get('subscription_package') or 'بدون باقة'
    package_lower = package_name.lower()
    if not user.get('subscription_package') or package_name == 'بدون باقة':
        pkg_slug = 'none'
    elif 'vip' in package_lower:
        pkg_slug = 'vip'
    else:
        pkg_slug = 'premium'
    end = str(user.get('subscription_end') or '').split('T')[0].split(' ')[0]
    return {
        'id': f"C{user.get('chat_id')}",
        'chat_id': user.get('chat_id'),
        'name': user.get('name') or user.get('username') or f"عميل {user.get('chat_id')}",
        'username': user.get('username') or '',
        'client_username': user.get('client_username') or '',
        'phone': user.get('phone_number') or '',
        'code': user.get('referral_code') or '',
        'referrer': user.get('referred_by_code') or '',
        'refs': int(user.get('referral_count') or 0),
        'paid': float(user.get('total_paid_amount') or 0),
        'pkg': pkg_slug,
        'pkgLabel': package_name,
        'package': package_name,
        'end': end,
        'subscription_end': user.get('subscription_end'),
        'status': _user_status(user),
        'avatarColor': ['cyan', 'purple', 'gold', 'emerald', 'crimson'][idx % 5],
        'frozenDaysRemaining': user.get('frozen_days_remaining'),
    }

def _csv_response(filename, headers, rows):
    import csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    data = io.BytesIO(('\ufeff' + output.getvalue()).encode('utf-8'))
    return send_file(data, mimetype='text/csv; charset=utf-8', as_attachment=True, download_name=filename)

@app.route('/pages/<path:filename>')
def dashboard_page_asset(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'templates', 'pages'), filename)

@app.route('/client')
@app.route('/client/<chat_id>')
def client_dashboard(chat_id=None):
    if chat_id and session.get('role') == 'client':
        session['client_chat_id'] = str(chat_id)
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or request.form
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    valid_user = (
        username == os.getenv('ADMIN_USERNAME', '') and
        password == os.getenv('ADMIN_PASSWORD', '')
    )
    if valid_user:
        session['logged_in'] = True
        session['role'] = 'admin'
        session['user'] = username
        return jsonify({'status': 'ok', 'user': username, 'role': 'admin'})

    ensure_zid_columns()
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT chat_id, name, client_username, paid, subscription_end, is_frozen
        FROM users
        WHERE client_username = ? AND client_password = ?
        LIMIT 1
    """, (username, password))
    user = cur.fetchone()
    conn.close()

    if user:
        user_dict = dict(user)
        if _user_status(user_dict) not in ('active', 'frozen'):
            return jsonify({'status': 'error', 'message': 'Client subscription is not active'}), 403
        session['logged_in'] = True
        session['role'] = 'client'
        session['client_chat_id'] = str(user['chat_id'])
        session['user'] = user['client_username']
        return jsonify({
            'status': 'ok',
            'user': user['client_username'],
            'name': user['name'] or user['client_username'],
            'role': 'client',
            'chat_id': str(user['chat_id'])
        })

    return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'status': 'ok'})
def _json_safe(value):
    if value is None:
        return None

    # Pandas / NumPy NaN / NaT
    if pd is not None:
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]

    return value
@app.route('/api/trades')
def api_trades():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    try:
        # جلب كل البيانات بدون فلترة تاريخ (لأن الجافاسكريبت سيفلترها)
        filters = _trade_filter_args()
        trades = _load_dashboard_trades(
            request.args.get('start_date'),
            request.args.get('end_date'),
            **filters
        )
        return jsonify({'status': 'ok', 'trades': trades, 'filters': filters})

        df = get_data_from_excel()
        
        if df.empty:
            return jsonify({'status': 'ok', 'trades': []})

        trades_list = []
        for index, row in df.iterrows():
            # تحويل القيم بأمان
            entry_price = float(row['open']) if pd.notna(row['open']) and str(row['open']).replace('.','',1).isdigit() else 0.0
            close_price = float(row['close_price']) if pd.notna(row['close_price']) and str(row['close_price']).replace('.','',1).isdigit() else 0.0
            pnl = float(row['pnl']) if pd.notna(row['pnl']) else 0.0
            
            # استخراج الساعة والدقيقة من وقت الدخول
            entry_time_str = str(row['entry_time'])
            hour = 0
            minute = 0
            if ':' in entry_time_str:
                time_parts = entry_time_str.split(' ')[0].split(':')
                if len(time_parts) == 2:
                    hour = int(time_parts[0])
                    minute = int(time_parts[1])
                    # تعديل للساعة بنظام 24 إذا كان مساءً
                    if 'مساء' in entry_time_str and hour != 12:
                        hour += 12
            
            trades_list.append({
                'id': str(row['number']),
                'date': str(row['date']),
                'hour': hour,
                'minute': minute,
                'type': str(row['type']),
                'strike': str(row['strike']),
                'entry': entry_price,
                'peak': close_price,
                'pnl': pnl,
                'duration': 0 # سيتم حسابه أو تجاهله إذا لم يكن متوفراً بدقة
            })
            
        return jsonify({'status': 'ok', 'trades': trades_list})
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500
@app.route('/api/trades/export')
def api_trades_export():
    denied = _require_admin_json()
    if denied:
        return denied
    filters = _trade_filter_args()
    trades = _load_dashboard_trades(request.args.get('start_date'), request.args.get('end_date'), **filters)
    headers = ['date', 'asset_class', 'asset_symbol', 'ticker', 'timeframe', 'type', 'strike', 'entry', 'close_price', 'profit', 'loss', 'pnl', 'duration']
    return _csv_response('trades.csv', headers, [[t.get(h, '') for h in headers] for t in trades])

@app.route('/api/clients')
def api_clients():
    denied = _require_admin_json()
    if denied:
        return denied
    clients = [_client_payload(u, i) for i, u in enumerate(_fetch_users())]
    return jsonify({'status': 'ok', 'clients': clients})

@app.route('/api/subscriptions')
def api_subscriptions():
    denied = _require_admin_json()
    if denied:
        return denied
    users = _fetch_users()
    subs = []
    active = frozen = expired = this_month = 0
    revenue = 0.0
    current_month = datetime.now().strftime('%Y-%m')
    for u in users:
        p = _client_payload(u)
        active += p['status'] == 'active'
        frozen += p['status'] == 'frozen'
        expired += p['status'] == 'expired'
        revenue += p['paid']
        if str(u.get('first_seen') or '').startswith(current_month):
            this_month += 1
        subs.append({'chatId': u.get('chat_id'), 'name': p['name'], 'package': p['package'], 'status': p['status'], 'end': p['end'], 'paid': p['paid'], 'phone': p['phone']})
    return jsonify({'status': 'ok', 'subscriptions': subs, 'packages': get_settings().get('packages', []), 'kpis': {'active': active, 'frozen': frozen, 'expired': expired, 'revenue': revenue, 'thisMonth': this_month}})

@app.route('/api/referrals')
def api_referrals():
    denied = _require_admin_json()
    if denied:
        return denied
    users = _fetch_users()
    by_code = {u.get('referral_code'): u for u in users if u.get('referral_code')}
    referrals = []
    for u in users:
        code = u.get('referred_by_code')
        if not code:
            continue
        referrer = by_code.get(code, {})
        item = dict(u)
        item['referrer_name'] = referrer.get('name') or referrer.get('username') or ''
        item['referrer_username'] = referrer.get('username') or ''
        item['referrer_reward_preference'] = referrer.get('referral_reward_preference') or 'days'
        referrals.append(item)

    leaders = sorted(
        [u for u in users if int(u.get('referral_count') or 0) > 0],
        key=lambda x: int(x.get('referral_count') or 0),
        reverse=True
    )
    reward_stats = {
        'cashout': sum(1 for u in leaders if (u.get('referral_reward_preference') or 'days') == 'cashout'),
        'discount': sum(1 for u in leaders if (u.get('referral_reward_preference') or 'days') == 'discount'),
        'days': sum(1 for u in leaders if (u.get('referral_reward_preference') or 'days') == 'days'),
        'cashoutBalance': sum(float(u.get('referral_cashout_balance') or 0) for u in leaders),
        'discountBalance': sum(float(u.get('referral_discount_balance') or 0) for u in leaders),
        'daysEarned': sum(int(u.get('referral_days_earned') or 0) for u in leaders)
    }
    return jsonify({
        'status': 'ok',
        'referrals': referrals,
        'leaders': leaders[:25],
        'rewardStats': reward_stats,
        'settings': _referral_settings()
    })

@app.route('/api/referrals/export')
def api_referrals_export():
    denied = _require_admin_json()
    if denied:
        return denied
    referrals = [u for u in _fetch_users() if u.get('referred_by_code')]
    headers = ['chat_id', 'name', 'referred_by_code', 'subscription_package', 'total_paid_amount']
    return _csv_response('referrals.csv', headers, [[r.get(h, '') for h in headers] for r in referrals])

@app.route('/api/withdrawals')
def api_withdrawals():
    denied = _require_admin_json()
    if denied:
        return denied
    settings = get_settings()
    withdrawals = [
        w for w in settings.get('withdrawals', [])
        if w.get('source') == 'client_request'
    ]
    pending = sum(1 for w in withdrawals if w.get('status', 'pending') == 'pending')
    approved = sum(1 for w in withdrawals if w.get('status') == 'approved')
    rejected = sum(1 for w in withdrawals if w.get('status') == 'rejected')
    total_paid = sum(float(w.get('amount') or 0) for w in withdrawals if w.get('status') == 'approved')
    pending_amount = sum(float(w.get('amount') or 0) for w in withdrawals if w.get('status', 'pending') == 'pending')
    return jsonify({
        'status': 'ok',
        'withdrawals': withdrawals,
        'kpis': {
            'pending': pending,
            'approved': approved,
            'rejected': rejected,
            'totalPaid': total_paid,
            'pendingAmount': pending_amount,
            'amount': total_paid
        }
    })

@app.route('/api/withdrawals/<withdrawal_id>/<action>', methods=['POST'])
def api_withdrawal_action(withdrawal_id, action):
    denied = _require_admin_json()
    if denied:
        return denied
    if action not in ('approve', 'reject'):
        return jsonify({'status': 'error', 'message': 'Invalid action'}), 400
    settings = get_settings()
    withdrawals = settings.setdefault('withdrawals', [])
    note = (request.get_json(silent=True) or {}).get('note', '')
    for w in withdrawals:
        if str(w.get('id')) == str(withdrawal_id):
            w['status'] = 'approved' if action == 'approve' else 'rejected'
            w['admin_note'] = note
            w['updated_at'] = datetime.now().isoformat()
            if action == 'approve' and w.get('chat_id'):
                try:
                    amount = float(w.get('amount') or 0)
                    conn = sqlite3.connect(DATABASE_PATH)
                    cur = conn.cursor()
                    cur.execute("""
                        UPDATE users
                        SET referral_cashout_balance = MAX(COALESCE(referral_cashout_balance, 0) - ?, 0),
                            referral_wallet_balance = MAX(COALESCE(referral_wallet_balance, 0) - ?, 0)
                        WHERE chat_id = ?
                    """, (amount, amount, w.get('chat_id')))
                    conn.commit()
                    conn.close()
                except Exception:
                    print(traceback.format_exc())
            save_settings({'withdrawals': withdrawals})
            return jsonify({'status': 'ok'})
    return jsonify({'status': 'error', 'message': 'Withdrawal not found'}), 404

@app.route('/api/withdrawals/export')
def api_withdrawals_export():
    denied = _require_admin_json()
    if denied:
        return denied
    withdrawals = [
        w for w in get_settings().get('withdrawals', [])
        if w.get('source') == 'client_request'
    ]
    headers = ['id', 'chat_id', 'name', 'phone', 'amount', 'bank', 'account_name', 'iban', 'status', 'created_at']
    return _csv_response('withdrawals.csv', headers, [[w.get(h, '') for h in headers] for w in withdrawals])


def _notification_segment_labels():
    return {
        'all': 'كل العملاء',
        'active': 'المشتركين النشطين',
        'expired': 'المنتهية اشتراكاتهم',
        'expiring': 'قرب انتهاء الاشتراك',
        'vip': 'VIP',
        'custom_ids': 'القائمة المخصصة',
    }


def _normalize_multi(value):
    if value is None:
        return []
    if isinstance(value, str):
        items = value.split(',')
    elif isinstance(value, (list, tuple, set)):
        items = []
        for item in value:
            if isinstance(item, str) and ',' in item:
                items.extend(item.split(','))
            else:
                items.append(item)
    else:
        items = [value]

    normalized = []
    for item in items:
        item = str(item or '').strip()
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def _normalize_groups(value):
    allowed = {'public', 'private'}
    return [group for group in _normalize_multi(value) if group in allowed]


def _notification_group_chat_id(group_type):
    if group_type == 'public':
        return str(PUBLIC_GROUP_ID or '').strip()
    if group_type == 'private':
        return str(PRIVATE_GROUP_ID or '').strip()
    return ''


def _is_expiring_user(user, now=None):
    now = now or datetime.now()
    try:
        end = datetime.fromisoformat(str(user.get('subscription_end')))
        return now <= end <= now + timedelta(days=7)
    except Exception:
        return False


def _notification_segment_counts(users=None):
    users = users if users is not None else _fetch_users()
    settings = get_settings()
    now = datetime.now()
    counts = {key: 0 for key in _notification_segment_labels()}
    custom_ids = {str(x).strip() for x in settings.get('allowed_user_ids', []) if str(x).strip()}

    counts['all'] = len([u for u in users if u.get('chat_id')])
    for user in users:
        chat_id = str(user.get('chat_id') or '').strip()
        if not chat_id:
            continue
        status = _user_status(user)
        package = str(user.get('subscription_package') or '').lower()
        if status == 'active':
            counts['active'] += 1
        if status == 'expired':
            counts['expired'] += 1
        if _is_expiring_user(user, now):
            counts['expiring'] += 1
        if 'vip' in package:
            counts['vip'] += 1
        if chat_id in custom_ids:
            counts['custom_ids'] += 1

    return counts


def _notification_user_matches(user, segment, custom_ids=None, now=None):
    chat_id = str(user.get('chat_id') or '').strip()
    if not chat_id:
        return False
    if segment == 'all':
        return True
    if segment == 'active':
        return _user_status(user) == 'active'
    if segment == 'expired':
        return _user_status(user) == 'expired'
    if segment == 'expiring':
        return _is_expiring_user(user, now)
    if segment == 'vip':
        return 'vip' in str(user.get('subscription_package') or '').lower()
    if segment == 'custom_ids':
        return chat_id in (custom_ids or set())
    return False


def _notification_recipients(segments):
    segments = [s for s in _normalize_multi(segments) if s in _notification_segment_labels()]
    if not segments:
        return []

    settings = get_settings()
    custom_ids = {str(x).strip() for x in settings.get('allowed_user_ids', []) if str(x).strip()}
    now = datetime.now()
    recipients = []
    seen = set()

    for user in _fetch_users():
        chat_id = str(user.get('chat_id') or '').strip()
        if not chat_id or chat_id in seen:
            continue
        if any(_notification_user_matches(user, segment, custom_ids, now) for segment in segments):
            seen.add(chat_id)
            recipients.append(chat_id)

    return recipients


def _build_notification_text(data):
    title = (data.get('title') or '').strip()
    message = (data.get('message') or data.get('text') or '').strip()
    link = (data.get('link') or '').strip()
    return '\n\n'.join(part for part in (title, message, link) if part).strip()


def _send_payment_bot_message(chat_id, text, image_token=''):
    chat_id = str(chat_id or '').strip()
    if not chat_id or not text:
        return False

    try:
        if image_token:
            url = f"https://api.telegram.org/bot{PAYMENT_BOT_TOKEN}/sendPhoto"
            local_path = os.path.join(SCHEDULED_IMAGES_FOLDER, image_token)
            if os.path.isfile(local_path):
                with open(local_path, 'rb') as img_file:
                    files = {'photo': ('notification.png', img_file, 'image/png')}
                    payload = {'chat_id': chat_id, 'caption': text, 'parse_mode': 'HTML'}
                    resp = requests.post(url, data=payload, files=files, timeout=20)
            else:
                payload = {'chat_id': chat_id, 'photo': image_token, 'caption': text, 'parse_mode': 'HTML'}
                resp = requests.post(url, json=payload, timeout=20)
        else:
            return send_telegram_message(chat_id, text)

        print("Telegram notification:", resp.status_code, resp.text[:300])
        return resp.status_code == 200
    except Exception:
        print(traceback.format_exc())
        return False


@app.route('/api/notifications/segments')
def api_notification_segments():
    denied = _require_admin_json()
    if denied:
        return denied
    users = _fetch_users()
    segments = _notification_segment_counts(users)
    destinations = {
        'public': {'label': 'المجموعة العامة', 'enabled': bool(str(PUBLIC_GROUP_ID or '').strip())},
        'private': {'label': 'المجموعة الخاصة', 'enabled': bool(str(PRIVATE_GROUP_ID or '').strip())},
    }
    labels = _notification_segment_labels()
    return jsonify({'status': 'ok', 'segments': segments, 'labels': labels, 'destinations': destinations})


@app.route('/api/notifications/scheduled')
def api_notifications_scheduled():
    denied = _require_admin_json()
    if denied:
        return denied

    messages = []
    for msg in get_settings().get('scheduled_messages', []):
        item = dict(msg)
        image_filename = item.get('image_filename') or ''
        item['image_url'] = f"/static/scheduled/{image_filename}" if image_filename else ''
        item['groups'] = _normalize_multi(item.get('groups') or item.get('destinations'))
        item['segments'] = _normalize_multi(item.get('segments'))
        messages.append(item)
    return jsonify({'status': 'ok', 'scheduled_messages': messages})

@app.route('/api/notifications/send', methods=['POST'])
def api_notifications_send():
    denied = _require_admin_json()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    text = _build_notification_text(data)
    segments = _normalize_multi(data.get('segments') or data.get('segment'))
    groups = _normalize_groups(data.get('destinations') or data.get('groups'))
    image_token = (data.get('image_filename') or data.get('image_token') or '').strip()

    if not text:
        return jsonify({'status': 'error', 'message': 'Notification text is required'}), 400
    if not segments and not groups:
        return jsonify({'status': 'error', 'message': 'Select at least one target'}), 400

    sent = failed = 0

    for chat_id in _notification_recipients(segments):
        ok = _send_payment_bot_message(chat_id, text, image_token)
        sent += 1 if ok else 0
        failed += 0 if ok else 1

    for group in groups:
        chat_id = _notification_group_chat_id(group)
        ok = _send_payment_bot_message(chat_id, text, image_token)
        sent += 1 if ok else 0
        failed += 0 if ok else 1

    return jsonify({'status': 'ok', 'sent': sent, 'failed': failed})

@app.route('/api/auditlog')
def api_auditlog():
    denied = _require_admin_json()
    if denied:
        return denied
    events = get_settings().get('audit_log', [])
    return jsonify({'status': 'ok', 'events': events, 'logs': events})

@app.route('/api/auditlog/export')
def api_auditlog_export():
    denied = _require_admin_json()
    if denied:
        return denied
    events = get_settings().get('audit_log', [])
    headers = ['time', 'user', 'action', 'details']
    return _csv_response('auditlog.csv', headers, [[e.get(h, '') for h in headers] for e in events])


def _client_request_chat_id():
    if session.get('role') == 'admin':
        data = request.get_json(silent=True) or {}
        return str(request.args.get('chat_id') or data.get('chat_id') or session.get('client_chat_id') or '').strip()
    if not session.get('logged_in') or session.get('role') != 'client':
        return ''
    return str(session.get('client_chat_id') or '').strip()


def _client_required_chat_id():
    chat_id = _client_request_chat_id()
    if not chat_id:
        return None, (jsonify({'status': 'error', 'message': 'Client login required'}), 401)
    return chat_id, None


def _load_client_user(chat_id):
    ensure_zid_columns()
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT chat_id, name, username, phone_number, paid, subscription_package,
               subscription_end, referral_code, referred_by_code, referral_count,
               referral_wallet_balance, referral_reward_preference,
               referral_discount_balance, referral_cashout_balance,
               referral_days_earned, client_username
        FROM users
        WHERE chat_id = ?
        LIMIT 1
    """, (chat_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def _load_client_trades(chat_id, limit=500):
    ensure_client_trade_tables()
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, chat_id, date, symbol, contract, type, strike, entry, exit,
               quantity, pnl, status, note, created_at, updated_at
        FROM client_trades
        WHERE chat_id = ?
        ORDER BY COALESCE(date, created_at) DESC, created_at DESC
        LIMIT ?
    """, (str(chat_id), int(limit)))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _client_trade_summary(trades):
    total = len(trades)
    wins = [t for t in trades if float(t.get('pnl') or 0) > 0]
    losses = [t for t in trades if float(t.get('pnl') or 0) <= 0]
    net = sum(float(t.get('pnl') or 0) for t in trades)
    return {
        'total': total,
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round((len(wins) / total * 100), 1) if total else 0,
        'net_pnl': round(net, 2),
        'gross_profit': round(sum(float(t.get('pnl') or 0) for t in wins), 2),
        'gross_loss': round(abs(sum(float(t.get('pnl') or 0) for t in losses)), 2),
    }


@app.route('/api/client/profile')
def api_client_profile():
    chat_id, denied = _client_required_chat_id()
    if denied:
        return denied
    user = _load_client_user(chat_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'Client not found'}), 404
    trades = _load_client_trades(chat_id, 1000)
    referral_settings = _referral_settings()
    return jsonify({'status': 'ok', 'client': _client_payload(user), 'wallet': {
        'wallet': float(user.get('referral_wallet_balance') or 0),
        'cashout': float(user.get('referral_cashout_balance') or 0),
        'discount': float(user.get('referral_discount_balance') or 0),
        'days': int(user.get('referral_days_earned') or 0),
        'reward_preference': user.get('referral_reward_preference') or 'days',
        'cashout_minimum': float(referral_settings.get('cashout_minimum') or 200)
    }, 'summary': _client_trade_summary(trades)})


@app.route('/api/client/password/reset', methods=['POST'])
def api_client_password_reset():
    if not session.get('logged_in') or session.get('role') != 'client':
        return jsonify({'status': 'error', 'message': 'Client login required'}), 401
    data = request.get_json(silent=True) or {}
    new_password = str(data.get('password') or '').strip()
    if len(new_password) < 6:
        return jsonify({'status': 'error', 'message': 'Password must be at least 6 characters'}), 400
    chat_id = str(session.get('client_chat_id') or '').strip()
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET client_password = ? WHERE chat_id = ?", (new_password, chat_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'message': 'Password updated'})


@app.route('/api/client/referral/preference', methods=['POST'])
def api_client_referral_preference():
    if not session.get('logged_in') or session.get('role') != 'client':
        return jsonify({'status': 'error', 'message': 'Client login required'}), 401
    data = request.get_json(silent=True) or {}
    pref = str(data.get('preference') or '').strip().lower()
    if pref not in {'cashout', 'discount', 'days'}:
        return jsonify({'status': 'error', 'message': 'Invalid preference'}), 400
    chat_id = str(session.get('client_chat_id') or '').strip()
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET referral_reward_preference = ? WHERE chat_id = ?", (pref, chat_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'preference': pref})


@app.route('/api/client/referrals')
def api_client_referrals():
    chat_id, denied = _client_required_chat_id()
    if denied:
        return denied
    user = _load_client_user(chat_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'Client not found'}), 404
    code = user.get('referral_code') or ''
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT chat_id, name, username, subscription_package, paid, first_seen,
               total_paid_amount
        FROM users
        WHERE referred_by_code = ?
        ORDER BY first_seen DESC
    """, (code,))
    referrals = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({
        'status': 'ok',
        'referrals': referrals,
        'stats': {
            'count': len(referrals),
            'paid': sum(1 for r in referrals if int(r.get('paid') or 0) == 1),
            'totalPaid': round(sum(float(r.get('total_paid_amount') or 0) for r in referrals), 2)
        }
    })


@app.route('/api/client/withdrawals')
def api_client_withdrawals():
    chat_id, denied = _client_required_chat_id()
    if denied:
        return denied
    settings = get_settings()
    withdrawals = [
        w for w in settings.get('withdrawals', [])
        if str(w.get('chat_id')) == str(chat_id) and w.get('source') == 'client_request'
    ]
    withdrawals.sort(key=lambda w: str(w.get('created_at') or ''), reverse=True)
    return jsonify({'status': 'ok', 'withdrawals': withdrawals})


@app.route('/api/client/withdrawals/request', methods=['POST'])
def api_client_withdrawal_request():
    chat_id, denied = _client_required_chat_id()
    if denied:
        return denied
    user = _load_client_user(chat_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'Client not found'}), 404
    data = request.get_json(silent=True) or {}
    try:
        amount = float(data.get('amount') or 0)
    except (TypeError, ValueError):
        amount = 0
    bank = str(data.get('bank') or '').strip()
    account_name = str(data.get('account_name') or '').strip()
    iban = str(data.get('iban') or '').replace(' ', '').upper().strip()
    available = float(user.get('referral_cashout_balance') or user.get('referral_wallet_balance') or 0)
    min_amount = float((_referral_settings() or {}).get('cashout_minimum') or 200)
    if amount <= 0:
        return jsonify({'status': 'error', 'message': 'أدخل مبلغ السحب'}), 400
    if amount < min_amount:
        return jsonify({'status': 'error', 'message': f'الحد الأدنى للسحب {min_amount:g} ر.س'}), 400
    if amount > available:
        return jsonify({'status': 'error', 'message': 'المبلغ أكبر من الرصيد المتاح'}), 400
    if not bank or not account_name or not iban:
        return jsonify({'status': 'error', 'message': 'أكمل بيانات البنك والآيبان'}), 400
    if not iban.startswith('SA') or len(iban) < 20:
        return jsonify({'status': 'error', 'message': 'صيغة الآيبان غير صحيحة'}), 400

    settings = get_settings()
    withdrawals = settings.setdefault('withdrawals', [])
    now = datetime.now().isoformat()
    withdrawal = {
        'id': f"WD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{str(chat_id)[-4:]}",
        'source': 'client_request',
        'chat_id': str(chat_id),
        'name': user.get('name') or user.get('username') or f"عميل {chat_id}",
        'username': user.get('username') or '',
        'phone': user.get('phone_number') or '',
        'amount': round(amount, 2),
        'bank': bank,
        'account_name': account_name,
        'iban': iban,
        'method': 'bank',
        'status': 'pending',
        'created_at': now,
        'updated_at': now,
        'note': 'طلب مرسل من صفحة محفظة العميل'
    }
    withdrawals.append(withdrawal)
    save_settings({'withdrawals': withdrawals})
    return jsonify({'status': 'ok', 'withdrawal': withdrawal})


@app.route('/api/client/trades/list')
def api_client_trades_list():
    chat_id, denied = _client_required_chat_id()
    if denied:
        return denied
    limit = int(request.args.get('limit') or 200)
    trades = _load_client_trades(chat_id, limit)
    return jsonify({'status': 'ok', 'chat_id': chat_id, 'trades': trades})

@app.route('/api/client/analyzer')
def api_client_analyzer():
    chat_id, denied = _client_required_chat_id()
    if denied:
        return denied
    trades = list(reversed(_load_client_trades(chat_id, 1000)))
    capital = 10000.0
    equity = []
    wins = losses = 0
    total_pnl = 0.0
    best_trade = None
    worst_trade = None
    for t in trades:
        change = float(t.get('pnl') or 0)
        total_pnl += change
        if change > 0:
            wins += 1
        elif change < 0:
            losses += 1
        item = {'id': t.get('id'), 'pnl': round(change, 2)}
        if best_trade is None or change > best_trade['pnl']:
            best_trade = item
        if worst_trade is None or change < worst_trade['pnl']:
            worst_trade = item
        capital += change
        equity.append({
            'date': t.get('date'),
            'time': t.get('exit_time') or t.get('entry_time') or t.get('date'),
            'equity': round(capital, 2),
            'change': round(change, 2)
        })
    total = len(trades)
    gross_win = sum(float(t.get('pnl') or 0) for t in trades if float(t.get('pnl') or 0) > 0)
    gross_loss = abs(sum(float(t.get('pnl') or 0) for t in trades if float(t.get('pnl') or 0) < 0))
    summary = {
        **_client_trade_summary(trades),
        'total_trades': total,
        'open_count': 0,
        'wins': wins,
        'losses': losses,
        'win_rate': round((wins / total * 100), 1) if total else 0,
        'total_pnl': round(total_pnl, 2),
        'profit_factor': round(gross_win / gross_loss, 2) if gross_loss else None,
        'expectancy': round(total_pnl / total, 2) if total else 0,
        'best_trade': best_trade,
        'worst_trade': worst_trade,
    }
    insights = []
    if total:
        insights.append({'title': 'ملخص الأداء', 'text': f'صافي الربح {round(total_pnl, 2)}$ من {total} صفقة.', 'icon': 'pulse', 'level': 'info'})
    return jsonify({'status': 'ok', 'empty': total == 0, 'summary': summary, 'equity_curve': equity, 'insights': insights})

@app.route('/api/client/trades/log', methods=['POST'])
@app.route('/api/client/trades/close', methods=['POST'])
@app.route('/api/client/trades/delete', methods=['POST'])
def api_client_trade_mutation():
    chat_id, denied = _client_required_chat_id()
    if denied:
        return denied
    ensure_client_trade_tables()
    data = request.get_json(silent=True) or {}
    path = request.path
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        cur = conn.cursor()
        now = datetime.now().isoformat()
        if path.endswith('/delete'):
            trade_id = str(data.get('id') or data.get('trade_id') or '').strip()
            cur.execute("DELETE FROM client_trades WHERE id = ? AND chat_id = ?", (trade_id, chat_id))
            conn.commit()
            return jsonify({'status': 'ok'})
        if path.endswith('/close'):
            trade_id = str(data.get('id') or data.get('trade_id') or '').strip()
            exit_price = float(data.get('exit') or data.get('exit_price') or 0)
            entry_price = float(data.get('entry') or data.get('entry_price') or 0)
            qty = int(float(data.get('quantity') or data.get('qty') or 1))
            pnl = float(data.get('pnl') or ((exit_price - entry_price) * 100 * qty if entry_price and exit_price else 0))
            cur.execute("""
                UPDATE client_trades
                SET exit = ?, pnl = ?, status = 'closed', updated_at = ?
                WHERE id = ? AND chat_id = ?
            """, (exit_price, pnl, now, trade_id, chat_id))
            conn.commit()
            return jsonify({'status': 'ok'})

        trade_id = str(uuid.uuid4())
        entry = float(data.get('entry') or data.get('entry_price') or 0)
        exit_price = float(data.get('exit') or data.get('exit_price') or 0)
        qty = int(float(data.get('quantity') or data.get('qty') or 1))
        pnl = float(data.get('pnl') or ((exit_price - entry) * 100 * qty if exit_price else 0))
        status = 'closed' if exit_price else 'open'
        side = str(data.get('type') or data.get('side') or '').upper() or 'CALL'
        entry_time = data.get('entry_time') or now
        exit_time = data.get('exit_time') or now
        cur.execute("""
            INSERT INTO client_trades
            (id, chat_id, date, symbol, contract, type, strike, entry, exit, quantity, pnl, status, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id, chat_id, data.get('date') or datetime.now().strftime('%Y-%m-%d'),
            data.get('symbol') or '', data.get('contract') or data.get('symbol') or '', side,
            data.get('strike') or '', entry, exit_price, qty, pnl, status,
            data.get('note') or '', entry_time, exit_time
        ))
        conn.commit()
        return jsonify({'status': 'ok', 'id': trade_id, 'trade': {'id': trade_id}})
    finally:
        conn.close()

@app.route('/api/client/trades/clear', methods=['POST'])
def api_client_trades_clear():
    chat_id, denied = _client_required_chat_id()
    if denied:
        return denied
    ensure_client_trade_tables()
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM client_trades WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})

@app.route('/api/client/trades/export')
def api_client_trades_export():
    chat_id, denied = _client_required_chat_id()
    if denied:
        return denied
    trades = _load_client_trades(chat_id, 5000)
    headers = ['id', 'symbol', 'side', 'qty', 'entry_price', 'exit_price', 'entry_time', 'exit_time', 'pnl', 'status', 'note']
    return _csv_response(f'client_{chat_id}_trades.csv', headers, [[t.get(h, '') for h in headers] for t in trades])

@app.route('/login', methods=['GET', 'POST'])
def login():
    # إذا كان المستخدم مسجل دخوله بالفعل، انقله مباشرة للوحة التحكم
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # التحقق من اسم المستخدم وكلمة المرور
        valid_user = (
        username == os.getenv('ADMIN_USERNAME', '') and
        password == os.getenv('ADMIN_PASSWORD', '')
    )

        if valid_user:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة')
            return redirect(url_for('login'))
            
    return render_template('index.html')

@app.route('/api/referral_settings')
def get_referral_settings_api():
    return jsonify(_referral_settings())


@app.route('/api/settings/dashboard')
def api_settings_dashboard():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    settings = get_settings()
    return jsonify({
        'status': 'ok',
        'schedule_time': settings.get('schedule_time', '23:59'),
        'monitor_increase': settings.get('monitor_increase', 0.10),
        'allowed_user_ids': settings.get('allowed_user_ids', []),
        'referral_settings': _referral_settings(),
        'packages': settings.get('packages', []),
        'indicator_packages': settings.get('indicator_packages', []),
        'trade_image_templates': _trade_template_payload(settings),
    })

@app.route('/save_referral_settings', methods=['POST'])
def save_referral_settings():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    first_bonus = int(data.get('first_time_bonus', 10))
    renewal_bonus = int(data.get('renewal_bonus', 3))
    reward_type = str(data.get('reward_type', 'days')).lower()
    if reward_type not in ('days', 'amount'):
        reward_type = 'days'
    first_amount = float(data.get('first_time_amount', 0) or 0)
    renewal_amount = float(data.get('renewal_amount', 0) or 0)
    first_discount = float(data.get('first_time_discount', 0) or 0)
    renewal_discount = float(data.get('renewal_discount', 0) or 0)
    cashout_minimum = float(data.get('cashout_minimum', 150) or 0)
    package_rewards = {}
    for name, row in (data.get('package_rewards') or {}).items():
        package_name = str(name or '').strip()
        if not package_name:
            continue
        row = row or {}
        package_rewards[package_name] = {
            'cashout': float(row.get('cashout', 0) or 0),
            'discount': float(row.get('discount', 0) or 0),
            'days': int(float(row.get('days', 0) or 0)),
        }
    
    if first_bonus < 0 or renewal_bonus < 0:
        return jsonify({'status': 'error', 'message': 'القيم لا يمكن أن تكون سالبة'}), 400
    
    save_settings({
        'referral_settings': {
            'first_time_bonus': first_bonus,
            'renewal_bonus': renewal_bonus,
            'reward_type': reward_type,
            'first_time_amount': first_amount,
            'renewal_amount': renewal_amount,
            'first_time_discount': first_discount,
            'renewal_discount': renewal_discount,
            'cashout_minimum': cashout_minimum,
            'package_rewards': package_rewards
        }
    })
    
    return jsonify({'status': 'ok', 'message': 'تم حفظ إعدادات الإحالة بنجاح'})
@app.route('/logout')
def logout():
    session.pop('logged_in', None) # حذف بيانات الجلسة
    flash('تم تسجيل خروجك بنجاح')
    return redirect(url_for('login'))
@app.route('/')
def home():
    """الصفحة الرئيسية العامة لـ CAMELSPX - بدون login"""
    return render_template('index.html')
@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        settings = get_settings()
        report_settings = settings.get('report_settings', {})
        logo_url = None
        
        # --- منطق الفلترة وتحديد التواريخ ---
        filter_type = request.args.get('filter', 'daily')
        today = datetime.today()
        
        # مصفوفات لتعريب التاريخ
        days_ar =['الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
        months_ar =['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
        
        if filter_type == 'weekly':
            # آخر 7 أيام
            start_date = (today - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
            report_title = f"نتائج الأسبوع (من {start_date} إلى {end_date})"
        elif filter_type == 'monthly':
            # من بداية الشهر الحالي
            start_date = today.replace(day=1).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
            report_title = f"نتائج شهر {months_ar[today.month - 1]} {today.year}"
        else:
            # يومي (أو بحسب اختيار المستخدم اليدوي)
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            
            if not start_date and not end_date:
                start_date = today.strftime('%Y-%m-%d')
                end_date = today.strftime('%Y-%m-%d')
                report_title = f"نتائج يوم {days_ar[today.weekday()]} {today.day} {months_ar[today.month - 1]}"
            else:
                report_title = f"نتائج من {start_date} إلى {end_date}"
                if not end_date: end_date = today.strftime('%Y-%m-%d')
                if not start_date: start_date = end_date

        # جلب البيانات
        df = get_data_from_excel(start_date, end_date)
        
        if os.path.exists(app.config['UPLOAD_FOLDER']) and os.listdir(app.config['UPLOAD_FOLDER']):
            filename = os.listdir(app.config['UPLOAD_FOLDER'])[0]
            logo_url = f'/static/uploads/{filename}'
            
        # --- حساب الإحصائيات في الباك إند ---
        total_profit = float(df['profit'].sum()) if not df.empty else 0.0
        total_loss  = float(df['loss'].sum()) if not df.empty else 0.0
        total_pnl   = float(df['pnl'].sum()) if not df.empty else 0.0
        total_trades = len(df)
        
        # حساب الصفقات الرابحة والخاسرة (بناءً على الوصف: 100 دولار فأكثر ربح، أقل من 100 خسارة)
        if not df.empty:
            win_trades = int((df['pnl'] >= 50).sum())
            loss_trades = int((df['pnl'] < 50).sum())
        else:
            win_trades = 0
            loss_trades = 0
            
        # نسبة النجاح
        success_rate = round((win_trades / total_trades * 100), 2) if total_trades > 0 else 0

        call_trades = int((df['type'] == 'CALL').sum()) if not df.empty else 0
        put_trades  = int((df['type'] == 'PUT').sum()) if not df.empty else 0
        table_data = json.loads(df.to_json(orient='records')) if not df.empty else[]
        overall_stats = {'pnl': total_pnl, 'number': total_trades}
        
        # الرسم البياني الشهري
        if not df.empty and pd.api.types.is_datetime64_any_dtype(df['date_obj']):
            monthly_pnl = df.groupby(pd.Grouper(key='date_obj', freq='M'))['pnl'].sum()
            chart_labels = monthly_pnl.index.strftime('%Y-%m').tolist()
            chart_pnl_data =[float(pnl) for pnl in monthly_pnl.values]
        else:
            chart_labels = []
            chart_pnl_data = []
            
        chart_type_data =[call_trades, put_trades]
        
        return render_template(
            'index.html',
            table_data=table_data, 
            total_profit=total_profit, 
            total_loss=total_loss, 
            net_profit=total_pnl, 
            overall_stats=overall_stats, 
            call_trades=call_trades, 
            put_trades=put_trades, 
            chart_labels=chart_labels,
            chart_pnl_data=chart_pnl_data, 
            chart_type_data=chart_type_data, 
            start_date=start_date or '', 
            end_date=end_date or '',
            logo_url=logo_url, 
            report_settings=report_settings,
            
            # المتغيرات الجديدة الخاصة بالفلترة والإحصائيات
            filter_type=filter_type,
            report_title=report_title,
            win_trades=win_trades,
            loss_trades=loss_trades,
            total_trades=total_trades,
            success_rate=success_rate,
            
            saved_opacity=int(settings.get('opacity', 10)),
            saved_schedule_time=settings.get('schedule_time', '23:59'),
            saved_monitor_increase=settings.get('monitor_increase', 0.10),
            closing_messages=settings.get('closing_messages', {'list':[], 'selected': ''}),
            scheduled_messages=settings.get('scheduled_messages',[])
        )
    except Exception as e:
        print(traceback.format_exc())
        return f"<h1>حدث خطأ:</h1><p>{e}</p>", 500
import uuid 
# لا تحتاج لمكتبات جديدة أخرى

# --- أضف هذه المسارات الجديدة إلى ملف aبpp.py ---

# مسار جديد لإدارة الباقات
@app.route('/settings/packages', methods=['GET', 'POST'])
def manage_packages():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    if request.method == 'GET':
        return jsonify({'status': 'ok', 'packages': get_settings().get('packages', [])})

    data = request.get_json() or {}
    action = data.get('action')
    package = data.get('package') or {}

    settings = get_settings()

    if 'packages' not in settings:
        settings['packages'] = []

    # تنظيف الحقول الأساسية
    if action in ('add', 'update'):
        package['name'] = str(package.get('name', '')).strip()
        package['price'] = str(package.get('price', '')).strip()
        package['duration_days'] = str(package.get('duration_days', '')).strip()

        # رابط الباقة في سلة، مع إبقاء zid_product_url للتوافق مع أي كود قديم.
        package_url = str(
            package.get('zid_product_url')
            or package.get('product_url')
            or package.get('salla_product_url')
            or package.get('payment_url')
            or package.get('url')
            or ''
        ).strip()
        package['product_url'] = package_url
        package['zid_product_url'] = package_url

        if not package['name']:
            return jsonify({'status': 'error', 'message': 'اسم الباقة مطلوب'}), 400

        if not package['duration_days']:
            return jsonify({'status': 'error', 'message': 'مدة الباقة مطلوبة'}), 400

        if not package_url:
            return jsonify({'status': 'error', 'message': 'رابط الباقة مطلوب'}), 400

    if action == 'add':
        if 'id' not in package or not package.get('id'):
            package['id'] = str(uuid.uuid4())

        settings['packages'].append(package)
        print(f"تم إضافة باقة جديدة: {package['name']}")

    elif action == 'update':
        package_id = package.get('id')
        found = False

        for i, p in enumerate(settings['packages']):
            if str(p.get('id')) == str(package_id):
                settings['packages'][i] = package
                found = True
                break

        if not found:
            return jsonify({'status': 'error', 'message': 'الباقة غير موجودة للتعديل'}), 404

        print(f"تم تعديل الباقة: {package['name']}")

    elif action == 'delete':
        package_id = package.get('id')
        original_count = len(settings['packages'])

        settings['packages'] = [
            p for p in settings['packages']
            if str(p.get('id')) != str(package_id)
        ]

        if len(settings['packages']) == original_count:
            return jsonify({'status': 'error', 'message': 'الباقة غير موجودة للحذف'}), 404

        print(f"تم حذف الباقة بـ ID: {package_id}")

    else:
        return jsonify({'status': 'error', 'message': 'إجراء غير معروف'}), 400

    save_settings(settings)

    return jsonify({
        'status': 'ok',
        'packages': settings['packages']
    })
# في ملف app.py
import hmac
import hashlib

@app.route('/toggle_freeze', methods=['POST'])
def toggle_freeze():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')

        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # جلب بيانات المستخدم الحالية
        cursor.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'status': 'error', 'message': 'User not found'}), 404

        # توكن بوت الاشتراكات لإرسال الرسائل (نفس المستخدم في الويب هوك)
        PAYMENT_BOT_TOKEN = os.getenv('PAYMENT_BOT_TOKEN', '')

        if user['is_frozen']:
            # ==========================================
            # 1. حالة إلغاء التجميد (العودة للقناة)
            # ==========================================
            days_left = user['frozen_days_remaining']
            if days_left is None or days_left <= 0:
                new_end_date = datetime.now() - timedelta(days=1)
            else:
                new_end_date = datetime.now() + timedelta(days=days_left)
            
            cursor.execute("""
                UPDATE users SET is_frozen = 0, subscription_end = ?, frozen_days_remaining = NULL 
                WHERE chat_id = ?
            """, (new_end_date.isoformat(), chat_id))
            
            # 🌟 إنشاء رابط وإرسال رسالة العودة للعميل 🌟
            try:
                invite_url = f"https://api.telegram.org/bot{PAYMENT_BOT_TOKEN}/createChatInviteLink"
                payload_inv = {'chat_id': '-1003703182738', 'expire_date': int(time.time()) + 300, 'member_limit': 1}
                resp_inv = requests.post(invite_url, json=payload_inv, timeout=10).json()
                invite_link = resp_inv['result']['invite_link'] if resp_inv.get('ok') else None
            except:
                invite_link = None

            msg = (
                f"❄️ <b>تم إلغاء تجميد اشتراكك بنجاح!</b>\n\n"
                f"📅 تاريخ الانتهاء الجديد: <b>{new_end_date.strftime('%Y-%m-%d')}</b>\n"
                f"🚀 نرحب بعودتك للتداول معنا:\n"
            )
            if invite_link:
                msg += f"🔗 <a href=\"{invite_link}\">اضغط هنا للدخول إلى القناة فورًا</a>\n⚠️ <i>الرابط صالح لمدة 60 ثانية فقط.</i>"
            else:
                msg += "⚠️ <i>حدث خطأ في توليد الرابط، تواصل مع الدعم.</i>"

            requests.post(f"https://api.telegram.org/bot{PAYMENT_BOT_TOKEN}/sendMessage", json={
                'chat_id': chat_id, 'text': msg, 'parse_mode': 'HTML', 'disable_web_page_preview': True
            })

            flash('تم إلغاء تجميد اشتراك العميل وإرسال رابط العودة له بنجاح.')

        else:
            # ==========================================
            # 2. حالة التجميد (الإيقاف المؤقت)
            # ==========================================
            sub_end_dt = datetime.fromisoformat(user['subscription_end']) if user['subscription_end'] else None
            
            if not sub_end_dt or sub_end_dt < datetime.now():
                return jsonify({'status': 'error', 'message': 'Subscription expired'})

            remaining_days = (sub_end_dt - datetime.now()).days
            
            cursor.execute("""
                UPDATE users SET is_frozen = 1, frozen_days_remaining = ?
                WHERE chat_id = ?
            """, (remaining_days, chat_id))

            removed_ok, remove_message = remove_user_from_private_channel(chat_id)
            if not removed_ok:
                print(f"تعذر إخراج العميل من القناة أثناء التجميد: {remove_message}")
            
            # 🌟 إرسال رسالة التجميد للعميل 🌟
            msg = (
                f"❄️ <b>تم تجميد اشتراكك بنجاح!</b>\n\n"
                f"⏳ الأيام المحفوظة لك: <b>{remaining_days} يوم</b>\n"
                f"سيتم ازالتك  من القناة مؤقتاً لحفظ أيامك، وعند فك التجميد سيصلك رابط العودة تلقائياً. بالتوفيق! 🚀"
            )
            requests.post(f"https://api.telegram.org/bot{PAYMENT_BOT_TOKEN}/sendMessage", json={
                'chat_id': chat_id, 'text': msg, 'parse_mode': 'HTML'
            })

            flash('تم تجميد اشتراك العميل بنجاح.')

        conn.commit()
        conn.close()
        return jsonify({'status': 'ok'})

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/kick_client/<int:chat_id>', methods=['POST'])
def kick_client(chat_id):
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    ok, message = remove_user_from_private_channel(chat_id)
    if not ok:
        return jsonify({'status': 'error', 'message': message}), 500

    return jsonify({'status': 'ok'})


@app.route('/clients')
def clients_page():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # الإحصائيات (نفسها)
        cursor.execute("SELECT COUNT(chat_id) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(total_paid_amount) FROM users")
        total_revenue = cursor.fetchone()[0] or 0.0
        
        # جلب كل الأعمدة بما فيها الجديدة للإحالة
        cursor.execute("""
            SELECT chat_id, name, username, phone_number, paid, subscription_package, subscription_end, 
                   total_paid_amount, is_frozen, frozen_days_remaining,
                   referral_code, referred_by_code, referral_count 
            FROM users ORDER BY first_seen DESC
        """)
        clients = cursor.fetchall()
        conn.close()

        # معالجة البيانات (نفس السابق مع إضافة الجديد)
        clients_data = []
        active_subscribers = 0
        for client in clients:
            client_dict = dict(client)
            sub_end_str = client_dict.get('subscription_end')
            is_active = False
            if sub_end_str:
                try:
                    sub_end_dt = datetime.fromisoformat(sub_end_str)
                    client_dict['subscription_end_formatted'] = sub_end_dt.strftime('%Y-%m-%d %H:%M')
                    if datetime.now() < sub_end_dt:
                        is_active = True
                        active_subscribers += 1
                except (ValueError, TypeError):
                    client_dict['subscription_end_formatted'] = "تاريخ غير صالح"
            else:
                client_dict['subscription_end_formatted'] = "لا يوجد"
            
            client_dict['is_active'] = is_active
            
            # إضافة عرض للأكواد
            client_dict['referral_code_display'] = client_dict.get('referral_code') or "غير مُولد بعد"
            client_dict['referred_by_code_display'] = client_dict.get('referred_by_code') or "لا يوجد"
            client_dict['referral_count_display'] = client_dict.get('referral_count', 0)
            
            clients_data.append(client_dict)

        stats = {
            'total_users': total_users,
            'total_revenue': total_revenue,
            'active_subscribers': active_subscribers,
            'inactive_users': total_users - active_subscribers
        }

        settings = get_settings()
        packages = settings.get('packages', [])
        
        # تمرير إعدادات الإحالة للعرض إن أردت (اختياري الآن)
        referral_settings = settings.get('referral_settings', {'first_time_bonus': 10, 'renewal_bonus': 3})

        return render_template('clients.html', clients=clients_data, packages=packages, stats=stats,
                               referral_settings=referral_settings)
    except Exception as e:
        print(traceback.format_exc())
        return f"<h1>خطأ في عرض العملاء:</h1><p>{e}</p>", 500
# أضف هذه الدالة الجديدة في ملف app.py

@app.route('/settings', methods=['GET'])
def settings_page():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    settings = get_settings()

    opacity = int(settings.get('opacity', 10))
    schedule_time = settings.get('schedule_time', '23:59')
    monitor_increase = settings.get('monitor_increase', 0.10)
    scheduled_messages = settings.get('scheduled_messages', [])

    # تجهيز رابط الصورة لكل رسالة مجدولة
    for msg in scheduled_messages:
        filename = msg.get('image_filename') or ''
        if filename:
            msg['image_url'] = url_for('static', filename=f'scheduled/{filename}')
        else:
            msg['image_url'] = ''

    # الشعار
    logo_url = None
    if os.path.exists(app.config['UPLOAD_FOLDER']) and os.listdir(app.config['UPLOAD_FOLDER']):
        filename = os.listdir(app.config['UPLOAD_FOLDER'])[0]
        logo_url = f'/static/uploads/{filename}'

    # تمرير إعدادات الإحالة بشكل صحيح
    referral_settings = settings.get('referral_settings', {
        'first_time_bonus': 10,
        'renewal_bonus': 3
    })

    # إضافة إعدادات التقرير (الجديد)
    report_settings = settings.get('report_settings', {})

    return render_template(
        'settings.html',
        logo_url=logo_url,
        saved_opacity=opacity,
        saved_schedule_time=schedule_time,
        saved_monitor_increase=monitor_increase,
        scheduled_messages=scheduled_messages,
        referral_settings=referral_settings,
        report_settings=report_settings,       # ← الإضافة الجديدة المطلوبة
        settings=settings                      # اختياري: إذا كنت تحتاجه في القالب أيضاً
    )
import os

# 1. مسار حفظ النصوص والألوان والأحجام
@app.route('/api/save_report_settings', methods=['POST'])
def save_report_settings():
    data = request.get_json()
    settings = get_settings()
    
    # حفظ البيانات المرسلة داخل مفتاح report_settings
    settings['report_settings'] = data
    
    save_settings(settings)
    return jsonify({'status': 'ok'})

# 2. مسار رفع الشعار الجديد
@app.route('/api/upload_report_logo', methods=['POST'])
def upload_report_logo():
    if 'logo' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file'})
    
    file = request.files['logo']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'Empty filename'})

    # حفظ الصورة في مجلد static/images باسم ثابت لسهولة الوصول إليه
    # تأكد أن المسار صحيح في جهازك
    image_path = os.path.join('static', 'images', 'custom_logo.png')
    file.save(image_path)
    
    return jsonify({'status': 'ok', 'url': '/static/images/custom_logo.png'})


@app.route('/api/trade_image_templates', methods=['GET'])
def api_trade_image_templates():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    return jsonify({'status': 'ok', 'templates': _trade_template_payload()})


@app.route('/api/trade_image_templates/preview/<slot>')
def api_trade_image_template_preview(slot):
    item, _templates = _trade_template_slot(slot)
    if not item:
        return jsonify({'status': 'error', 'message': 'Unknown template slot'}), 404
    path = item.get('pending_path') or item.get('active_path')
    use_right = slot.endswith('_right')
    return send_file(_draw_trade_template_preview(path, use_right), mimetype='image/png', download_name=f'{slot}_preview.png')


@app.route('/api/trade_image_templates/upload', methods=['POST'])
def api_trade_image_template_upload():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    slot = (request.form.get('slot') or '').strip()
    item, templates = _trade_template_slot(slot)
    if not item:
        return jsonify({'status': 'error', 'message': 'Unknown template slot'}), 400
    if 'image' not in request.files:
        return jsonify({'status': 'error', 'message': 'No image uploaded'}), 400

    file = request.files['image']
    if not file.filename:
        return jsonify({'status': 'error', 'message': 'Empty file name'}), 400

    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower() or '.png'
    pending_name = f'{slot}_{uuid.uuid4().hex}{ext}'
    pending_path = os.path.join(TRADE_TEMPLATE_PENDING_FOLDER, pending_name)
    file.save(pending_path)

    size = _image_size(pending_path)
    expected = item.get('expected_size') or size
    if expected and size != expected:
        try:
            os.remove(pending_path)
        except Exception:
            pass
        return jsonify({
            'status': 'error',
            'message': f'Image size must be {expected[0]}x{expected[1]} px. Uploaded image is {size[0]}x{size[1]} px.'
        }), 400

    item['pending_path'] = _rel_path(pending_path)
    templates[slot] = item
    _save_trade_templates(templates)

    return jsonify({
        'status': 'ok',
        'slot': slot,
        'pending_url': _static_url(pending_path),
        'size': size,
        'preview_url': f'/api/trade_image_templates/preview/{slot}?v={int(time.time())}'
    })


@app.route('/api/trade_image_templates/save', methods=['POST'])
def api_trade_image_template_save():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    slot = str(data.get('slot') or '').strip()
    item, templates = _trade_template_slot(slot)
    if not item:
        return jsonify({'status': 'error', 'message': 'Unknown template slot'}), 400

    pending_path = item.get('pending_path') or ''
    if not pending_path or not os.path.exists(_abs_path(pending_path)):
        return jsonify({'status': 'error', 'message': 'No pending image to save'}), 400

    active_path = item.get('active_path') or ''
    archive = item.setdefault('archive', [])
    if active_path and os.path.exists(_abs_path(active_path)):
        archived_name = f"{slot}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(active_path)}"
        archived_path = os.path.join(TRADE_TEMPLATE_ARCHIVE_FOLDER, archived_name)
        shutil.copy2(_abs_path(active_path), archived_path)
        archive.insert(0, _rel_path(archived_path))
        item['archive'] = archive[:10]

    ext = os.path.splitext(pending_path)[1] or '.png'
    active_name = f'{slot}{ext}'
    final_path = os.path.join(TRADE_TEMPLATE_FOLDER, active_name)
    shutil.move(_abs_path(pending_path), final_path)
    item['active_path'] = _rel_path(final_path)
    item['expected_size'] = _image_size(final_path)
    item.pop('pending_path', None)
    templates[slot] = item
    _save_trade_templates(templates)

    return jsonify({'status': 'ok', 'templates': _trade_template_payload()})


@app.route('/api/trade_image_templates/revert', methods=['POST'])
def api_trade_image_template_revert():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    slot = str(data.get('slot') or '').strip()
    item, templates = _trade_template_slot(slot)
    if not item:
        return jsonify({'status': 'error', 'message': 'Unknown template slot'}), 400

    archive = item.get('archive') or []
    previous = next((p for p in archive if os.path.exists(_abs_path(p))), '')
    if not previous:
        return jsonify({'status': 'error', 'message': 'No archived image found'}), 400

    item['active_path'] = previous
    item['expected_size'] = _image_size(previous)
    item.pop('pending_path', None)
    templates[slot] = item
    _save_trade_templates(templates)
    return jsonify({'status': 'ok', 'templates': _trade_template_payload()})

# 3. مسار استعادة الضبط الأصلي (Reset)
@app.route('/api/reset_report_settings', methods=['POST'])
def reset_report_settings():
    try:
        # بما أن دالة save_settings تقوم بعمل update (دمج)
        # فالحل هو إرسال "report_settings" كقاموس فارغ ليتم الكتابة فوق القديم
        reset_payload = {
            'report_settings': {} 
        }
        
        # استدعاء دالتك كما هي دون تغييرها
        save_settings(reset_payload)
        print("Report settings cleared (set to empty dictionary).")

        # حذف الشعار المخصص إذا وجد
        logo_path = os.path.join('static', 'images', 'custom_logo.png')
        if os.path.exists(logo_path):
            try:
                os.remove(logo_path)
                print("Custom logo file deleted.")
            except Exception as e:
                print(f"Error deleting logo file: {e}")

        return jsonify({'status': 'ok', 'message': 'تمت الاستعادة بنجاح'})

    except Exception as e:
        print(f"Error during reset: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
@app.route('/analytics')
def analytics_page():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    try:
        # فلاتر التاريخ (اختياري)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # إذا لم يحدد المستخدم تاريخاً، نأخذ كل البيانات المخزنة
        df = get_data_from_excel(start_date, end_date)

        if df.empty:
            # بيانات فارغة
            return render_template(
                'analytics.html',
                has_data=False,
                start_date=start_date or '',
                end_date=end_date or ''
            )

        # إجمالي الربح والخسارة والصافي
        total_profit = float(df['profit'].sum())
        total_loss = float(df['loss'].sum())
        total_pnl = float(df['pnl'].sum())
        total_trades = int(df['number'].count())

        # عدد صفقات CALL و PUT
        call_trades = int((df['type'] == 'CALL').sum())
        put_trades = int((df['type'] == 'PUT').sum())
        chart_type_data = [call_trades, put_trades]

        # 1) منحنى Line لأداء الربح/الخسارة عبر الزمن (يومياً)
        daily_pnl = df.groupby(df['date'])['pnl'].sum().reset_index()
        line_labels = daily_pnl['date'].tolist()
        line_pnl_data = [float(x) for x in daily_pnl['pnl']]

        # 2) أعلى الاسترايكات ربحاً
        strike_pnl = df.groupby('strike')['pnl'].sum().reset_index()
        strike_pnl_sorted = strike_pnl.sort_values('pnl', ascending=False)

        best_strikes = strike_pnl_sorted.head(10)
        worst_strikes = strike_pnl_sorted.tail(10).sort_values('pnl')

        best_strikes_labels = best_strikes['strike'].astype(str).tolist()
        best_strikes_values = [float(x) for x in best_strikes['pnl']]

        worst_strikes_labels = worst_strikes['strike'].astype(str).tolist()
        worst_strikes_values = [float(x) for x in worst_strikes['pnl']]

        return render_template(
            'analytics.html',
            has_data=True,
            start_date=start_date or '',
            end_date=end_date or '',
            total_profit=total_profit,
            total_loss=total_loss,
            total_pnl=total_pnl,
            total_trades=total_trades,
            call_trades=call_trades,
            put_trades=put_trades,
            chart_type_data=chart_type_data,
            line_labels=line_labels,
            line_pnl_data=line_pnl_data,
            best_strikes_labels=best_strikes_labels,
            best_strikes_values=best_strikes_values,
            worst_strikes_labels=worst_strikes_labels,
            worst_strikes_values=worst_strikes_values
        )

    except Exception as e:
        print(traceback.format_exc())
        return f"<h1>خطأ في صفحة التحليلات:</h1><p>{e}</p>", 500

@app.route('/delete_logo', methods=['POST'])
def delete_logo():
    try:
        # حذف كل الملفات الموجودة في مجلد الرفع
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
        return jsonify({'status': 'ok', 'message': 'تم حذف الشعار بنجاح'})
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500
@app.route('/delete_client/<int:chat_id>', methods=['POST'])
def delete_client(chat_id):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
        conn.commit()
        conn.close()
        return redirect(url_for('clients_page'))
    except Exception as e:
        print(traceback.format_exc())
        return f"<h1>خطأ في حذف العميل:</h1><p>{e}</p>", 500
# --------------------------

@app.route('/save_general_settings', methods=['POST'])
def save_general_settings():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}

        schedule_time = data.get('schedule_time', '23:59')
        monitor_increase = float(data.get('monitor_increase', 0.10))

        settings_update = {
            'schedule_time': schedule_time,
            'monitor_increase': monitor_increase
        }
        if 'scheduled_messages' in data:
            settings_update['scheduled_messages'] = data.get('scheduled_messages', [])

        save_settings(settings_update)
        return jsonify({'status': 'ok', 'message': 'تم حفظ الإعدادات بنجاح'})
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/schedule_message', methods=['POST'])
def schedule_message():
    """
    إضافة رسالة مجدولة جديدة:
    - text: نص الرسالة
    - time: على هيئة HH:MM (تم تحويلها من AM/PM في الواجهة)
    - to_public: '1' أو '0'
    - to_private: '1' أو '0'
    - image: (اختياري) ملف صورة مرفوع من الجهاز
    """
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    try:
        text = (request.form.get('text') or '').strip()
        time_str = (request.form.get('time') or '').strip()

        # استلام أعلام المجموعات من الفورم
        raw_public = (request.form.get('to_public') or '0').strip()
        raw_private = (request.form.get('to_private') or '0').strip()

        to_public = raw_public in ('1', 'true', 'True', 'on')
        to_private = raw_private in ('1', 'true', 'True', 'on')
        groups = _normalize_groups(request.form.getlist('destinations') or request.form.getlist('groups'))
        if to_public and 'public' not in groups:
            groups.append('public')
        if to_private and 'private' not in groups:
            groups.append('private')
        segments = [
            segment for segment in _normalize_multi(request.form.getlist('segments') or request.form.get('segment'))
            if segment in _notification_segment_labels()
        ]

        if not text:
            return jsonify({'status': 'error', 'message': 'نص الرسالة مطلوب'}), 400
        if not time_str:
            return jsonify({'status': 'error', 'message': 'وقت الإرسال مطلوب'}), 400

        if not groups and not segments:
            return jsonify({'status': 'error', 'message': 'اختر على الأقل مجموعة واحدة'}), 400

        # حفظ الصورة (إن وجدت)
        image_file = request.files.get('image')
        image_filename = (request.form.get('image_filename') or '').strip()
        if image_file and image_file.filename:
            filename = secure_filename(image_file.filename)
            ext = os.path.splitext(filename)[1]
            unique_name = f"{uuid.uuid4().hex}{ext}"
            save_path = os.path.join(SCHEDULED_IMAGES_FOLDER, unique_name)
            image_file.save(save_path)
            image_filename = unique_name

        # تحميل الإعدادات الحالية
        settings = get_settings()
        scheduled_messages = settings.get('scheduled_messages', [])

        # إنشاء ID فريد للرسالة
        msg_id = str(uuid.uuid4())

        scheduled_messages.append({
            'id': msg_id,
            'text': text,
            'time': time_str,          # HH:MM
            'groups': groups,          # ['public'] أو ['private'] أو ['public','private']
            'segments': segments,
            'image_filename': image_filename,
            'last_sent_date': ''
        })

        # حفظ التعديل
        save_settings({'scheduled_messages': scheduled_messages})

        return jsonify({'status': 'ok', 'message': 'تمت إضافة الرسالة بنجاح', 'id': msg_id})
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500




@app.route('/delete_scheduled_message', methods=['POST'])
def delete_scheduled_message():
    """
    حذف رسالة مجدولة بحسب الـ id
    يحذف أيضاً ملف الصورة من static/scheduled إن وجد.
    """
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}
        msg_id = data.get('id')
        if not msg_id:
            return jsonify({'status': 'error', 'message': 'معرّف الرسالة غير موجود'}), 400

        settings = get_settings()
        scheduled_messages = settings.get('scheduled_messages', [])

        new_list = []
        for msg in scheduled_messages:
            if msg.get('id') == msg_id:
                # حذف الصورة إن وجدت
                image_filename = msg.get('image_filename')
                if image_filename:
                    img_path = os.path.join(SCHEDULED_IMAGES_FOLDER, image_filename)
                    try:
                        if os.path.isfile(img_path):
                            os.remove(img_path)
                    except Exception as e:
                        print("خطأ أثناء حذف ملف صورة مجدولة:", e)
                # لا نضيف هذه الرسالة إلى القائمة الجديدة (تم حذفها)
                continue
            new_list.append(msg)

        save_settings({'scheduled_messages': new_list})
        return jsonify({'status': 'ok', 'message': 'تم حذف الرسالة المجدولة'})
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/upload_logo', methods=['POST'])
def upload_logo():
    if 'logo' not in request.files: return jsonify({'status': 'error', 'message': 'No file part'}), 400
    file = request.files['logo']
    if file.filename == '': return jsonify({'status': 'error', 'message': 'No selected file'}), 400
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return jsonify({'status': 'ok', 'url': f'/static/uploads/{filename}'})
@app.route('/upload_scheduled_image', methods=['POST'])
def upload_scheduled_image():
    """
    يرفع صورة خاصة برسالة مجدولة ويحفظها في static/scheduled
    ويعيد اسم الملف + رابط المعاينة.
    """
    if 'image' not in request.files:
        return jsonify({'status': 'error', 'message': 'لم يتم اختيار صورة'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'اسم الملف فارغ'}), 400

    filename = secure_filename(file.filename)
    # اسم فريد
    ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4().hex}{ext}"

    save_path = os.path.join(SCHEDULED_IMAGES_FOLDER, unique_name)
    file.save(save_path)

    return jsonify({
        'status': 'ok',
        'filename': unique_name,
        'url': f"/static/scheduled/{unique_name}"
    })

@app.route('/save_opacity', methods=['POST'])
def save_opacity():
    data = request.get_json()
    opacity = data.get('opacity')
    if opacity is None: return jsonify({'status': 'error', 'message': 'لم يتم توفير قيمة الشفافية'}), 400
    save_settings({'opacity': int(opacity)})
    return jsonify({'status': 'ok', 'message': 'تم حفظ الشفافية'})

# --- الـ ENDPOINT الجديد المطلوب ---
@app.route('/add_watermark', methods=['POST'])
def add_watermark():
    if 'image' not in request.files:
        return jsonify({'status': 'error', 'message': 'الرجاء إرسال الصورة تحت مفتاح "image"'}), 400
    base_image_file = request.files['image']

    if not os.listdir(app.config['UPLOAD_FOLDER']):
        return jsonify({'status': 'error', 'message': 'لا توجد علامة مائية محفوظة. يرجى رفع واحدة أولاً.'}), 400
    
    try:
        settings = get_settings()
        opacity_value = settings.get('opacity', 10) / 100.0
        watermark_filename = os.listdir(app.config['UPLOAD_FOLDER'])[0]
        watermark_path = os.path.join(app.config['UPLOAD_FOLDER'], watermark_filename)

        base_image = Image.open(base_image_file.stream).convert("RGBA")
        watermark = Image.open(watermark_path).convert("RGBA")

        watermark = watermark.resize((base_image.width, base_image.height), Image.Resampling.LANCZOS)

        # تطبيق الشفافية
        alpha = watermark.getchannel('A')
        alpha = alpha.point(lambda i: int(i * opacity_value))
        watermark.putalpha(alpha)

        # لصق العلامة المائية على الصورة الأصلية (في الزاوية 0,0 لأن الحجم متطابق)
        base_image.paste(watermark, (0, 0), watermark)

        final_image_io = io.BytesIO()
        base_image.save(final_image_io, format='PNG')
        final_image_io.seek(0) # مهم جدا: إعادة المؤشر لبداية الملف
        
        # --- التغيير الرئيسي: إرسال الصورة كاستجابة ---
        return send_file(
            final_image_io,
            mimetype='image/png',
            as_attachment=True, # يجعل المتصفح يقترح تحميل الملف
            download_name='watermarked_image.png' # اسم الملف المقترح للتحميل
        )

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': f'حدث خطأ أثناء معالجة الصورة: {str(e)}'}), 500


@app.route('/api/allowed_users', methods=['GET'])
def get_allowed_users():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    settings = get_settings()
    return jsonify({'allowed_user_ids': settings.get('allowed_user_ids', [])})

@app.route('/api/allowed_users', methods=['POST'])
def manage_allowed_users():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    action = data.get('action')  # 'add' أو 'remove'
    chat_id = data.get('chat_id')
    
    if not chat_id or not str(chat_id).isdigit():
        return jsonify({'status': 'error', 'message': 'Chat ID غير صالح'}), 400
    
    chat_id = int(chat_id)
    settings = get_settings()
    allowed = settings.get('allowed_user_ids', [])
    
    if action == 'add':
        if chat_id not in allowed:
            allowed.append(chat_id)
            save_settings({'allowed_user_ids': allowed})
            return jsonify({'status': 'ok', 'message': 'تم إضافة المستخدم بنجاح', 'allowed_user_ids': allowed})
        else:
            return jsonify({'status': 'error', 'message': 'هذا المستخدم موجود مسبقًا'})
    
    elif action == 'remove':
        if chat_id in allowed:
            allowed.remove(chat_id)
            save_settings({'allowed_user_ids': allowed})
            return jsonify({'status': 'ok', 'message': 'تم حذف المستخدم بنجاح', 'allowed_user_ids': allowed})
        else:
            return jsonify({'status': 'error', 'message': 'المستخدم غير موجود'})
    
    return jsonify({'status': 'error', 'message': 'إجراء غير معروف'}), 400
def generate_table_image(start_date, end_date, title, mode='daily'):
    """
    ينشئ صورة (PNG) للجدول للفترة المحددة ويعيد bytes أو None إذا لا توجد بيانات.
    mode: 'daily' أو 'weekly' أو 'monthly' للتحكم بحجم الخط.
    """
    from PIL import Image, ImageDraw, ImageFont

    df = get_data_from_excel(start_date, end_date)
    if df.empty:
        return None, df

    # إعداد الحجم العام
    width = 1600
    row_height = 40
    header_height = 70
    title_height = 80
    footer_height = 60

    # حجم الخط حسب نوع التقرير
    if mode == 'monthly':
        font_size = 16
    elif mode == 'weekly':
        font_size = 18
    else:
        font_size = 20

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
        font_bold = ImageFont.truetype("arial.ttf", font_size + 2)
    except:
        font = ImageFont.load_default()
        font_bold = ImageFont.load_default()

    # الأعمدة المستخدمـة في الصورة
    columns = [
        ('#', 'number'),
        ('التاريخ', 'date'),
        ('وقت الدخول', 'entry_time'),
        ('نسبة الربح %', 'profit_pct'),
        ('مدة الهدف', 'duration'),
        ('النوع', 'type'),
        ('Strike', 'strike'),
        ('سعر الطرح', 'open'),
        ('السعر المحقق', 'close_price'),
        ('الربح بالعقد', 'profit'),
        ('الخسارة بالعقد', 'loss'),
        ('الصافي', 'pnl'),
    ]

    col_count = len(columns)
    col_width = width // col_count

    height = title_height + header_height + (len(df) * row_height) + footer_height

    img = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # عنوان التقرير
    draw.rectangle([0, 0, width, title_height], fill=(15, 15, 15))
    draw.text((20, 20), title, font=font_bold, fill=(255, 255, 255))

    # ترويسة الجدول
    header_top = title_height
    header_bottom = header_top + header_height
    draw.rectangle([0, header_top, width, header_bottom], fill=(25, 25, 25))

    x = 0
    for header_text, col_name in columns:
        draw.text((x + 10, header_top + 20), header_text, font=font_bold, fill=(255, 255, 255))
        x += col_width

    # صفوف البيانات
    start_y = header_bottom
    for _, row in df.iterrows():
        row_top = start_y
        row_bottom = row_top + row_height

        # خلفية الصف بالتناوب
        bg_color = (18, 18, 18) if (_ % 2 == 0) else (25, 25, 25)
        draw.rectangle([0, row_top, width, row_bottom], fill=bg_color)

        x = 0
        for header_text, col_name in columns:
            val = row.get(col_name, "")
            if pd.isna(val):
                val = ""
            if col_name in ['profit', 'loss', 'pnl']:
                try:
                    val_num = float(val)
                    val = f"{val_num:.2f}"
                except:
                    pass
            if col_name == 'profit_pct':
                try:
                    val_num = float(val)
                    val = f"{val_num:.2f}%"
                except:
                    val = ""
            text = str(val)
            draw.text((x + 6, row_top + 10), text, font=font, fill=(230, 230, 230))
            x += col_width

        start_y += row_height

    # تذييل بالإجماليات
    footer_top = height - footer_height
    draw.rectangle([0, footer_top, width, height], fill=(20, 20, 20))

    total_profit = float(df['profit'].sum())
    total_loss = float(df['loss'].sum())
    total_pnl = float(df['pnl'].sum())

    footer_text = f"إجمالي الربح: {total_profit:.2f} | إجمالي الخسارة: {total_loss:.2f} | صافي الربح: {total_pnl:.2f}"
    draw.text((20, footer_top + 15), footer_text, font=font_bold, fill=(255, 255, 255))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read(), df
def send_image_bytes_to_telegram(image_bytes, caption_text, group_type='public'):
    """
    إرسال صورة (bytes) مباشرة إلى مجموعة تليجرام (عامة أو خاصة).
    """
    if group_type == 'public':
        chat_id = PUBLIC_GROUP_ID
        group_name = "العامة"
    elif group_type == 'private':
        chat_id = PRIVATE_GROUP_ID
        group_name = "الخاصة"
    else:
        print("❌ نوع المجموعة غير صحيح في send_image_bytes_to_telegram")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    files = {'photo': ('spx_report.png', io.BytesIO(image_bytes), 'image/png')}
    payload = {
        'chat_id': chat_id,
        'caption': caption_text,
        'parse_mode': 'Markdown'
    }

    try:
        response = requests.post(url, data=payload, files=files, timeout=30)
        response.raise_for_status()
        result = response.json()
        if result.get('ok'):
            print(f"تم إرسال الصورة بنجاح تلقائياً إلى المجموعة {group_name} ({chat_id})")
            return True
        else:
            print("فشل إرسال الصورة تلقائياً:", result)
            return False
    except Exception as e:
        print("خطأ أثناء الإرسال التلقائي لتليجرام:", e)
        return False
    
def send_scheduled_message_to_telegram(text: str, image_token: str, group_type: str):
    """
    إرسال رسالة مجدولة (كنص أو صورة) إلى مجموعة عامة أو خاصة.
    image_token:
      - إما اسم ملف محلي محفوظ في static/scheduled (image_filename)
      - أو رابط صورة خارجي قديم (للتوافق مع الإعدادات القديمة).
    group_type: 'public' أو 'private'
    """
    if group_type == 'public':
        chat_id = PUBLIC_GROUP_ID
    elif group_type == 'private':
        chat_id = PRIVATE_GROUP_ID
    else:
        return

    try:
        if image_token:
            # أولاً نحاول اعتباره ملفاً محلياً
            local_path = os.path.join(SCHEDULED_IMAGES_FOLDER, image_token)
            if os.path.isfile(local_path):
                url = f"https://api.telegram.org/bot{PAYMENT_BOT_TOKEN}/sendPhoto"
                with open(local_path, 'rb') as img_file:
                    files = {'photo': ('scheduled.png', img_file, 'image/png')}
                    data = {
                        'chat_id': chat_id,
                        'caption': text
                    }
                    requests.post(url, data=data, files=files, timeout=15)
            else:
                # إذا لم يكن ملفاً محلياً، نعامله كرابط قديم (توافق)
                url = f"https://api.telegram.org/bot{PAYMENT_BOT_TOKEN}/sendPhoto"
                payload = {
                    'chat_id': chat_id,
                    'photo': image_token,
                    'caption': text
                }
                requests.post(url, json=payload, timeout=15)
        else:
            # إرسال نص فقط
            url = f"https://api.telegram.org/bot{PAYMENT_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': text
            }
            requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print("خطأ أثناء إرسال رسالة مجدولة:", e)

def process_scheduled_messages(now: datetime):
    """
    معالجة الرسائل المجدولة اليومية المتكررة:
    - إذا حان الوقت → تُرسل الرسالة
    - لا تُحذف أبدًا تلقائيًا
    - تستمر في الإرسال كل يوم في نفس الوقت
    """
    settings = get_settings()
    scheduled_messages = settings.get('scheduled_messages', [])
    if not scheduled_messages:
        return

    current_time = now.strftime('%H:%M')  # مثال: "23:59"

    sent_count = 0
    today_key = now.strftime('%Y-%m-%d')
    changed = False
    for msg in scheduled_messages:
        time_str = msg.get('time')
        if not time_str:
            continue

        # إذا الوقت الحالي يطابق وقت الرسالة → نرسلها (ولا نحذفها!)
        if time_str == current_time and msg.get('last_sent_date') != today_key:
            text = (msg.get('text') or '').strip()
            image_token = msg.get('image_filename') or msg.get('image_url') or ''
            groups = _normalize_groups(msg.get('groups') or msg.get('destinations'))
            segments = [s for s in _normalize_multi(msg.get('segments')) if s in _notification_segment_labels()]

            if text and (groups or segments):
                for g in groups:
                    send_scheduled_message_to_telegram(text, image_token, g)
                for chat_id in _notification_recipients(segments):
                    _send_payment_bot_message(chat_id, text, image_token)
                msg['last_sent_date'] = today_key
                changed = True
                sent_count += 1
                print(f"Scheduled notification sent '{msg.get('id')}' to groups={groups}, segments={segments} at {current_time}")

    if sent_count > 0:
        if changed:
            save_settings({'scheduled_messages': scheduled_messages})
        print(f"📅 تم إرسال {sent_count} رسالة/رسائل مجدولة يومية في {current_time}")
def build_period_caption(df, period_label):
    usd_to_sar_rate = 3.75

    total_profit = float(df['profit'].sum())
    total_loss = float(df['loss'].sum())
    total_pnl = float(df['pnl'].sum())

    profit_sar = total_profit * usd_to_sar_rate
    loss_sar = total_loss * usd_to_sar_rate
    pnl_sar = total_pnl * usd_to_sar_rate

    profit_percentage = 0.0
    if total_profit > 0:
        profit_percentage = (total_pnl / total_profit) * 100.0

    caption = f"""
نتائج {period_label} لربوت SPX
أرباح الفترة : {total_profit:.2f} دولار = {profit_sar:.2f} ريال
خسائر الفترة : {abs(total_loss):.2f} دولار = {abs(loss_sar):.2f} ريال
نسبة الربح {profit_percentage:.2f}%
صافي الربح : {total_pnl:.2f} دولار = {pnl_sar:.2f} ريال

للإنضمام اضغط هنا
@Spxinfobot
""".strip()

    return caption



@app.route('/send_telegram', methods=['POST'])
def send_telegram():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    temp_path = None
    try:
        if 'image' not in request.files:
            return jsonify({'status': 'error', 'message': 'لا يوجد ملف صورة'}), 400
            
        file = request.files['image']
        group_type = request.form.get('group_type', 'public')
        
        # استلام البيانات
        total = request.form.get('total', '0')
        wins = request.form.get('wins', '0')
        loss = request.form.get('loss', '0')
        rate = request.form.get('rate', '0%')
        date_range = request.form.get('date_range', 'غير محدد')
        filter_type = request.form.get('filter_type', 'daily')

        # تحديد نوع العنوان
        type_title = ""
        if filter_type == 'daily':
            type_title = "اليومي"
        elif filter_type == 'weekly':
            type_title = "الأسبوعي"
        elif filter_type == 'monthly':
            type_title = "الشهري"

        # صياغة النص
        caption = (
            f"📊 تقرير أداء BOT CAMEL SPX {type_title} :\n\n"
            f"📅 الفترة: {date_range}\n\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"📡 إحصائيات التداول\n\n"
            f"📊 إجمالي الصفقات: [ {total} ]\n"
            f"🟢 الصفقات الرابحة: [ {wins} ]\n"
            f"🔴 الصفقات الخاسرة: [ {loss} ]\n"
            f"🎯 نسبة النجاح: [ {rate} ]"
        )

        # عمليات الحفظ والإرسال المعتادة
        filename = f"report_{uuid.uuid4().hex}.jpg"
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_path)
        
        chat_id = PUBLIC_GROUP_ID if group_type == 'public' else PRIVATE_GROUP_ID

        with open(temp_path, 'rb') as f:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            payload = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'}
            files = {'photo': ('report.jpg', f, 'image/jpeg')}
            response = requests.post(url, data=payload, files=files, timeout=60)

        if response.status_code == 200:
            return jsonify({'status': 'ok'})
        else:
            return jsonify({'status': 'error', 'message': response.text})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@app.route('/api/check_update')
def check_update():
    """
    مسار وظيفته التحقق من وقت آخر تعديل لملفات البيانات (CSV و JSON).
    إذا تم إضافة صفقة جديدة سيتغير هذا الوقت.
    """
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # قراءة وقت آخر تعديل لملف CSV
        filters = _trade_filter_args()
        mtimes = []
        for cfg in _trade_file_configs(**filters):
            for path in (cfg.get('csv_path'), cfg.get('json_path')):
                if path and os.path.exists(path):
                    mtimes.append(os.path.getmtime(path))
        if mtimes:
            return jsonify({'last_update': max(mtimes)})

        csv_mtime = os.path.getmtime(DATA_FILE_PATH) if os.path.exists(DATA_FILE_PATH) else 0
        # قراءة وقت آخر تعديل لملف JSON
        json_mtime = os.path.getmtime(JSON_FILE_PATH) if os.path.exists(JSON_FILE_PATH) else 0
        
        # نأخذ أحدث وقت بينهما
        latest_mtime = max(csv_mtime, json_mtime)
        
        return jsonify({'last_update': latest_mtime})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/update_subscription', methods=['POST'])
def update_subscription():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        new_package_id = data.get('package_id')

        if not chat_id or not new_package_id:
            return jsonify({'status': 'error', 'message': 'Missing data'}), 400

        # جلب تفاصيل الباقة الجديدة من الإعدادات
        settings = get_settings()
        package = next((p for p in settings.get('packages', []) if p.get('id') == new_package_id), None)
        if not package:
            return jsonify({'status': 'error', 'message': 'Package not found'}), 404

        # حساب تاريخ الانتهاء الجديد (من اليوم + مدة الباقة الجديدة)
        duration_days = int(package['duration_days'])
        new_subscription_end = datetime.now() + timedelta(days=duration_days)

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET 
                subscription_package = ?, 
                subscription_end = ?,
                paid = 1,
                is_frozen = 0, -- إعادة تفعيل الاشتراك عند تغييره
                frozen_days_remaining = NULL
            WHERE chat_id = ?
        """, (package['name'], new_subscription_end.isoformat(), chat_id))
        
        conn.commit()
        conn.close()

        flash('تم تحديث اشتراك العميل بنجاح!')
        return jsonify({'status': 'ok'})

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500
from flask import send_from_directory

@app.route('/.well-known/acme-challenge/<path:filename>')
def acme_challenge(filename):
    return send_from_directory(r'C:\wacs-validation\.well-known\acme-challenge', filename)

# أضف هذا في app.py (في أي مكان بعد تعريف app)
# أضف مفتاح API سري في أعلى الملف (مع المتغيرات الأخرى)
BOT_API_KEY = os.getenv('BOT_API_KEY', '')

@app.route('/api/packages')
def get_packages_api():
    provided_key = request.headers.get('X-Bot-API-Key')

    if provided_key != BOT_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401

    settings = get_settings()
    packages = settings.get('packages', [])

    # لا نخفي أي حقل؛ نعيد كل بيانات الباقة للبوت
    return jsonify(packages)

import hmac
import hashlib

# 🔴 ضع هنا الـ Secret Key الخاص بالويب هوك من لوحة تحكم StreamPay
STREAMPAY_WEBHOOK_SECRET = "hasonazx12@H" 

def verify_webhook_signature(secret: str, raw_body: bytes, signature_header: str):
    """دالة للتحقق من أن الطلب قادم فعلاً من منصة StreamPay بناءً على الدوكمنتيشن"""
    if not signature_header or not secret:
        return False
    try:
        parts = dict(x.split('=') for x in signature_header.split(','))
        timestamp = parts.get('t')
        signature = parts.get('v1')
        if not timestamp or not signature:
            return False
        message = f"{timestamp}.{raw_body.decode('utf-8')}"
        computed = hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, signature)
    except Exception as e:
        print("Signature Error:", e)
        return False

# تغيير المسار ليصبح /webhook فقط
# أضفنا strict_slashes=False لكي يقبل /webhook أو /webhook/ بدون مشاكل
# أضفنا GET مؤقتاً لكي تطمئن أنه يعمل عندما تفتحه من المتصفح
# 🌟 التوكن الخاص ببوت الاشتراكات (يُستخدم فقط داخل هذه الدالة)
# 🌟 التوكن الخاص ببوت الاشتراكات (يُستخدم فقط داخل الويب هوك)
# 🌟 التوكن الخاص ببوت الاشتراكات (يُستخدم فقط داخل الويب هوك)
PAYMENT_BOT_TOKEN = os.getenv('PAYMENT_BOT_TOKEN', '')

# 🌟 دالة مساعدة لتحويل التاريخ إلى الأشهر العربية
def get_arabic_date(iso_date_str):
    try:
        dt = datetime.fromisoformat(iso_date_str)
        months =['', 'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
        return f"{dt.day} {months[dt.month]} {dt.year}"
    except:
        return iso_date_str.split('T')[0]

import hmac
import hashlib
import time
from datetime import datetime, timedelta
import traceback
import sqlite3
from flask import request, jsonify

# ==========================================
# إعدادات ويب هوك سلة وبوت التفعيل
# ==========================================
SALLA_WEBHOOK_SECRET = "8a6e38ff2f4b7f9dcafbdc8c05bff964af468231b6966e6e4526617f43b3de2b"
PAYMENT_BOT_TOKEN = os.getenv('PAYMENT_BOT_TOKEN', '')

def verify_salla_signature(request_body: bytes, headers) -> bool:
    """التحقق من صحة التوقيع الأمني القادم من سلة."""

    # استخراج التوقيع من الهيدرز
    signature = (
        headers.get('x-salla-signature')
        or headers.get('X-Salla-Signature')
        or headers.get('Authorization')
        or ''
    )

    signature = str(signature).strip()
    webhook_secret = str(SALLA_WEBHOOK_SECRET or '').strip()

    if not signature:
        print("❌ خطأ: لم يصل توقيع من سلة.")
        return False

    if not webhook_secret:
        print("❌ خطأ: متغير SALLA_WEBHOOK_SECRET غير موجود أو فارغ.")
        return False

    # في حال كانت سلة ترسل المفتاح السري نفسه مباشرة
    if hmac.compare_digest(signature, webhook_secret):
        print("✅ التوقيع آمن: تمت المطابقة المباشرة للمفتاح.")
        return True

    # في حال وصول Authorization بصيغة Bearer
    if signature.lower().startswith('bearer '):
        signature = signature[7:].strip()

        if hmac.compare_digest(signature, webhook_secret):
            print("✅ التوقيع آمن: تمت المطابقة عبر Authorization Bearer.")
            return True

    # التحقق القياسي باستخدام HMAC SHA256
    try:
        secret_bytes = webhook_secret.encode('utf-8')

        computed_hex_signature = hmac.new(
            secret_bytes,
            request_body,
            hashlib.sha256
        ).hexdigest()

        # بعض الأنظمة ترسل التوقيع بصيغة hex
        if hmac.compare_digest(
            computed_hex_signature.lower(),
            signature.lower()
        ):
            print("✅ التوقيع آمن: تم التحقق باستخدام HMAC SHA256 HEX.")
            return True

        # بعض الأنظمة ترسل التوقيع بصيغة Base64
        computed_base64_signature = base64.b64encode(
            hmac.new(
                secret_bytes,
                request_body,
                hashlib.sha256
            ).digest()
        ).decode('utf-8')

        if hmac.compare_digest(computed_base64_signature, signature):
            print("✅ التوقيع آمن: تم التحقق باستخدام HMAC SHA256 Base64.")
            return True

        print("❌ التوقيع غير مطابق.")
        print(f"التوقيع المستلم: {signature[:25]}...")
        return False

    except Exception as e:
        print(f"❌ Salla Signature Error: {e}")
        return False


@app.route('/webhook', methods=['POST', 'GET'], strict_slashes=False)
def salla_webhook():
    if request.method == 'GET':
        return (
            "✅ الويب هوك الخاص بسلة يعمل بنجاح ومستعد لاستقبال الطلبات!",
            200
        )

    conn = None

    try:
        # ============================================================
        # 1. قراءة البيانات الخام والتحقق من توقيع سلة
        # ============================================================

        raw_body = request.get_data(cache=True)

        # التعديل المهم:
        # نرسل request.headers بالكامل وليس متغير signature النصي
        if not verify_salla_signature(raw_body, request.headers):
            print("❌ Salla Webhook: توقيع غير صالح، محاولة غير مصرح بها.")

            return jsonify({
                'status': 'error',
                'message': 'Unauthorized'
            }), 401

        # قراءة JSON بعد الاحتفاظ بالبيانات الخام
        payload = request.get_json(silent=True) or {}

        if not isinstance(payload, dict):
            print("❌ البيانات القادمة من سلة ليست JSON صالحًا.")

            return jsonify({
                'status': 'error',
                'message': 'Invalid JSON payload'
            }), 400

        event_name = str(payload.get('event', '')).strip()

        print(f"\n🛒 [SALLA WEBHOOK] حدث جديد وصل: {event_name}")

        # ============================================================
        # 2. فلترة الأحداث
        # ============================================================

        allowed_events = (
            'order.created',
            'order.updated',
            'order.status.updated'
        )

        if event_name not in allowed_events:
            print(f"⚠️ تم تجاهل الحدث غير المطلوب: {event_name}")

            return jsonify({
                'status': 'ignored',
                'message': 'Not an order event'
            }), 200

        # ============================================================
        # 3. توحيد مكان استخراج بيانات الطلب
        # ============================================================

        payload_data = payload.get('data', {})

        if not isinstance(payload_data, dict):
            payload_data = {}

        if event_name == 'order.status.updated':
            order_data = payload_data.get('order', {})
        else:
            order_data = payload_data

        if not isinstance(order_data, dict):
            order_data = {}

        if not order_data:
            print("❌ لم يتم العثور على بيانات الطلب داخل الويب هوك.")

            return jsonify({
                'status': 'ignored',
                'message': 'Order data not found'
            }), 200

        # ============================================================
        # 4. التأكد من حالة الدفع
        # ============================================================

        status_data = order_data.get('status', {})

        if not isinstance(status_data, dict):
            status_data = {}

        status_slug = str(
            status_data.get('slug', '')
        ).strip().lower()

        payment_status_data = order_data.get('payment_status', '')

        if isinstance(payment_status_data, dict):
            payment_status = str(
                payment_status_data.get('slug')
                or payment_status_data.get('status')
                or payment_status_data.get('name')
                or ''
            ).strip().lower()
        else:
            payment_status = str(
                payment_status_data or ''
            ).strip().lower()

        completed_statuses = (
            'completed',
            'delivering',
            'delivered'
        )

        if status_slug not in completed_statuses:
            if payment_status != 'paid':
                print(
                    "⚠️ الطلب لم يكتمل أو لم يُدفع بعد. "
                    f"حالة الطلب: {status_slug} | "
                    f"حالة الدفع: {payment_status}"
                )

                return jsonify({
                    'status': 'ignored',
                    'message': 'Not paid yet'
                }), 200

        # ============================================================
        # 5. استخراج بيانات العميل والطلب
        # ============================================================

        order_id = str(order_data.get('id', '')).strip()

        if not order_id:
            print("❌ رقم الطلب غير موجود.")

            return jsonify({
                'status': 'ignored',
                'message': 'Order ID not found'
            }), 200

        amounts_data = order_data.get('amounts', {})

        if not isinstance(amounts_data, dict):
            amounts_data = {}

        total_data = amounts_data.get('total', {})

        if isinstance(total_data, dict):
            raw_order_amount = total_data.get('amount', 0)
        else:
            raw_order_amount = total_data

        try:
            order_amount = float(raw_order_amount or 0)
        except (TypeError, ValueError):
            order_amount = 0.0

        customer = order_data.get('customer', {})

        if not isinstance(customer, dict):
            customer = {}

        mobile_code = str(
            customer.get('mobile_code', '')
        ).replace('+', '').strip()

        mobile = str(
            customer.get('mobile', '')
        ).replace(' ', '').strip()

        if mobile.startswith('+') or mobile.startswith('966'):
            customer_phone = mobile
        else:
            customer_phone = mobile_code + mobile

        customer_name = (
            f"{customer.get('first_name', '')} "
            f"{customer.get('last_name', '')}"
        ).strip()

        normalized_phone = normalize_phone(customer_phone)

        print(
            f"📦 بيانات الطلب | "
            f"رقم الطلب: {order_id} | "
            f"العميل: {customer_name} | "
            f"الجوال: {normalized_phone} | "
            f"المبلغ: {order_amount}"
        )

        if not normalized_phone:
            print("❌ رقم جوال العميل غير موجود أو غير صالح.")

            return jsonify({
                'status': 'ignored',
                'message': 'Customer phone not found'
            }), 200

        # ============================================================
        # 6. استخراج اسم المنتج أو الباقة
        # ============================================================

        items = order_data.get('items', [])

        if not isinstance(items, list) or not items:
            print("⚠️ الطلب لا يحتوي على منتجات.")

            return jsonify({
                'status': 'ignored',
                'message': 'No items'
            }), 200

        first_item = items[0]

        if not isinstance(first_item, dict):
            first_item = {}

        product_name = str(
            first_item.get('name', 'باقة اشتراك')
        ).strip() or 'باقة اشتراك'

        print(
            f"✅ طلب مدفوع في سلة | "
            f"الطلب: {order_id} | "
            f"الجوال: {normalized_phone} | "
            f"المبلغ: {order_amount} | "
            f"المنتج: {product_name}"
        )

        # ============================================================
        # 7. الاتصال بقاعدة البيانات
        # ============================================================

        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.row_factory = sqlite3.Row

        c = conn.cursor()

        # التأكد من وجود الأعمدة المطلوبة
        ensure_column(
            c,
            "users",
            "salla_order_id",
            "TEXT"
        )

        ensure_column(
            c,
            "users",
            "referral_reward_preference",
            "TEXT DEFAULT 'days'"
        )

        ensure_column(
            c,
            "users",
            "referral_discount_balance",
            "REAL DEFAULT 0"
        )

        ensure_column(
            c,
            "users",
            "referral_cashout_balance",
            "REAL DEFAULT 0"
        )

        ensure_column(
            c,
            "users",
            "referral_days_earned",
            "INTEGER DEFAULT 0"
        )

        ensure_column(
            c,
            "users",
            "referral_wallet_balance",
            "REAL DEFAULT 0"
        )

        # ============================================================
        # 8. منع تكرار معالجة الطلب
        # ============================================================

        c.execute(
            """
            SELECT chat_id
            FROM users
            WHERE salla_order_id = ?
            LIMIT 1
            """,
            (order_id,)
        )

        existing_order = c.fetchone()

        if existing_order:
            print(
                f"⚠️ الطلب {order_id} من سلة "
                "تم تفعيله مسبقًا."
            )

            conn.close()
            conn = None

            return jsonify({
                'status': 'ignored',
                'message': 'Already processed'
            }), 200

        # ============================================================
        # 9. البحث عن مستخدم البوت برقم الجوال
        # ============================================================

        phone_variants = {
            normalized_phone,
            normalized_phone.lstrip('+')
        }

        normalized_without_country = normalized_phone.lstrip('+')

        if normalized_without_country.startswith('966'):
            local_phone = '0' + normalized_without_country[3:]
            phone_variants.add(local_phone)
            phone_variants.add(normalized_without_country[3:])

        user_row = None

        for phone_variant in phone_variants:
            if not phone_variant:
                continue

            c.execute(
                """
                SELECT *
                FROM users
                WHERE phone_number = ?
                   OR phone_number LIKE ?
                ORDER BY first_seen DESC
                LIMIT 1
                """,
                (
                    phone_variant,
                    f"%{phone_variant}%"
                )
            )

            user_row = c.fetchone()

            if user_row:
                break

        if not user_row:
            print(
                "❌ لم يتم العثور على مستخدم في البوت "
                f"برقم الجوال: {normalized_phone}"
            )

            conn.close()
            conn = None

            return jsonify({
                'status': 'ignored',
                'message': 'User not found in bot'
            }), 200

        # ============================================================
        # 10. قراءة بيانات المستخدم
        # ============================================================

        chat_id = user_row['chat_id']
        current_sub_end_str = user_row['subscription_end']
        was_paid_before = int(user_row['paid'] or 0)

        existing_referrer = user_row['referred_by_code']

        if 'referral_discount_balance' in user_row.keys():
            discount_balance = float(
                user_row['referral_discount_balance'] or 0
            )
        else:
            discount_balance = 0.0

        if was_paid_before and discount_balance > 0:
            discount_used = min(
                discount_balance,
                order_amount
            )
        else:
            discount_used = 0.0

        # ============================================================
        # 11. تحديد مدة الباقة
        # ============================================================

        settings = get_settings() or {}
        packages = settings.get('packages', [])

        if not isinstance(packages, list):
            packages = []

        duration_days = 30
        matched_package_name = product_name

        for pkg in packages:
            if not isinstance(pkg, dict):
                continue

            try:
                pkg_price = float(pkg.get('price', 0) or 0)
            except (TypeError, ValueError):
                pkg_price = 0.0

            # هامش بسيط بسبب الضرائب أو فروق الكسور
            if abs(pkg_price - order_amount) < 5:
                try:
                    duration_days = int(
                        pkg.get('duration_days', 30) or 30
                    )
                except (TypeError, ValueError):
                    duration_days = 30

                matched_package_name = str(
                    pkg.get('name', product_name)
                ).strip() or product_name

                break

        # ============================================================
        # 12. حساب تاريخ انتهاء الاشتراك
        # ============================================================

        now_time = datetime.now()
        base_date = now_time

        if current_sub_end_str and was_paid_before == 1:
            try:
                current_end_dt = datetime.fromisoformat(
                    str(current_sub_end_str)
                )

                if current_end_dt > now_time:
                    base_date = current_end_dt

            except (TypeError, ValueError):
                print(
                    "⚠️ تعذر قراءة تاريخ الاشتراك الحالي، "
                    "سيبدأ التجديد من الوقت الحالي."
                )

        new_subscription_end = (
            base_date + timedelta(days=duration_days)
        )

        # ============================================================
        # 13. تجهيز كود الإحالة وبيانات لوحة العميل
        # ============================================================

        my_referral_code = user_row['referral_code']

        if not my_referral_code:
            my_referral_code = generate_unique_referral_code(c)

        client_username = user_row['client_username']
        client_password = user_row['client_password']

        if not client_username or not client_password:
            generated_username, generated_password = (
                generate_client_credentials(c, chat_id)
            )

            if not client_username:
                client_username = generated_username

            if not client_password:
                client_password = generated_password

        # ============================================================
        # 14. تحديث بيانات العميل
        # ============================================================

        c.execute(
            """
            UPDATE users
            SET
                name = COALESCE(NULLIF(?, ''), name),
                paid = 1,
                subscription_package = ?,
                subscription_end = ?,
                total_paid_amount =
                    COALESCE(total_paid_amount, 0) + ?,
                referral_discount_balance =
                    MAX(
                        COALESCE(
                            referral_discount_balance,
                            0
                        ) - ?,
                        0
                    ),
                referral_code = ?,
                is_frozen = 0,
                frozen_days_remaining = NULL,
                salla_order_id = ?,
                client_username =
                    COALESCE(client_username, ?),
                client_password =
                    COALESCE(client_password, ?)
            WHERE chat_id = ?
            """,
            (
                customer_name,
                matched_package_name,
                new_subscription_end.isoformat(),
                order_amount,
                discount_used,
                my_referral_code,
                order_id,
                client_username,
                client_password,
                chat_id
            )
        )

        if c.rowcount == 0:
            raise RuntimeError(
                f"لم يتم تحديث المستخدم ذي chat_id={chat_id}"
            )

        # ============================================================
        # 15. تطبيق مكافأة الإحالة
        # ============================================================

        reward_result = None

        if existing_referrer:
            try:
                reward_result = _apply_referral_reward(
                    c,
                    existing_referrer,
                    customer_name,
                    was_paid_before,
                    settings,
                    matched_package_name
                )

                if reward_result:
                    reward_labels = {
                        'cashout': 'كاش أوت',
                        'discount': 'خصم على التجديد',
                        'days': 'أيام إضافية'
                    }

                    try:
                        requests.post(
                            (
                                "https://api.telegram.org/"
                                f"bot{PAYMENT_BOT_TOKEN}/sendMessage"
                            ),
                            json={
                                'chat_id': reward_result['chat_id'],
                                'text': (
                                    "🎉 <b>مكافأة إحالة ناجحة!</b>\n\n"
                                    "اشترك عميل باستخدام كودك.\n"
                                    "نوع المكافأة: "
                                    f"<b>{reward_labels.get(reward_result['type'], reward_result['type'])}</b>\n"
                                    "القيمة: "
                                    f"<b>{reward_result['value']} "
                                    f"{reward_result['unit']}</b>"
                                ),
                                'parse_mode': 'HTML'
                            },
                            timeout=10
                        )

                    except Exception as telegram_reward_error:
                        print(
                            "⚠️ تعذر إرسال إشعار مكافأة الإحالة: "
                            f"{telegram_reward_error}"
                        )

                    if reward_result.get('type') == 'cashout':
                        c.execute(
                            """
                            SELECT *
                            FROM users
                            WHERE chat_id = ?
                            """,
                            (reward_result['chat_id'],)
                        )

                        ref_user = c.fetchone()

                        if ref_user:
                            new_cashout_balance = float(
                                ref_user[
                                    'referral_cashout_balance'
                                ] or 0
                            )

                            _sync_cashout_withdrawal(
                                settings,
                                ref_user,
                                new_cashout_balance
                            )

                            save_settings({
                                'withdrawals': settings.get(
                                    'withdrawals',
                                    []
                                )
                            })

            except Exception as referral_error:
                # لا نوقف تفعيل العميل بسبب خطأ في الإحالة
                print(
                    "⚠️ حدث خطأ أثناء تطبيق الإحالة: "
                    f"{referral_error}"
                )

        # حفظ تفعيل الاشتراك في قاعدة البيانات
        conn.commit()
        conn.close()
        conn = None

        # ============================================================
        # 16. إنشاء رابط القناة الخاص
        # ============================================================

        invite_link = None

        try:
            invite_url = (
                "https://api.telegram.org/"
                f"bot{PAYMENT_BOT_TOKEN}/createChatInviteLink"
            )

            invite_payload = {
                'chat_id': PRIVATE_GROUP_ID,
                'expire_date': int(time.time()) + 300,
                'member_limit': 1
            }

            invite_response = requests.post(
                invite_url,
                json=invite_payload,
                timeout=10
            )

            invite_response.raise_for_status()
            invite_result = invite_response.json()

            if invite_result.get('ok'):
                invite_link = (
                    invite_result
                    .get('result', {})
                    .get('invite_link')
                )
            else:
                print(
                    "❌ تعذر إنشاء رابط الدعوة: "
                    f"{invite_result}"
                )

        except Exception as invite_error:
            print(
                "❌ خطأ في إنشاء رابط القناة: "
                f"{invite_error}"
            )

        # ============================================================
        # 17. إنشاء رسالة نجاح الدفع
        # ============================================================

        success_msg = (
            "🎉 <b>تم تأكيد الدفع وتفعيل اشتراكك "
            "بنجاح!</b>\n\n"
            f"✨ الباقة: <b>{matched_package_name}</b>\n"
            "📅 تاريخ الانتهاء: "
            f"<b>{new_subscription_end.strftime('%Y-%m-%d %H:%M')}</b>\n"
            "🎟 كود الدعوة الخاص بك: "
            f"<code>{my_referral_code}</code>\n\n"
        )

        if discount_used > 0:
            success_msg += (
                "🟡 تم استخدام رصيد خصم إحالة بقيمة "
                f"<b>{discount_used:.2f} ر.س</b> "
                "على هذا التجديد.\n\n"
            )

        if invite_link:
            success_msg += (
                f'🔗 <a href="{invite_link}">'
                "اضغط هنا للدخول إلى القناة فورًا"
                "</a>\n"
                "⚠️ <b>تنبيه:</b> الرابط صالح لمرة واحدة "
                "ولمدة قصيرة، ادخل الآن!"
            )
        else:
            success_msg += (
                "⚠️ <i>حدث خطأ في توليد رابط القناة، "
                "يرجى التواصل مع الدعم الفني.</i>"
            )

        client_panel_url = f"{PUBLIC_SITE_URL}/login"

        success_msg += (
            "\n\n💻 <b>بيانات دخول لوحة التحكم "
            "الخاصة بك:</b>\n"
            f"الرابط: <code>{client_panel_url}</code>\n"
            f"اسم المستخدم: <code>{client_username}</code>\n"
            f"كلمة المرور: <code>{client_password}</code>\n"
            f"كود الإحالة: <code>{my_referral_code}</code>"
        )

        # ============================================================
        # 18. إرسال رسالة التفعيل للعميل
        # ============================================================

        try:
            telegram_response = requests.post(
                (
                    "https://api.telegram.org/"
                    f"bot{PAYMENT_BOT_TOKEN}/sendMessage"
                ),
                json={
                    'chat_id': chat_id,
                    'text': (
                        success_msg
                        + "\n\nاختر طريقة مكافآت الإحالة "
                          "التي تفضلها للكود الخاص بك:"
                    ),
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': True,
                    'reply_markup': {
                        'inline_keyboard': [
                            [
                                {
                                    'text': 'كاش أوت عند الإحالة',
                                    'callback_data':
                                        'ref_reward_cashout'
                                }
                            ],
                            [
                                {
                                    'text': 'خصم عند التجديد',
                                    'callback_data':
                                        'ref_reward_discount'
                                }
                            ],
                            [
                                {
                                    'text': 'أيام إضافية',
                                    'callback_data':
                                        'ref_reward_days'
                                }
                            ]
                        ]
                    }
                },
                timeout=15
            )

            telegram_result = telegram_response.json()

            if not telegram_result.get('ok'):
                print(
                    "⚠️ تم تفعيل الاشتراك ولكن تعذر إرسال "
                    f"رسالة تيليجرام: {telegram_result}"
                )

        except Exception as telegram_error:
            print(
                "⚠️ تم تفعيل الاشتراك ولكن حدث خطأ "
                "أثناء إرسال رسالة تيليجرام: "
                f"{telegram_error}"
            )

        print(
            f"✅ [SUCCESS] تم تفعيل العميل {chat_id} "
            f"بنجاح عبر سلة، الطلب: {order_id}"
        )

        return jsonify({
            'status': 'success',
            'order_id': order_id
        }), 200

    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass

        print(
            "❌ Salla Webhook Error:\n"
            f"{traceback.format_exc()}"
        )

        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
def scheduler_loop():
    """
    حلقة بسيطة تفحص كل دقيقة بتوقيت السعودية (Asia/Riyadh):
    - فقط: فحص الرسائل المجدولة وإرسالها وقتها
    """
    ksa_tz = ZoneInfo("Asia/Riyadh")

    while True:
        try:
            # الوقت الحالي في السعودية
            now_ksa = datetime.now(ksa_tz)

            # معالجة الرسائل المجدولة باستخدام توقيت السعودية
            process_scheduled_messages(now_ksa)

        except Exception as e:
            print("❌ خطأ في حلقة الجدولة:", e)
            traceback.print_exc()

        # فحص كل 60 ثانية
        time.sleep(60)
@app.route('/api/indicator_packages')
def get_indicator_packages_api():
    provided_key = request.headers.get('X-Bot-API-Key')
    if provided_key != BOT_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    settings = get_settings()
    return jsonify(settings.get('indicator_packages', []))

@app.route('/settings/indicator_packages', methods=['POST'])
def manage_indicator_packages():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    action = data.get('action')
    package = data.get('package')
    
    settings = get_settings()
    if 'indicator_packages' not in settings:
        settings['indicator_packages'] = []

    if action == 'add':
        if 'id' not in package:
            package['id'] = str(uuid.uuid4())
        settings['indicator_packages'].append(package)

    elif action == 'update':
        package_id = package.get('id')
        for i, p in enumerate(settings['indicator_packages']):
            if p.get('id') == package_id:
                settings['indicator_packages'][i] = package
                break

    elif action == 'delete':
        package_id = package.get('id')
        settings['indicator_packages'] = [p for p in settings['indicator_packages'] if p.get('id') != package_id]

    save_settings(settings)
    return jsonify({'status': 'ok', 'packages': settings['indicator_packages']})


@app.route('/indicator_clients')
def indicator_clients_page():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        # قاعدة بيانات المؤشر المنفصلة
        conn = sqlite3.connect(os.path.join(BASE_DIR, 'indicator_users.db'))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # الإحصائيات
        cursor.execute("SELECT COUNT(chat_id) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(package_price) FROM users WHERE paid = 1")
        total_revenue = cursor.fetchone()[0] or 0.0
        
        cursor.execute("""
            SELECT chat_id, name, username, phone_number, tradingview_username,
                   paid, subscription_package, subscription_end, package_price
            FROM users ORDER BY first_seen DESC
        """)
        clients = cursor.fetchall()
        conn.close()

        active_subscribers = 0
        clients_data = []
        for client in clients:
            client_dict = dict(client)
            sub_end_str = client_dict.get('subscription_end')
            is_active = False
            if sub_end_str:
                try:
                    sub_end_dt = datetime.fromisoformat(sub_end_str)
                    client_dict['subscription_end_formatted'] = sub_end_dt.strftime('%Y-%m-%d %H:%M')
                    if datetime.now() < sub_end_dt:
                        is_active = True
                        active_subscribers += 1
                except:
                    client_dict['subscription_end_formatted'] = "تاريخ غير صالح"
            else:
                client_dict['subscription_end_formatted'] = "لا يوجد"
            
            client_dict['is_active'] = is_active
            clients_data.append(client_dict)

        stats = {
            'total_users': total_users,
            'total_revenue': total_revenue,
            'active_subscribers': active_subscribers,
            'inactive_users': total_users - active_subscribers
        }

        return render_template('indicator_clients.html', clients=clients_data, stats=stats)
    
    except Exception as e:
        print(traceback.format_exc())
        return f"<h1>خطأ في عرض عملاء المؤشر:</h1><p>{e}</p>", 500


def start_scheduler():
    """
    تشغيل حلقة الرسائل المجدولة (يومي/أسبوعي/شهري)
    """
    th = threading.Thread(target=scheduler_loop, daemon=True)
    th.start()
    print("✅ تم تشغيل حلقة الجدولة التلقائية (يومي/أسبوعي/شهري).")


if __name__ == '__main__':
    # تشغيل حلقة الرسائل المجدولة
    start_scheduler()

    # تشغيل فاحص انتهاء الاشتراكات وطرد المستخدمين

    # تشغيل السيرفر Flask
    print("🚀 تشغيل الداش بورد على http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)      
