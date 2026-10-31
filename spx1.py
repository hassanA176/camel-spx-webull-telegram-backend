import asyncio
import os
import telegram
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import re
import json
import calendar
from datetime import datetime, timedelta
from apscheduler.jobstores.base import JobLookupError
import threading
import logging
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import copy
from typing import Any
import math
import io
import csv
from datetime import datetime, time
import pandas as pd
import httpx
import uuid
import requests
import json
from datetime import time # تأكد من وجودها، قد تكون موجودة بالفعل
import asyncio
# Telegram bot token
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# Font path for image generation
FONT_PATH = r'C:\Windows\Fonts\arialbd.ttf'          # للأرقام والإنجليزي (عادةً يشتغل كويس)
ARABIC_FONT_PATH = r'C:\Windows\Fonts\arialbd.ttf'   # ← نفس الخط حاليًا، لكن الأفضل تغييره
BELL_ICON_PATH = r'C:\Users\Administrator\Desktop\talal\aiease_1760178893454.jpg'
SQUARE_ICON_PATH = r'C:\Users\Administrator\Desktop\talal\saka.png'
csv_lock = asyncio.Lock()
# Group ID (replace with your actual group ID)
PUBLIC_GROUP_ID = os.getenv('TELEGRAM_PUBLIC_GROUP_ID', '')
PRIVATE_GROUP_ID = os.getenv('TELEGRAM_PRIVATE_GROUP_ID', '')

TRADES_JSON = 'trades.json'
TRADES_CSV = 'trades.csv'
CSV_FIELDNAMES = ['Number', 'Date', 'Type Contract', 'SPX Strike', 'Open', 'High', 'السعر المحقق', 'الربح بالعقد', 'الخسارة بالعقد', 'مدة التحقيق']

CSV_FILE = "trades.csv"

# =========================
# Webull HTTP API Helpers
# =========================
# ==========================================
# متغيرات الشركات الجديدة
# ==========================================
COMPANIES_TICKERS = {
    "NVDA": 913257561,  # استبدل الأرقام بالتيكر ID الخاص بك لكل شركة
    "MSTR": 913323987,
    "TSLA": 913255598,
    "AVGO": 913256091,
    "META": 913303928,
    "AAPL": 913256135,
    "SMCI": 913257435,
    "GOOG": 913303964,
    "MSFT": 913323997
}

COMPANY_TRADES_JSON = 'company_trades.json'
COMPANY_TRADES_CSV = 'company_trades.csv'
COMPANY_CSV_FIELDNAMES = ['Ticker', 'Number', 'Date', 'Type Contract', 'Strike', 'Open', 'High', 'السعر المحقق', 'الربح بالعقد', 'الخسارة بالعقد', 'مدة التحقيق']
COOKIES_FILE = "cookies.json"
# مسارات خلفيات SPX (موجودة عندك مسبقاً)
# ==========================================
# متغيرات المؤشرات الجديدة وصورها وملفاتها
# ==========================================
# يرجى التأكد من وضع التيكر ID الصحيح لكل مؤشر من Webull
TICKER_ID_SPX = 913354362
INDICES_TICKERS = {
    "SPX": 913354362,
    "SPY": 913243251,  # استبدل برقم SPY الصحيح
    "QQQ": 913243249,  # استبدل برقم QQQ الصحيح
    "NDX": 913354088   # استبدل برقم NDX الصحيح
}

# الجذور الصحيحة للعقود اليومية (0DTE) في Webull
# SPX و NDX لديهم رموز خاصة للعقود اليومية (SPXW و NDXP)
INDEX_ROOT_SYMBOLS = {
    "SPX": "SPXW",
    "NDX": "NDXP",
    "SPY": "SPY",
    "QQQ": "QQQ"
}

# مسارات الملفات لكل مؤشر
INDICES_FILES = {
    "SPX": {"csv": "trades.csv", "json": "trades.json"},
    "SPY": {"csv": "spy_trades.csv", "json": "spy_trades.json"},
    "QQQ": {"csv": "qqq_trades.csv", "json": "qqq_trades.json"},
    "NDX": {"csv": "ndx_trades.csv", "json": "ndx_trades.json"}
}

# مسارات الصور لكل مؤشر
INDICES_BACKGROUNDS = {
    "SPX": {
        "normal": r'C:\Users\Administrator\Desktop\talal\camel_spx_normal.png',
        "right":  r'C:\Users\Administrator\Desktop\talal\camel_spx_with_right_.png'
    },
    "SPY": {
        "normal": r'C:\Users\Administrator\Desktop\talal\camel_spx_normal.png', # مسار صورة SPY
        "right":  r'C:\Users\Administrator\Desktop\talal\camel_spx_with_right_.png'
    },
    "QQQ": {
        "normal": r'C:\Users\Administrator\Desktop\talal\camel_spx_normal.png', # مسار صورة QQQ
        "right":  r'C:\Users\Administrator\Desktop\talal\camel_spx_with_right_.png'
    },
    "NDX": {
        "normal": r'C:\Users\Administrator\Desktop\talal\camel_spx_normal.png', # مسار صورة NDX
        "right":  r'C:\Users\Administrator\Desktop\talal\camel_spx_with_right_.png'
    }
}
# مسارات خلفيات الشركات الموحدة (قم بتعديلها لمسارات الصور الجديدة)
COMPANY_NORMAL_BG = r'C:\Users\Administrator\Desktop\talal\camel_spx_normal.png'
COMPANY_RIGHT_BG  = r'C:\Users\Administrator\Desktop\talal\camel_spx_with_right_.png'
STRATEGY_LIST_HEADERS = {
    "appid": "wb_web_app",
    "sec-ch-ua-platform": "\"Windows\"",
    "device-type": "Web",
    "hl": "en",
    "x-sv": os.getenv("WEBULL_X_SV", ""),
    "sec-ch-ua": "\"Chromium\";v=\"141\", \"Not?A_Brand\";v=\"8\"",
    "sec-ch-ua-mobile": "?0",
    "app": "global",
    "t_time": os.getenv("WEBULL_T_TIME", ""),
    "content-type": "application/json;charset=UTF-8",
    "x-s": os.getenv("WEBULL_X_S", ""),
    "os": "web",
    "platform": "web",
    "referer": "https://app.webull.com/",
    "tz": "America/Los_Angeles",
    "osv": "i9zh",
    "reqid": os.getenv("WEBULL_REQ_ID", ""),
    "did": os.getenv("WEBULL_DEVICE_ID", ""),
    "ph": "Windows Chrome",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36"
    ),
    "ver": "6.5.1",
    "app-group": "broker",
    "access_token": os.getenv("WEBULL_ACCESS_TOKEN", ""),
}

STRATEGY_LIST_PAYLOAD = {
    "expireCycle": [3, 2, 4],
    "type": 0,
    "quoteMultiplier": 100,
    "count": -1,
    "direction": "all",

}


def format_signed_change(val: Any, decimals: int = 2) -> str:
    v = safe_float(val)
    # NaN أو عدم وجود قيمة → 0
    if math.isnan(v):
        v = 0.0
    return f"{v:+.{decimals}f}"  # يعطي +0.25 أو -0.25


def format_signed_change_perc_from_ratio(ratio_val: Any, decimals: int = 2) -> str:
    """
    ratio_val هو changeRatio القادم من Webull (مثل -0.7143)
    نضربه في 100 ونضيف + أو - ونرجع نص جاهز للاستخدام في الصورة مثل: +12.34%
    """
    r = safe_float(ratio_val)
    if math.isnan(r):
        r = 0.0
    perc = r * 100.0
    return f"{perc:+.{decimals}f}%"

def load_cookies_from_file(path: str = COOKIES_FILE) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    cookies = {}
    if isinstance(data, list):
        for c in data:
            if "name" in c and "value" in c:
                cookies[c["name"]] = c["value"]
    elif isinstance(data, dict) and "cookies" in data and isinstance(data["cookies"], list):
        for c in data["cookies"]:
            if "name" in c and "value" in c:
                cookies[c["name"]] = c["value"]
    return cookies


def make_client() -> httpx.AsyncClient:
    cookies = load_cookies_from_file()
    return httpx.AsyncClient(
        base_url="https://quotes-gw.webullfintech.com",
        headers=STRATEGY_LIST_HEADERS,
        cookies=cookies,
        timeout=20.0,
    )


async def fetch_option_chain(client: httpx.AsyncClient, ticker_id: int = TICKER_ID_SPX) -> dict:
    # أخذ نسخة من القالب الأساسي
    payload = STRATEGY_LIST_PAYLOAD.copy()
    
    # إضافة التيكر المطلوب (سواء كان SPX، أو شركة، أو مؤشر آخر)
    payload["tickerId"] = ticker_id
    
    r = await client.post("/api/quote/option/strategy/list", json=payload)
    r.raise_for_status()
    return r.json()



def get_next_valid_expire_date() -> str:
    """
    ترجع التاريخ المناسب للبحث عن العقود بناءً على وقت الإغلاق في settings.json
    - يستخدم الحقل "schedule_time" الموجود في ملفك
    """
    now = datetime.now(LOCAL_TZ)
    current_date_str = now.strftime("%Y-%m-%d")

    try:
        # قراءة الإعدادات
        settings = {}
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)

        # استخدام schedule_time كوقت الإغلاق اليومي
        close_time_str = settings.get('schedule_time', '23:00')   # مثال: "23:00"

        # تحويل "23:00" إلى ساعة ودقيقة
        hour, minute = map(int, close_time_str.split(':'))
        
        # بناء وقت الإغلاق في اليوم الحالي
        close_time_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if now < close_time_today:
            # لا يزال قبل وقت الإغلاق → استخدم عقود اليوم الحالي
            print(f"[{now.strftime('%H:%M')}] قبل وقت الإغلاق ({close_time_str}) → استخدام عقود يوم {current_date_str}")
            return current_date_str
        else:
            # بعد وقت الإغلاق → انتقل إلى اليوم التالي
            next_day = now + timedelta(days=1)
            next_date = next_day.strftime("%Y-%m-%d")
            print(f"[{now.strftime('%H:%M')}] بعد وقت الإغلاق ({close_time_str}) → الانتقال إلى يوم {next_date}")
            return next_date

    except Exception as e:
        print(f"⚠️ خطأ في حساب التاريخ التالي: {e} → استخدام اليوم الحالي")
        return current_date_str


def get_weekly_expire_date() -> str:
    """
    ترجع تاريخ الجمعة القادمة لعقد weekly.

    القاعدة:
    - من السبت إلى الخميس: أقرب جمعة قادمة.
    - يوم الجمعة نفسه: الجمعة التي بعدها، وليس نفس اليوم.
    """
    now = datetime.now(LOCAL_TZ)

    # 0=الإثنين, 1=الثلاثاء, 2=الأربعاء, 3=الخميس, 4=الجمعة, 5=السبت, 6=الأحد
    days_ahead = 4 - now.weekday()

    # مهم جداً:
    # لو اليوم جمعة days_ahead = 0
    # نريد الجمعة القادمة، لذلك نضيف 7
    if days_ahead <= 0:
        days_ahead += 7

    target_date = now + timedelta(days=days_ahead)
    return target_date.strftime("%Y-%m-%d")


def get_monthly_expire_date() -> str:
    """
    ترجع تاريخ آخر يوم عمل في الشهر الحالي.
    إذا تجاوزنا هذا اليوم، ترجع آخر يوم عمل في الشهر القادم.

    ملاحظة:
    هذا المنطق يعتبر الشهري = آخر يوم عمل في الشهر.
    إذا كنت تقصد monthly options الأمريكية القياسية، فهي غالباً ثالث جمعة من الشهر،
    وليس آخر يوم عمل.
    """
    now = datetime.now(LOCAL_TZ)

    def last_business_day(year: int, month: int):
        last_day = calendar.monthrange(year, month)[1]
        d = datetime(year, month, last_day, tzinfo=LOCAL_TZ)

        # لو السبت نرجع الجمعة
        if d.weekday() == 5:
            d -= timedelta(days=1)

        # لو الأحد نرجع الجمعة
        elif d.weekday() == 6:
            d -= timedelta(days=2)

        return d

    target_date = last_business_day(now.year, now.month)

    # إذا تجاوزنا آخر يوم عمل في الشهر الحالي، نذهب للشهر القادم
    if now.date() > target_date.date():
        if now.month == 12:
            next_year = now.year + 1
            next_month = 1
        else:
            next_year = now.year
            next_month = now.month + 1

        target_date = last_business_day(next_year, next_month)

    return target_date.strftime("%Y-%m-%d")
def find_contract_in_chain(
    chain: dict,
    strike: float,
    direction: str | None = None,
    expire_date: str | None = None,
    use_next_day_after_close: bool = True,
    target_root_symbol: str | None = None
) -> dict | None:
    
    direction = (direction or "").lower()

    if expire_date is None and use_next_day_after_close:
        min_expire = get_next_valid_expire_date()
    else:
        min_expire = expire_date

    # === التعديل الذكي لتخطي إجازات السوق ===
    if expire_date:
        available_dates = []
        for exp_block in chain.get("expireDateList", []):
            dv = exp_block.get("from", {}).get("date") or exp_block.get("expireDate")
            if dv: available_dates.append(dv)
        
        # إذا كان التاريخ المطلوب غير موجود في سلسلة ويبول (بسبب إجازة)
        if expire_date not in available_dates:
            try:
                dt_target = datetime.strptime(expire_date, "%Y-%m-%d")
                # الرجوع للخلف حتى 4 أيام للبحث عن أقرب يوم عمل متاح
                for i in range(1, 5):
                    fallback_date = (dt_target - timedelta(days=i)).strftime("%Y-%m-%d")
                    if fallback_date in available_dates:
                        print(f"⚠️ تاريخ {expire_date} غير متاح في السوق (إجازة)، تم الرجوع تلقائياً إلى {fallback_date}")
                        expire_date = fallback_date
                        min_expire = fallback_date
                        break
            except Exception:
                pass
    # ========================================

    print(f"البحث عن عقد | Strike: {strike} | Direction: {direction} | Expire: {expire_date} | Root: {target_root_symbol}")

    for exp_block in chain.get("expireDateList", []):
        date_val = exp_block.get("from", {}).get("date") or exp_block.get("expireDate")
        if not date_val:
            continue

        if min_expire and date_val < min_expire:
            continue

        if expire_date and date_val != expire_date:
            continue

        for opt in exp_block.get("data", []):
            sp_raw = opt.get("strikePrice") or opt.get("strike")
            if not sp_raw:
                continue

            try:
                sp_val = float(sp_raw)
            except Exception:
                continue

            if abs(sp_val - float(strike)) > 0.01:
                continue

            un_symbol = (opt.get("unSymbol") or opt.get("underlyingSymbol") or opt.get("rootSymbol") or "").upper()
            
            if target_root_symbol and un_symbol != target_root_symbol.upper():
                continue

            if direction:
                dval = (opt.get("direction") or "").lower()
                if direction.startswith("c") and not dval.startswith("c"):
                    continue
                if direction.startswith("p") and not dval.startswith("p"):
                    continue

            ticker_id = opt.get("tickerId") or opt.get("derivativeId")
            if not ticker_id:
                continue

            return {
                "expireDate": date_val,
                "tickerId": ticker_id,
                "direction": opt.get("direction"),
                "strikePrice": sp_raw,
                "unSymbol": un_symbol,
            }
    return None

async def fetch_option_quote(client: httpx.AsyncClient, tid: int) -> dict:
    r = await client.get(
        "/api/quote/option/quotes/queryBatch",
        params={"derivativeIds": str(tid)},
    )
    r.raise_for_status()
    js = r.json()
    
    # تحصين: إذا أرجع Webull قائمة فارغة (عقد منتهي)، نرجع قاموساً فارغاً لكي لا ينهار الكود
    if isinstance(js, list):
        return js[0] if len(js) > 0 else {}
    
    return js if isinstance(js, dict) else {}


def quote_to_popup_data(quote: dict, is_calls: bool, symbol_override: str = "SPXW") -> dict:
    strike_str = str(quote.get("strikePrice", "0"))
    try:
        strike_val = float(strike_str)
    except Exception:
        strike_val = 0.0

    direction_raw = (quote.get("direction") or "").lower()
    direction_text = "Call" if direction_raw.startswith("c") else "Put"

    # 1. إصلاح التاريخ ليعود بصيغة 15 Jun 26
    expire_date = quote.get("expireDate")
    expire_str = ""
    if expire_date:
        try:
            dt_exp = datetime.strptime(expire_date, "%Y-%m-%d")
            expire_str = dt_exp.strftime("%d %b %y")
        except Exception:
            expire_str = expire_date

    # 2. إصلاح الهيدر داخل الصورة ليعود لشكله القديم
    if symbol_override == "SPXW":
        header = f"SPXW ${strike_str} {expire_str}   (w) {direction_text}  100"
    else:
        # للشركات يكون بدون حرف w
        header = f"{symbol_override} ${strike_str} {expire_str}   {direction_text}  100"

    spx_banner = symbol_override

    close = quote.get("close", "0.00")
    change_str = str(quote.get("change", "0.00"))
    change_ratio = quote.get("changeRatio", "0.0")

    if change_str and not change_str.startswith(('+', '-')):
        try:
            v = float(change_str)
            if v > 0:
                change_str = "+" + change_str
        except Exception:
            pass

    try:
        cr = float(change_ratio) * 100.0
        change_perc = f"{cr:+.4f}%"
    except Exception:
        s = str(change_ratio).strip()
        change_perc = s + '%' if s and not s.endswith('%') else s

    trade_time = quote.get("tradeTime")
    tz_name = quote.get("tzName", "EST")
    closed_time = "Open --/-- --:-- " + tz_name
    if trade_time:
        try:
            tt = trade_time.replace("+0000", "+00:00") if "+0000" in trade_time else trade_time
            dt_trade = datetime.fromisoformat(tt)
            closed_time = "Open " + dt_trade.strftime("%m/%d %H:%M ") + tz_name
        except Exception:
            pass

    bid_list = quote.get("bidList") or []
    ask_list = quote.get("askList") or []
    bid_price = safe_float(bid_list[0].get("price")) if bid_list else 0.0
    ask_price = safe_float(ask_list[0].get("price")) if ask_list else 0.0
    mid_val = (bid_price + ask_price) / 2.0 if bid_price > 0 and ask_price > 0 else 0.0

    close_f = safe_float(close, 0.0)
    be_val = strike_val + close_f if direction_text == "Call" else strike_val - close_f

    metrics = {
        "Open": str(quote.get("open", "--")),
        "Mid": f"{mid_val:.2f}",
        "Prev Close": str(quote.get("preClose", "0.00")),
        "High": str(quote.get("high", "--")),
        "Low": str(quote.get("low", "--")),
        "Break Even": f"{be_val:.2f}",
        "Volume": str(quote.get("volume", "0")),
        "Open Int": str(quote.get("openInterest", "0")),
    }

    return {
        "header": header,
        "price": str(close),
        "change": change_str,
        "changePerc": change_perc,
        "closedTime": closed_time,
        "spxBanner": spx_banner,
        "metrics": metrics,
    }


# --- إعدادات مشتركة مع الداش بورد ---
# المسار المطلق للمجلد الذي يوجد فيه هذا الملف
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, 'settings.json')
def _job_exists(context, job_id: str) -> bool:
    try:
        return context.job_queue.scheduler.get_job(job_id) is not None
    except Exception:
        return False

async def safe_remove_job(job, context):
    try:
        if job and _job_exists(context, job.id):
            job.schedule_removal()
    except JobLookupError:
        pass

# --- استبدل دالة get_settings القديمة بهذه ---

def get_settings():
    """تقرأ كل الإعدادات من ملف JSON وتوفر قيم افتراضية آمنة"""
    defaults = {
        'schedule_time': '23:59', # وقت إغلاق الصفقات
        'monitor_increase': 0.10,
        'allowed_user_ids': [8513152190],  # نسبة الزيادة للمراقبة
        'closing_messages': {      # رسائل الإغلاق
            'list': ["اغلاق موفق للجميع"],
            'selected': "صفقتنا اليوم ولله الحمد 🤩👏\nبمجموعة عقود سباكس SPX\nبسعر {entry_price_adjusted:.0f} دولار حققت {highest_price_adjusted:.0f} دولار"
        }
    }
    if not os.path.exists(SETTINGS_FILE):
        print("[get_settings] تحذير: ملف settings.json غير موجود. سيتم استخدام الإعدادات الافتراضية.")
        return defaults
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content:
                print("[get_settings] تحذير: ملف settings.json فارغ. سيتم استخدام الإعدادات الافتراضية.")
                return defaults
            
            settings = json.loads(content)
            
            # دمج الإعدادات المحفوظة مع الافتراضية لضمان وجود كل المفاتيح
            # هذا يضمن أن الكود لن يتعطل إذا كان مفتاح ما مفقودًا من الملف
            final_settings = defaults.copy()
            final_settings.update(settings)

            # طباعة القيم التي تم تحميلها للمراجعة
            print(f"[get_settings] تم تحميل الإعدادات بنجاح:")
            print(f"  - وقت الجدولة: {final_settings['schedule_time']}")
            print(f"  - نسبة المتابعة: {final_settings['monitor_increase']}")
            print(f"  - رسالة الإغلاق المختارة: {final_settings['closing_messages']['selected']}")
            
            return final_settings
            
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"[get_settings] خطأ: ملف settings.json تالف أو غير موجود ({e}). سيتم استخدام الإعدادات الافتراضية.")
        return defaults

def _resolve_local_path(path: str) -> str:
    if not path:
        return ''
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path.replace('/', os.sep))


def _configured_template_path(slot: str, fallback: str) -> str:
    try:
        templates = get_settings().get('trade_image_templates', {}) or {}
        path = (templates.get(slot) or {}).get('active_path') or ''
        resolved = _resolve_local_path(path)
        if resolved and os.path.exists(resolved):
            return resolved
    except Exception as exc:
        print(f"[trade_image_templates] failed to read {slot}: {exc}")
    return fallback


# ------------------------------------
# ------------------------------------
def safe_float(value, default=0.00):
    """
    تحويل آمن للقيم إلى float مع التعامل مع '--' أو القيم الفارغة أو غير الصالحة
    """
    if value in ['--', '', None, 'None', float('nan')]:
        return default
    try:
        # إزالة الفواصل إذا وجدت (مثل 1,234.56 → 1234.56)
        cleaned = str(value).replace(',', '')
        return float(cleaned)
    except (ValueError, TypeError):
        return default


def create_image(
    data: dict,
    is_calls: bool = True,
    entry_price: float = 0.0,
    peak_price: float = 0.0,
    use_right_panel_background: bool = False
) -> io.BytesIO:
    """
    إنشاء صورة تحليل مع خيار اللوحة اليمنى ودعم المؤشرات والشركات
    """
    symbol = data.get('spxBanner', 'SPXW').strip()
    
    # تحديد الصورة بناءً على الرمز
    if symbol in INDICES_BACKGROUNDS:
        bg_dict = INDICES_BACKGROUNDS[symbol]
        slot = "indicator_right" if use_right_panel_background else "indicator_normal"
        fallback = bg_dict["right"] if use_right_panel_background else bg_dict["normal"]
        bg_path = _configured_template_path(slot, fallback)
    elif symbol == "SPXW":  # حالة احتياطية لسباكس
        bg_dict = INDICES_BACKGROUNDS["SPX"]
        slot = "indicator_right" if use_right_panel_background else "indicator_normal"
        fallback = bg_dict["right"] if use_right_panel_background else bg_dict["normal"]
        bg_path = _configured_template_path(slot, fallback)
    else:
        # إذا لم يكن مؤشراً، فهو شركة
        slot = "company_right" if use_right_panel_background else "company_normal"
        fallback = COMPANY_RIGHT_BG if use_right_panel_background else COMPANY_NORMAL_BG
        bg_path = _configured_template_path(slot, fallback)
    
    try:
        img = Image.open(bg_path).convert("RGBA")
    except Exception as e:
        print(f"فشل تحميل الخلفية {bg_path}: {e}")
        img = Image.new('RGBA', (800, 1200), (0, 0, 0, 255))

    draw = ImageDraw.Draw(img)

    # ─── تحميل الخطوط ───
    try:
        font_price_big  = ImageFont.truetype(FONT_PATH, 150)
        font_header     = ImageFont.truetype(FONT_PATH, 36)
        font_values     = ImageFont.truetype(FONT_PATH, 45)
        font_profit     = ImageFont.truetype(FONT_PATH, 50)
        font_peak       = ImageFont.truetype(FONT_PATH, 50)
        font_riyal_text = ImageFont.truetype(ARABIC_FONT_PATH, 45)
    except Exception as e:
        print(f"خطأ تحميل خطوط: {e}")
        default_font = ImageFont.load_default()
        font_price_big = font_header = font_values = font_profit = font_peak = font_riyal_text = default_font

    # استخراج البيانات الأساسية
    header_text  = data.get('header', 'SPX 5850 21 MAR 25 (w) Call')
    price        = data.get('price', '0.00')
    change_perc  = data.get('changePerc', '+0.00%')
    metrics      = data.get('metrics', {})

    # ─── تحديد المواضع حسب نوع الخلفية ───
    if use_right_panel_background:
        price_x       = 80
        price_y       = 150
        header_x      = 110
        header_y      = 80
        x_value_left  = 330
        y_start_left  = 345
        spacing_1     = 85
        spacing_2     = 85
        spacing_3     = 85
        x_right       = img.width - 270
        y_entry       = 410
        y_peak        = 720
        y_profit      = y_peak + 95
    else:
        price_x       = 90
        price_y       = 130
        header_x      = 110
        header_y      = 60
        x_value_left  = 440
        y_start_left  = 330
        spacing_1     = 110
        spacing_2     = 120
        spacing_3     = 110

    # السعر الكبير
    price_color = (12, 175, 130) if change_perc.startswith('+') else (254, 57, 87)
    draw.text((price_x, price_y), price, font=font_price_big, fill=price_color)

    # Header مع تلوين Call / Put
    green = (12, 175, 130)
    red   = (254, 57, 87)

    if "Call" in header_text:
        parts = header_text.split("Call", 1)
        before, after = parts[0], (parts[1] if len(parts) > 1 else "")
        draw.text((header_x, header_y), before, font=font_header, fill=(0, 0, 0))
        w = draw.textlength(before, font=font_header)
        draw.text((header_x + w, header_y), "Call", font=font_header, fill=green)
        w += draw.textlength("Call", font=font_header)
        draw.text((header_x + w, header_y), after, font=font_header, fill=(0, 0, 0))

    elif "Put" in header_text:
        parts = header_text.split("Put", 1)
        before, after = parts[0], (parts[1] if len(parts) > 1 else "")
        draw.text((header_x, header_y), before, font=font_header, fill=(0, 0, 0))
        w = draw.textlength(before, font=font_header)
        draw.text((header_x + w, header_y), "Put", font=font_header, fill=red)
        w += draw.textlength("Put", font=font_header)
        draw.text((header_x + w, header_y), after, font=font_header, fill=(0, 0, 0))

    else:
        draw.text((header_x, header_y), header_text, font=font_header, fill=(0, 0, 0))

    # القيم اليسارية
    open_val     = metrics.get('Open', '--')
    mid_val      = metrics.get('Mid', '--')
    open_int_val = metrics.get('Open Int', '0')
    be_val       = metrics.get('Break Even', '--')

    try:
        open_f = safe_float(open_val)
        prev   = safe_float(metrics.get('Prev Close', '0.00'))
        open_color = green if open_f > prev else red if open_f < prev else (0, 0, 0)
    except:
        open_color = (0, 0, 0)

    y_pos_left = [
        y_start_left,
        y_start_left + spacing_1,
        y_start_left + spacing_1 + spacing_2,
        y_start_left + spacing_1 + spacing_2 + spacing_3
    ]

    draw.text((x_value_left, y_pos_left[0]), str(open_val),     font=font_values, fill=open_color)
    draw.text((x_value_left, y_pos_left[1]), str(mid_val),      font=font_values, fill=(87, 93, 108))
    draw.text((x_value_left, y_pos_left[2]), str(open_int_val), font=font_values, fill=(87, 93, 108))
    draw.text((x_value_left, y_pos_left[3]), str(be_val),       font=font_values, fill=(87, 93, 108))

    # ─── الجانب الأيمن (إذا مفعّل) ───
    if use_right_panel_background and entry_price > 0:
        # سعر الدخول
        draw.text(
            (x_right + 20, y_entry + 17),
            f"{entry_price:.2f}",
            font=font_values,
            fill=(69, 83, 94)
        )

        # الربح بالدولار (USD)
        profit_usd_raw = (peak_price - entry_price) * 100
        profit_usd     = abs(profit_usd_raw)
        usd_amount     = f"{profit_usd:,.0f}"
        full_usd       = f"USD {usd_amount}"
        reshaped_usd   = arabic_reshaper.reshape(full_usd)
        bidi_usd       = get_display(reshaped_usd)

        draw.text((x_right - 20, y_peak), bidi_usd, font=font_riyal_text, fill=(255, 147, 0))

        usd_width = draw.textlength(bidi_usd, font=font_riyal_text)

        # ─── الربح بالريال (SAR) مع الإزاحة الذكية ───
        profit_sar   = profit_usd * 3.75
        sar_amount   = f"{profit_sar:,.0f}"
        full_sar     = f"SAR {sar_amount}"
        reshaped_sar = arabic_reshaper.reshape(full_sar)
        bidi_sar     = get_display(reshaped_sar)

        sar_full_width = draw.textlength(bidi_sar, font=font_riyal_text)

        # الإزاحة حسب إعداداتك الناجحة
        shift_x = 0
        if sar_full_width > 200:
            excess = sar_full_width - 200
            shift_x = min(excess * 0.5, 50)

        sar_x = (x_right - 20) - shift_x

        draw.text((sar_x, y_profit), bidi_sar, font=font_riyal_text, fill=(0, 0, 0))

        # النسبة المئوية
        perc_raw = ((peak_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        perc = abs(perc_raw)
        perc_text = f"{perc:+.1f}%"
        perc_color = green if perc >= 0 else red

        perc_width = draw.textlength(perc_text, font=font_profit)
        perc_x = (x_right - 20) + (usd_width - perc_width) // 2

        draw.text((perc_x, y_profit - 570), perc_text, font=font_profit, fill=perc_color)

    # ─── حفظ الصورة في الذاكرة وإرجاعها ───
    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    return bio
async def check_schedule_changes_job(context: ContextTypes.DEFAULT_TYPE):
    """
    وظيفة دورية آمنة تتحقق من تحديثات وقت الجدولة.
    """
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] التحقق من تحديثات وقت الجدولة...")

        # 1. احصل على الـ event loop الحالي
        loop = asyncio.get_running_loop()

        # 2. قم بتشغيل دالة قراءة الملف في executor منفصل لتجنب تجميد البوت
        # هذا هو الأسلوب الأكثر أمانًا لتشغيل كود متزامن
        settings = await loop.run_in_executor(None, get_settings)
        new_schedule_time_str = settings.get('schedule_time', '20:35')

        bot_data = context.application.bot_data
        current_schedule_time_str = bot_data.get('current_schedule_time')

        # 3. إذا لم يتغير الوقت، لا تفعل شيئًا واخرج مبكرًا
        if new_schedule_time_str == current_schedule_time_str:
            return

        # 4. إذا تغير الوقت، قم بالتحديث
        print(f"تم اكتشاف تغيير في وقت الجدولة! الجديد: {new_schedule_time_str}, القديم: {current_schedule_time_str}")
        
        job_queue = context.application.job_queue
        
        # إزالة المهام القديمة
        old_jobs = job_queue.get_jobs_by_name('daily_close_trades')
        if old_jobs:
            for job in old_jobs:
                await safe_remove_job(job, context)
            print(f"تمت إزالة {len(old_jobs)} مهمة مجدولة قديمة.")

        # جدولة المهمة الجديدة
        hour, minute = map(int, new_schedule_time_str.split(':'))
        
        job_queue.run_daily(
            close_trades_today, 
            time(hour, minute, tzinfo=LOCAL_TZ), 
            name='daily_close_trades'
        )

        # تحديث القيمة المحفوظة
        bot_data['current_schedule_time'] = new_schedule_time_str
        print(f"تمت جدولة مهمة إغلاق الصفقات اليومية بنجاح في الساعة {hour:02d}:{minute:02d}")
        new_monitor_increase = settings.get('monitor_increase', 0.10)
        current_monitor_increase = bot_data.get('current_monitor_increase')
        if new_monitor_increase != current_monitor_increase:
            print(f"تم اكتشاف تغيير في نسبة المتابعة! الجديدة: {new_monitor_increase}, القديمة: {current_monitor_increase}")
            bot_data['current_monitor_increase'] = new_monitor_increase
            # تحديث القيمة في كل العقود التي تتم متابعتها حاليًا
            tracked_contracts = bot_data.get('tracked_contracts', {})
            for key, contract_data in tracked_contracts.items():
                contract_data['monitor_increase'] = new_monitor_increase
            print(f"تم تحديث نسبة المتابعة لـ {len(tracked_contracts)} عقد تتم متابعته.")
    except (ValueError, TypeError) as e:
        print(f"خطأ في تنسيق الوقت '{new_schedule_time_str}'. لم يتم تحديث الجدولة. الخطأ: {e}")
    except Exception as e:
        # طباعة أي خطأ غير متوقع يحدث داخل الوظيفة نفسها
        import traceback
        print("حدث خطأ غير متوقع في وظيفة التحقق من الجدولة:")
        traceback.print_exc()
async def extract_popup_data(page, row_idx: int, is_calls: bool, expected_strike: str):
    async def clear_overlays():
        for _ in range(3):
            try:
                await page.keyboard.press('Escape')
                await page.wait_for_timeout(200)
            except:
                pass
        await page.wait_for_timeout(500)

    strike_formatted = f"{expected_strike[:1]},{expected_strike[1:]}"
    expected_type = "Call" if is_calls else "Put"
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            await page.evaluate("""(i)=>{
                const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
                const midWrap  = document.querySelector('div.midFrame  .simplebar-content-wrapper');
                const leftWrap = document.querySelector('div.leftFrame .simplebar-content-wrapper');
                const rightWrap= document.querySelector('div.rightFrame .simplebar-content-wrapper');
                const lRows=[...document.querySelectorAll('div.leftFrame  table.body > tbody > tr.row')];
                const rRows=[...document.querySelectorAll('div.rightFrame table.body > tbody > tr.row')];
                const mRows=[...document.querySelectorAll('div.midFrame tbody.strikes > tr')];
                const mt=mRows[i], lt=lRows[i], rt=rRows[i];
                if (midWrap && mt)      midWrap.scrollTop   = clamp(mt.offsetTop  - 60, 0, midWrap.scrollHeight);
                if (leftWrap && lt)     leftWrap.scrollTop  = clamp(lt.offsetTop  - 60, 0, leftWrap.scrollHeight);
                if (rightWrap && rt)    rightWrap.scrollTop = clamp(rt.offsetTop  - 60, 0, rightWrap.scrollHeight);
            }""", row_idx)
            await page.wait_for_timeout(300)

            selector = 'div.leftFrame table.body > tbody > tr.row' if is_calls else 'div.rightFrame table.body > tbody > tr.row'
            row = page.locator(selector).nth(row_idx)
            
            # التأكد من أن الصف مرئي وقابل للتفاعل
            await row.scroll_into_view_if_needed()
            await page.wait_for_timeout(1000)
            await row.wait_for(state="visible", timeout=20000)

            await clear_overlays()

            # النقر على الصف
            max_click_attempts = 3
            for click_attempt in range(1, max_click_attempts + 1):
                try:
                    await row.click(position={'x': 50, 'y': 18}, force=True, timeout=20000)
                    await page.wait_for_timeout(1000)
                    break
                except PlaywrightTimeoutError as e:
                    print(f"Click attempt {click_attempt} failed for strike {strike_formatted}: {e}")
                    if click_attempt == max_click_attempts:
                        raise Exception(f"Failed to click row after {max_click_attempts} attempts: {e}")
                    await page.wait_for_timeout(1500)

            # استخراج البيانات من النافذة المنبثقة
            popup_data = await page.evaluate("""()=>{
                const getText=(sel,root=document,d='--')=>{
                    const el=root.querySelector(sel);
                    return (el && (el.textContent||'').trim()) || d;
                };
                const tit=[...document.querySelectorAll('div.tit')].find(el=>/SPX/i.test(el.textContent||''));
                const card=(()=>{
                    let n=tit;
                    for(let k=0;k<6 && n;k++,n=n.parentElement){
                        if(n?.querySelector?.('div.price') && n?.querySelector?.('div.changePrice')) return n;
                    }
                    return document;
                })();
                const header=(tit && tit.textContent.trim()) || 'غير متاح';
                const price=getText('div.price', card, '0.00');
                const ratios=card.querySelectorAll('div.changePrice .ratio');
                const change=ratios[0]?.textContent.trim() || '0.00';
                const changePerc=ratios[1]?.textContent.trim() || '0.00%';
                const closedTime='Closed at ' + getText('.tips-time span', card, 'غير متاح');
                const bannerEl=document.querySelector('div.banner') ||
                    [...document.querySelectorAll('div')].find(d=>(d.className||'').includes('banner'));
                const spxBanner=bannerEl ? bannerEl.textContent.trim().replace('SPX：','SPX ') : 'SPX غير متاح';
                return {header, price, change, changePerc, closedTime, spxBanner};
            }""")

            # التحقق من أن البيانات المستخرجة تتطابق مع الاستريك ونوع العملية
            import re
            if not re.search(rf"\${strike_formatted.replace(',', '')}\b", popup_data['header']):
                print(f"Data mismatch: Expected strike {strike_formatted}, but got header {popup_data['header']}")
                raise Exception(f"Data mismatch for strike {strike_formatted}")
            
            # التحقق من نوع العملية (Call أو Put)
            if expected_type not in popup_data['header']:
                print(f"Operation type mismatch: Expected {expected_type}, but got header {popup_data['header']}")
                raise Exception(f"Operation type mismatch for {strike_formatted}: Expected {expected_type}")

            # محاولة استخراج البيانات الإضافية (key stats)
            for stat_attempt in range(1, max_attempts + 1):
                try:
                    await page.evaluate("""
                    (() => {
                        const nodes = [...document.querySelectorAll('body *')].filter(n => {
                            const t = (n.textContent || '').toLowerCase();
                            return t.includes('key stat');
                        });
                        if (!nodes.length) return;
                        const midY = window.scrollY + window.innerHeight/2;
                        let best = null, bestDist = Infinity;
                        for (const n of nodes) {
                            const r = n.getBoundingClientRect();
                            const cy = r.top + window.scrollY + r.height/2;
                            const d = Math.abs(cy - midY);
                            if (d < bestDist) { bestDist = d; best = n; }
                        }
                        let root = best;
                        for (let i=0; i<8 && root; i++) {
                            if (root.querySelector && root.querySelector('.tr')) break;
                            root = root.parentElement;
                        }
                        if (root) {
                            const chevr = root.querySelector('i[class*="webull-arrow_under_"]') ||
                                        document.querySelector('i[class*="webull-arrow_under_"]');
                            const rowsCnt = root.querySelectorAll('.tr').length;
                            if (chevr && rowsCnt < 5) {
                                chevr.dispatchEvent(new MouseEvent('click', {bubbles:true}));
                            }
                        }
                    })();
                    """)
                    await page.wait_for_timeout(500)

                    await page.wait_for_function("""
                    () => {
                        const nodes = [...document.querySelectorAll('body *')].filter(n => (n.textContent||'').toLowerCase().includes('key stat'));
                        if (!nodes.length) return false;
                        const midY = window.scrollY + window.innerHeight/2;
                        let best=null, bestDist=Infinity;
                        for (const n of nodes) {
                            const r = n.getBoundingClientRect();
                            const cy = r.top + window.scrollY + r.height/2;
                            const d = Math.abs(cy - midY);
                            if (d< bestDist){ bestDist=d; best=n; }
                        }
                        let root = best;
                        for (let i=0; i<8 && root; i++) {
                            if (root.querySelector && root.querySelector('.tr')) return true;
                            root = root.parentElement;
                        }
                        return false;
                    }
                    """, timeout=20000)
                    break
                except PlaywrightTimeoutError as e:
                    print(f"Attempt {stat_attempt} failed to load key stats for strike {strike_formatted}: {e}")
                    if stat_attempt == max_attempts:
                        raise Exception(f"Failed to load key stats after {max_attempts} attempts: {e}")
                    await clear_overlays()
                    await page.wait_for_timeout(1500)

            popup_metrics = await page.evaluate("""
            () => {
                const out = {};
                const wanted = new Set([
                    'open','prev close','volume','high','low','impl vol','delta','gamma',
                    'theta','vega','rho','open int','mid','break even','latest price vol','break even rate'
                ]);

                const nodes = [...document.querySelectorAll('body *')].filter(n => (n.textContent||'').toLowerCase().includes('key stat'));
                if (!nodes.length) return out;

                const midY = window.scrollY + window.innerHeight/2;
                let best=null, bestDist=Infinity;
                for (const n of nodes) {
                    const r = n.getBoundingClientRect();
                    const cy = r.top + window.scrollY + r.height/2;
                    const d = Math.abs(cy - midY);
                    if (d<bestDist){ bestDist=d; best=n; }
                }
                let root = best;
                for (let i=0; i<8 && root; i++) {
                    if (root.querySelector && root.querySelector('.tr')) break;
                    root = root.parentElement;
                }
                if (!root) return out;

                const rows = [...root.querySelectorAll('.tr')];
                for (const row of rows) {
                    const tds = row.querySelectorAll(':scope > .td');
                    if (!tds.length) continue;
                    const label = (tds[0].textContent || '').trim();
                    if (!label) continue;
                    const key = label.toLowerCase();
                    if (!wanted.has(key)) continue;
                    const valEl = row.querySelector(':scope > .td.value') || tds[1];
                    const value = (valEl && (valEl.textContent||'').trim()) || '--';
                    out[label] = value;
                }
                return out;
            }
            """)

            popup_data['metrics'] = popup_metrics
            return popup_data

        except Exception as e:
            print(f"Attempt {attempt} failed for strike {strike_formatted}: {e}")
            if attempt == max_attempts:
                raise Exception(f"Failed to extract popup data for strike {strike_formatted} after {max_attempts} attempts: {e}")
            await clear_overlays()
            await page.wait_for_timeout(2000)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [KeyboardButton("البحث في المؤشرات")],  # هذا لليومي
        [KeyboardButton("عقود أسبوعية"), KeyboardButton("عقود شهرية")], # الأسبوعي والشهري
        [KeyboardButton("النشر في جروب"), KeyboardButton("إرسال رسالة إلى الجروب")],
        [KeyboardButton("إرسال تنبيه")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text('مرحباً بك في بوت مراقبة المؤشرات', reply_markup=reply_markup)
    context.user_data.clear()

import io  # تأكد أنك مستورد io في أعلى الملف

async def send_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    text = user_data.get('group_message_text', '')
    photo_buffer = user_data.get('group_message_photo')   # هذا هو BytesIO
    target_groups = user_data.get('target_groups', [])

    if not target_groups:
        await update.message.reply_text(
            "خطأ: لم يتم تحديد أي جروب لإرسال الرسالة.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("العودة إلى القائمة الرئيسية")]], resize_keyboard=True)
        )
        return

    try:
        for group_id in target_groups:
            if photo_buffer:
                # هذا هو الحل الرئيسي:
                photo_buffer.seek(0)   # إعادة المؤشر إلى بداية الملف
                
                await context.bot.send_photo(
                    chat_id=group_id,
                    photo=InputFile(photo_buffer, filename="message_photo.png"),
                    caption=text
                )
            else:
                await context.bot.send_message(
                    chat_id=group_id,
                    text=text
                )

        await update.message.reply_text(
            "تم إرسال الرسالة إلى الجروب(ات) المحددة بنجاح! ✅",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("العودة إلى القائمة الرئيسية")]], resize_keyboard=True)
        )

    except Exception as e:
        print(f"Error sending message to groups: {e}")
        await update.message.reply_text(
            f"خطأ أثناء إرسال الرسالة: {str(e)}",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("العودة إلى القائمة الرئيسية")]], resize_keyboard=True)
        )
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    if user_data.get('state') == 'input_group_message_photo':
        photo = update.message.photo[-1]  # الحصول على الصورة بأعلى دقة
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        user_data['group_message_photo'] = io.BytesIO(photo_bytes)
        await update.message.reply_text(
            "أدخل النص المرافق للصورة (أو اضغط 'إرسال بدون نص' لإرسال الصورة بدون نص):",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("إرسال بدون نص")],
                [KeyboardButton("العودة إلى القائمة الرئيسية")]
            ], resize_keyboard=True)
        )
        user_data['state'] = 'input_group_message_photo_text'
    else:
        await update.message.reply_text(
            "يرجى اختيار 'إرسال رسالة إلى الجروب' أولاً.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("العودة إلى القائمة الرئيسية")]], resize_keyboard=True)
        )

# تعديل دالة handle_message لدعم النص المرافق للصورة

    # Handle photo text input
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # إذا كانت الرسالة نصية
    if update.message.text:
        text = update.message.text.strip()
    else:
        text = ""

    user_data = context.user_data

    # === التحقق من الصلاحية للأوامر الحساسة ===
    sensitive_texts = [
        "إرسال رسالة إلى الجروب",
        "Search for Strike",
        "النشر في جروب",
        "البحث عن شركات",
        "البحث في المؤشرات",
        "عقود أسبوعية",
        "عقود شهرية",
        "إرسال تنبيه",
    ]

    sensitive_states = [
        'select_message_type',
        'select_message_group',
        'input_group_message_text',
        'input_group_message_photo',
        'input_group_message_photo_text',
        'waiting_for_strike',
        'select_company',
        'waiting_for_company_strike',
        'select_index',
        'waiting_for_index_strike',
        'select_strike_type',
        'post_strike_action',
        'select_publish_group',
        'add_text',
        'input_text',
        'select_alert_symbol',
        'select_alert_destination',
    ]

    current_state = user_data.get('state')
    is_sensitive = (
        text in sensitive_texts or
        current_state in sensitive_states
    )

    if is_sensitive:
        settings = get_settings()
        allowed_ids = settings.get('allowed_user_ids', [])
        user_id = update.effective_user.id

        if user_id not in allowed_ids:
            await update.message.reply_text(
                "🚫 عذرًا، هذا الأمر محظور وغير متاح إلا للمشرفين المصرح لهم فقط.\n"
                "إذا كنت تعتقد أن هذا خطأ، تواصل مع المطور."
            )
            await start(update, context)
            return

    # === العودة للقائمة الرئيسية ===
    if text == "العودة إلى القائمة الرئيسية":
        await start(update, context)
        return

    # ===================== إرسال رسالة إلى الجروب (نص/صورة) =====================

    if user_data.get('state') == 'select_message_group':
        if text == "العودة إلى الخطوة السابقة":
            keyboard = [
                [KeyboardButton("نص فقط"), KeyboardButton("صورة مع نص")],
                [KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]
            await update.message.reply_text(
                "اختر نوع الرسالة:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            user_data['state'] = 'select_message_type'

        elif text in ["الجروب العام", "الجروب الخاص", "الجروبين معًا"]:
            user_data['target_groups'] = (
                [PUBLIC_GROUP_ID, PRIVATE_GROUP_ID] if text == "الجروبين معًا"
                else [PUBLIC_GROUP_ID] if text == "الجروب العام"
                else [PRIVATE_GROUP_ID]
            )

            if user_data.get('message_type') == "نص فقط":
                await update.message.reply_text(
                    "أدخل النص المطلوب لإرساله إلى الجروب(ات):",
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton("العودة إلى الخطوة السابقة"), KeyboardButton("العودة إلى القائمة الرئيسية")]],
                        resize_keyboard=True
                    )
                )
                user_data['state'] = 'input_group_message_text'
            else:
                await update.message.reply_text(
                    "أرسل الصورة التي تريد إرسالها إلى الجروب(ات):",
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton("العودة إلى الخطوة السابقة"), KeyboardButton("العودة إلى القائمة الرئيسية")]],
                        resize_keyboard=True
                    )
                )
                user_data['state'] = 'input_group_message_photo'
        else:
            await update.message.reply_text(
                "يرجى اختيار 'الجروب العام' أو 'الجروب الخاص' أو 'الجروبين معًا'",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("الجروب العام"), KeyboardButton("الجروب الخاص")],
                    [KeyboardButton("الجروبين معًا")],
                    [KeyboardButton("العودة إلى الخطوة السابقة"), KeyboardButton("العودة إلى القائمة الرئيسية")]
                ], resize_keyboard=True)
            )

    elif user_data.get('state') == 'input_group_message_photo_text':
        if text == "إرسال بدون نص":
            user_data['group_message_text'] = ""
        else:
            user_data['group_message_text'] = text

        await send_group_message(update, context)
        user_data.clear()
        await start(update, context)

    elif text == "إرسال رسالة إلى الجروب":
        keyboard = [
            [KeyboardButton("نص فقط"), KeyboardButton("صورة مع نص")],
            [KeyboardButton("العودة إلى القائمة الرئيسية")]
        ]
        await update.message.reply_text(
            "اختر نوع الرسالة:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        user_data['state'] = 'select_message_type'

    elif user_data.get('state') == 'select_message_type':
        if text == "نص فقط":
            user_data['message_type'] = "نص فقط"
            keyboard = [
                [KeyboardButton("الجروب العام"), KeyboardButton("الجروب الخاص")],
                [KeyboardButton("الجروبين معًا")],
                [KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]
            await update.message.reply_text(
                "اختر الجروب المستهدف:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            user_data['state'] = 'select_message_group'

        elif text == "صورة مع نص":
            user_data['message_type'] = "صورة مع نص"
            keyboard = [
                [KeyboardButton("الجروب العام"), KeyboardButton("الجروب الخاص")],
                [KeyboardButton("الجروبين معًا")],
                [KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]
            await update.message.reply_text(
                "اختر الجروب المستهدف:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            user_data['state'] = 'select_message_group'
        else:
            await update.message.reply_text(
                "يرجى اختيار 'نص فقط' أو 'صورة مع نص'",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("العودة إلى القائمة الرئيسية")]], resize_keyboard=True)
            )

    elif user_data.get('state') == 'input_group_message_text':
        user_data['group_message_text'] = text
        await send_group_message(update, context)
        user_data.clear()
        await start(update, context)

    # ===================== Search for Strike العادي =====================

    elif text == "Search for Strike":
        user_data.clear()

        user_data['is_company_mode'] = False
        user_data['is_index_mode'] = False

        await update.message.reply_text(
            "اكتب رقم الاستريك الذي تريده (مثال: 6530)",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                resize_keyboard=True
            )
        )

        user_data['waiting_for_strike'] = True
        user_data['state'] = 'waiting_for_strike'

    # ===================== البحث عن شركات =====================

    elif text == "البحث عن شركات":
        user_data.clear()

        user_data['is_company_mode'] = True
        user_data['is_index_mode'] = False

        comps = list(COMPANIES_TICKERS.keys())
        comp_keyboard = []

        for i in range(0, len(comps), 3):
            row = [KeyboardButton(c) for c in comps[i:i + 3]]
            comp_keyboard.append(row)

        comp_keyboard.append([KeyboardButton("العودة إلى القائمة الرئيسية")])

        await update.message.reply_text(
            "اختر الشركة المطلوبة:",
            reply_markup=ReplyKeyboardMarkup(comp_keyboard, resize_keyboard=True)
        )

        user_data['state'] = 'select_company'

    elif user_data.get('state') == 'select_company':
        if text in COMPANIES_TICKERS:
            user_data['selected_company'] = text
            user_data['company_ticker_id'] = COMPANIES_TICKERS[text]

            user_data['is_company_mode'] = True
            user_data['is_index_mode'] = False

            await update.message.reply_text(
                f"تم اختيار {text}.\nاكتب رقم الاستريك الذي تريده :",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                    resize_keyboard=True
                )
            )

            user_data['state'] = 'waiting_for_company_strike'
        else:
            await update.message.reply_text("يرجى اختيار شركة من الأزرار المتاحة.")

    elif user_data.get('state') == 'waiting_for_company_strike':
        try:
            float(text)

            user_data['strike'] = text

            keyboard = [
                [KeyboardButton("Calls"), KeyboardButton("Puts")],
                [KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]

            await update.message.reply_text(
                f"تم تحديد الاستريك {text} لشركة {user_data['selected_company']}.\nاختر نوع العقد:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )

            user_data['state'] = 'select_strike_type'

        except ValueError:
            await update.message.reply_text("يرجى إدخال رقم استريك صحيح")

    # ===================== البحث في المؤشرات (يومي / أسبوعي / شهري) =====================

    elif text in ["البحث في المؤشرات", "عقود أسبوعية", "عقود شهرية"]:
        user_data.clear()

        user_data['is_company_mode'] = False
        user_data['is_index_mode'] = True

        # حفظ نوع التوقيت بناءً على الزر الذي تم الضغط عليه
        if text == "البحث في المؤشرات":
            user_data['timeframe'] = 'daily'
        elif text == "عقود أسبوعية":
            user_data['timeframe'] = 'weekly'
        elif text == "عقود شهرية":
            user_data['timeframe'] = 'monthly'

        keyboard = [
            [KeyboardButton("SPX"), KeyboardButton("SPY")],
            [KeyboardButton("QQQ"), KeyboardButton("NDX")],
            [KeyboardButton("العودة إلى القائمة الرئيسية")]
        ]

        await update.message.reply_text(
            f"أنت الآن في قسم ({text})\nاختر المؤشر المطلوب:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

        user_data['state'] = 'select_index'

    elif user_data.get('state') == 'select_index':
        if text in INDICES_TICKERS:
            user_data['selected_index'] = text
            user_data['index_ticker_id'] = INDICES_TICKERS[text]

            await update.message.reply_text(
                f"تم اختيار مؤشر {text}.\nاكتب رقم الاستريك الذي تريده (مثال: 550):",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                    resize_keyboard=True
                )
            )

            user_data['state'] = 'waiting_for_index_strike'
        else:
            await update.message.reply_text("يرجى اختيار مؤشر من الأزرار المتاحة.")

    elif user_data.get('state') == 'waiting_for_index_strike':
        try:
            float(text)

            user_data['strike'] = text

            keyboard = [
                [KeyboardButton("Calls"), KeyboardButton("Puts")],
                [KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]

            await update.message.reply_text(
                f"تم تحديد الاستريك {text} لمؤشر {user_data['selected_index']}.\nاختر نوع العقد:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )

            user_data['state'] = 'select_strike_type'

        except ValueError:
            await update.message.reply_text("يرجى إدخال رقم استريك صحيح (مثال: 550)")

    # ===================== استريك SPX القديم =====================

    elif user_data.get('waiting_for_strike') and user_data.get('state') == 'waiting_for_strike':
        if re.match(r'^\d{4}$', text):
            user_data['waiting_for_strike'] = False
            user_data['strike'] = text

            keyboard = [
                [KeyboardButton("Calls"), KeyboardButton("Puts")],
                [KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]

            await update.message.reply_text(
                f"تم تحديد الاستريك {text}.\nاختر نوع العقد:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )

            user_data['state'] = 'select_strike_type'
        else:
            await update.message.reply_text("يرجى إدخال رقم استريك صحيح بـ 4 أرقام (مثال: 6530)")

    # ===================== اختيار Calls / Puts =====================

    elif user_data.get('state') == 'select_strike_type':
        if text in ["Calls", "Puts"]:
            strike = user_data.get('strike')

            if not strike:
                await update.message.reply_text(
                    "لا يوجد استريك محدد. استخدم زر 'Search for Strike' مرة أخرى."
                )
                user_data['state'] = None
                return

            user_data['contract_type'] = text

            selected_index = user_data.get('selected_index')
            selected_company = user_data.get('selected_company')

            if user_data.get('is_index_mode') and selected_index:
                await update.message.reply_text(
                    f"جاري سحب بيانات {text} للاستريك {strike} لمؤشر {selected_index}"
                )
            elif user_data.get('is_company_mode') and selected_company:
                await update.message.reply_text(
                    f"جاري سحب بيانات {text} للاستريك {strike} لشركة {selected_company}"
                )
            else:
                await update.message.reply_text(
                    f"جاري سحب بيانات {text} للاستريك {strike}"
                )

            await process_strike(update, context, strike, text)

            keyboard = [
                [KeyboardButton("النشر في جروب")],
                [KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]

            await update.message.reply_text(
                "تم تجهيز العقد.\nماذا تريد أن تفعل الآن؟",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )

            user_data['state'] = 'post_strike_action'

        elif text == "العودة إلى القائمة الرئيسية":
            await start(update, context)
            user_data['state'] = None
        else:
            keyboard = [
                [KeyboardButton("Calls"), KeyboardButton("Puts")],
                [KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]

            await update.message.reply_text(
                "يرجى اختيار 'Calls' أو 'Puts'",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )

    # ===================== النشر في جروب بعد اختيار العقد =====================

    elif user_data.get('state') == 'post_strike_action':
        if text == "النشر في جروب":
            keyboard = [
                [KeyboardButton("الجروب العام"), KeyboardButton("الجروب الخاص")],
                [KeyboardButton("الجروبين معًا")],
                [KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]

            await update.message.reply_text(
                "اختر الجروب المستهدف:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )

            user_data['state'] = 'select_publish_group'

        elif text == "العودة إلى القائمة الرئيسية":
            await start(update, context)
            user_data['state'] = None

        else:
            keyboard = [
                [KeyboardButton("النشر في جروب")],
                [KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]

            await update.message.reply_text(
                "يرجى اختيار 'النشر في جروب' أو 'العودة إلى القائمة الرئيسية'",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )

    # ===================== النشر في جروب =====================

    elif text == "النشر في جروب":
        keyboard = [
            [KeyboardButton("الجروب العام"), KeyboardButton("الجروب الخاص")],
            [KeyboardButton("الجروبين معًا")],
            [KeyboardButton("العودة إلى القائمة الرئيسية")]
        ]

        await update.message.reply_text(
            "اختر الجروب المستهدف:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

        user_data['state'] = 'select_publish_group'

    elif user_data.get('state') == 'select_publish_group':
        if text == "العودة إلى الخطوة السابقة":
            await start(update, context)

        elif text in ["الجروب العام", "الجروب الخاص", "الجروبين معًا"]:
            user_data['target_groups'] = (
                [PUBLIC_GROUP_ID, PRIVATE_GROUP_ID] if text == "الجروبين معًا"
                else [PUBLIC_GROUP_ID] if text == "الجروب العام"
                else [PRIVATE_GROUP_ID]
            )

            if 'contract_type' not in user_data:
                await update.message.reply_text(
                    "يجب أولاً اختيار عقد Call أو Put قبل النشر في الجروب.",
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                        resize_keyboard=True
                    )
                )
                user_data['state'] = None
                return

            keyboard = [
                [KeyboardButton("نعم"), KeyboardButton("لا")],
                [KeyboardButton("العودة إلى الخطوة السابقة"), KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]

            await update.message.reply_text(
                "هل تريد إضافة نص إلى الرسالة؟",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )

            user_data['state'] = 'add_text'
        else:
            await update.message.reply_text(
                "يرجى اختيار 'الجروب العام' أو 'الجروب الخاص' أو 'الجروبين معًا'",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("الجروب العام"), KeyboardButton("الجروب الخاص")],
                    [KeyboardButton("الجروبين معًا")],
                    [KeyboardButton("العودة إلى القائمة الرئيسية")]
                ], resize_keyboard=True)
            )

    elif user_data.get('state') == 'add_text':
        if text == "العودة إلى الخطوة السابقة":
            keyboard = [
                [KeyboardButton("الجروب العام"), KeyboardButton("الجروب الخاص")],
                [KeyboardButton("الجروبين معًا")],
                [KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]
            await update.message.reply_text(
                "اختر الجروب المستهدف:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            user_data['state'] = 'select_publish_group'

        elif text == "نعم":
            await update.message.reply_text(
                "أدخل النص المطلوب:",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("العودة إلى الخطوة السابقة"), KeyboardButton("العودة إلى القائمة الرئيسية")]],
                    resize_keyboard=True
                )
            )
            user_data['state'] = 'input_text'

        elif text == "لا":
            # النشر مباشرة بدون سؤال الوقف
            user_data['stop_loss'] = None
            await update.message.reply_text("شكراً على تعاونكم! جاري إرسال الصفقة إلى الجروب(ات)...")
            await publish_to_group(update, context)
            user_data['state'] = None

        else:
            await update.message.reply_text(
                "يرجى اختيار 'نعم' أو 'لا' أو 'العودة إلى الخطوة السابقة'",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                    resize_keyboard=True
                )
            )

    elif user_data.get('state') == 'input_text':
        if text == "العودة إلى الخطوة السابقة":
            keyboard = [
                [KeyboardButton("نعم"), KeyboardButton("لا")],
                [KeyboardButton("العودة إلى الخطوة السابقة"), KeyboardButton("العودة إلى القائمة الرئيسية")]
            ]
            await update.message.reply_text(
                "هل تريد إضافة نص إلى الرسالة؟",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            user_data['state'] = 'add_text'
        else:
            # النشر مباشرة بعد إدخال النص
            user_data['custom_text'] = text
            user_data['stop_loss'] = None
            await update.message.reply_text("شكراً على تعاونكم! جاري إرسال الصفقة إلى الجروب(ات)...")
            await publish_to_group(update, context)
            user_data['state'] = None

    # ===================== إرسال تنبيه =====================

    elif text == "إرسال تنبيه":
        # دمج كل المؤشرات والشركات في قائمة واحدة لتكوين الأزرار
        all_symbols = list(INDICES_TICKERS.keys())

        keyboard = []

        # ترتيب الأزرار كل 3 رموز في صف
        for i in range(0, len(all_symbols), 3):
            keyboard.append([KeyboardButton(s) for s in all_symbols[i:i + 3]])

        keyboard.append([KeyboardButton("العودة إلى القائمة الرئيسية")])

        await update.message.reply_text(
            "اختر الرمز الذي تريد التنبيه عنه:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

        user_data['state'] = 'select_alert_symbol'

    elif user_data.get('state') == 'select_alert_symbol':
        if text == "العودة إلى القائمة الرئيسية":
            await start(update, context)
            user_data.clear()
            return

        user_data['alert_symbol'] = text

        keyboard = [
            [KeyboardButton("القناة العامة"), KeyboardButton("القناة الخاصة")],
            [KeyboardButton("الاثنين معًا")],
            [KeyboardButton("العودة إلى القائمة الرئيسية")]
        ]

        await update.message.reply_text(
            "إلى أين تريد إرسال التنبيه؟",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

        user_data['state'] = 'select_alert_destination'

    elif user_data.get('state') == 'select_alert_destination':
        if text == "العودة إلى القائمة الرئيسية":
            await start(update, context)
            user_data.clear()
            return

        symbol = user_data.get('alert_symbol', '')

        # تنسيق رسالة التنبيه لتتضمن الرمز
        alert_text = f"📢⏳ {symbol} الاستعداد لطرح عقد ⏳📢"

        targets = []

        if text == "القناة العامة":
            targets = [PUBLIC_GROUP_ID]
        elif text == "القناة الخاصة":
            targets = [PRIVATE_GROUP_ID]
        elif text == "الاثنين معًا":
            targets = [PUBLIC_GROUP_ID, PRIVATE_GROUP_ID]
        else:
            await update.message.reply_text(
                "يرجى اختيار وجهة صحيحة أو العودة إلى القائمة الرئيسية",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                    resize_keyboard=True
                )
            )
            return

        success_count = 0
        error_messages = []

        for chat_id in targets:
            try:
                await context.bot.send_message(chat_id=chat_id, text=alert_text)
                success_count += 1
            except Exception as e:
                error_messages.append(f"فشل إرسال إلى {chat_id}: {str(e)}")

        if success_count == len(targets):
            reply = "تم إرسال التنبيه بنجاح إلى جميع الوجهات المختارة ✓"
        else:
            reply = f"تم الإرسال إلى {success_count} من {len(targets)} وجهة.\n"
            if error_messages:
                reply += "\n".join(error_messages)

        await update.message.reply_text(
            reply,
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                resize_keyboard=True
            )
        )

        user_data.clear()
def load_todays_trades():
    try:
        df = pd.read_csv(TRADES_CSV, encoding='utf-8-sig', on_bad_lines='skip')
        today = datetime.now().strftime('%Y-%m-%d')
        return df[df['Time'].str.startswith(today)]
    except FileNotFoundError:
        return pd.DataFrame(columns=['Trade ID', 'Time', 'Strike', 'Type', 'Entry Price', 'High', 'Profit', 'Loss', 'Stop Loss'])
    except Exception as e:
        print(f"Error loading trades CSV: {e}")
        return pd.DataFrame(columns=['Trade ID', 'Time', 'Strike', 'Type', 'Entry Price', 'High', 'Profit', 'Loss', 'Stop Loss'])


async def show_trades_for_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trades = load_todays_trades()
    if trades.empty:
        await update.message.reply_text("لا توجد صفقات مسجلة لهذا اليوم.", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("العودة إلى القائمة الرئيسية")]], resize_keyboard=True))
        await start(update, context)
        return
    trades_text = "\n".join(
        f"الصفقة {i+1}: الاستريك {row['Strike']} ({row['Type']}), سعر الدخول: {row['Entry Price']}, أعلى سعر: {row['High']}, ربح: {row['Profit']}, خسارة: {row['Loss']}, الوقت: {row['Time']}"
        for i, row in trades.iterrows()
    )
    await update.message.reply_text(f"الصفقات اليومية:\n{trades_text}\n\nأدخل رقم الصفقة للتعديل (مثال: 1):", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("العودة إلى القائمة الرئيسية")]], resize_keyboard=True))


async def extract_data(app, context, use_monitor_browser=False):
    """
    Extract table data for a given strike from the Webull options page.
    
    Args:
        app: The Application object containing bot data and job/user information.
        context: The ContextTypes.DEFAULT_TYPE object to access user_data.
        use_monitor_browser: Boolean to indicate whether to use the monitor browser (True) or search browser (False).
    
    Returns:
        tuple: (calls, puts, idx) where calls and puts are dictionaries of column-value pairs,
               and idx is the row index of the strike.
    
    Raises:
        Exception: If the page is unavailable, closed, or the strike is not found after max retries.
    """
    # Get the appropriate page based on context
    page_key = 'monitor_page' if use_monitor_browser else 'search_page'
    page = app.bot_data.get(page_key)
    if not page or page.is_closed():
        print(f"Error: {page_key} is not available or closed")
        raise Exception(f"الصفحة {page_key} غير متاحة أو مغلقة")

    # Get strike from job.data (for monitoring) or user_data (for search)
    strike = None
    if use_monitor_browser:
        if app.bot_data.get('job') and app.bot_data['job'].data.get('strike'):
            strike = app.bot_data['job'].data['strike']
            print("Using strike from job.data")
    else:
        if context.user_data.get('strike'):
            strike = context.user_data['strike']
            print("Using strike from user_data")
    
    if not strike:
        print("Error: Strike value is not available")
        raise Exception("قيمة الاستريك غير متاحة")

    strike_formatted = f"{strike[:1]},{strike[1:]}"
    print(f"Starting data extraction for strike {strike_formatted} using {page_key}")
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Attempt {attempt}: Clicking refresh button for strike {strike_formatted}...")
            await page.locator('footer i.webull-little-Refresh_1').click()
            await page.wait_for_load_state('networkidle', timeout=60000)
            await page.wait_for_timeout(1000)

            # Scroll to ensure the strike is visible
            print(f"Attempt {attempt}: Scrolling to find strike {strike_formatted}...")
            for _ in range(5):
                await page.evaluate('''() => {
                    const wrappers = [
                        'div.leftFrame .simplebar-content-wrapper',
                        'div.midFrame .simplebar-content-wrapper',
                        'div.rightFrame .simplebar-content-wrapper'
                    ];
                    wrappers.forEach(sel => {
                        const el = document.querySelector(sel);
                        if (el) {
                            el.scrollTop += 1200;
                            el.dispatchEvent(new Event('scroll'));
                        }
                    });
                }''')
                await page.wait_for_timeout(500)

            # Evaluate the page to extract table data
            print(f"Attempt {attempt}: Evaluating {page_key} for strike {strike_formatted}...")
            snap = await page.evaluate("""(strike) => {
                const getCols = sel => [...document.querySelectorAll(sel + ' table.head td.cell')]
                    .map(td => td.textContent.trim()).filter(Boolean);
                const isBanner = tr => tr.querySelector('td.jss2506, td.jss1115, .banner');
                const rowVals = tr => [...tr.querySelectorAll('td')].map(td => td.querySelector('div.cell'))
                    .filter(Boolean).map(cell => {
                        const v = cell.querySelector('.cellVal span, .cellVal');
                        const t = (v ? v.textContent : cell.textContent).trim();
                        return t || '--';
                    });

                const midRows = [...document.querySelectorAll('div.midFrame tbody.strikes > tr')]
                    .filter(tr => !isBanner(tr));
                const leftRows = [...document.querySelectorAll('div.leftFrame table.body > tbody > tr.row')]
                    .filter(tr => !tr.classList.contains('jss2497'));
                const rightRows = [...document.querySelectorAll('div.rightFrame table.body > tbody > tr.row')]
                    .filter(tr => !tr.classList.contains('jss2497'));

                const calls_cols = getCols('.leftHead');
                const puts_cols = getCols('.rightHead');

                const strikes = midRows.map(tr => {
                    const el = tr.querySelector('td div.cell div.cellVal');
                    return el ? el.textContent.trim() : tr.textContent.trim();
                });

                const calls = leftRows.map(rowVals);
                const puts = rightRows.map(rowVals);

                const idx = strikes.findIndex(s => s === strike);
                return idx >= 0 && idx < calls.length && idx < puts.length 
                    ? { calls_cols, puts_cols, calls: calls[idx], puts: puts[idx], idx } 
                    : null;
            }""", strike_formatted)

            if snap:
                calls = {snap['calls_cols'][j]: snap['calls'][j] for j in range(len(snap['calls_cols']))}
                puts = {snap['puts_cols'][j]: snap['puts'][j] for j in range(len(snap['puts_cols']))}
                print(f"Attempt {attempt}: Successfully extracted data - Calls: {calls}, Puts: {puts}, idx: {snap['idx']}")
                return calls, puts, snap['idx']
            
            print(f"Attempt {attempt}: Strike {strike_formatted} not found, retrying...")
            await asyncio.sleep(2)
        
        except Exception as e:
            print(f"Error during data extraction (Attempt {attempt}) on {page_key}: {e}")
            import traceback
            traceback.print_exc()
            if attempt == max_retries:
                print(f"Failed to extract data for strike {strike_formatted} after {max_retries} attempts")
                raise Exception(f"فشل استخراج البيانات بعد {max_retries} محاولات: {e}")
            await asyncio.sleep(5)
    
    print(f"Strike {strike_formatted} not found after {max_retries} attempts")
    raise Exception(f"الاستريك {strike_formatted} غير موجود بعد {max_retries} محاولات")

async def get_strike_index_only(app: Application, context: ContextTypes.DEFAULT_TYPE | None, use_monitor_browser: bool = False):
    """
    ترجع فقط idx للـ strike المطلوب بدون سحب بيانات جدول Calls/Puts
    """
    page_key = "monitor_page" if use_monitor_browser else "search_page"
    page = app.bot_data.get(page_key)

    if not page or page.is_closed():
        print(f"[get_strike_index_only] {page_key} غير متاح أو مغلق")
        return None

    # تحديد الاستريك حسب السياق
    if use_monitor_browser:
        job = app.bot_data.get('job')
        if not job or 'strike' not in job.data:
            print("[get_strike_index_only] Job أو strike غير موجود في monitor")
            return None
        strike = job.data['strike']
    else:
        if not context:
            print("[get_strike_index_only] context مفقود في وضع البحث")
            return None
        strike = context.user_data.get('strike')

    if not strike:
        print("[get_strike_index_only] لا يوجد strike محدد")
        return None

    strike_formatted = f"{strike[:1]},{strike[1:]}"
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        try:
            print(f"[get_strike_index_only] محاولة {attempt} للعثور على {strike_formatted} في {page_key}")

            # تحريك السكروول قليلاً لتحميل صفوف أكثر
            for _ in range(5):
                await page.evaluate('''() => {
                    const wrappers = [
                        'div.leftFrame .simplebar-content-wrapper',
                        'div.midFrame .simplebar-content-wrapper',
                        'div.rightFrame .simplebar-content-wrapper'
                    ];
                    wrappers.forEach(sel => {
                        const el = document.querySelector(sel);
                        if (el) {
                            el.scrollTop += 1200;
                            el.dispatchEvent(new Event('scroll'));
                        }
                    });
                }''')
                await page.wait_for_timeout(500)

            # قراءة strikes فقط من midFrame بدون بناء calls/puts
            idx = await page.evaluate("""(strike) => {
                const isBanner = tr => tr.querySelector('td.jss2506, td.jss1115, .banner');
                const midRows = [...document.querySelectorAll('div.midFrame tbody.strikes > tr')]
                    .filter(tr => !isBanner(tr));

                const strikes = midRows.map(tr => {
                    const el = tr.querySelector('td div.cell div.cellVal');
                    return el ? el.textContent.trim() : tr.textContent.trim();
                });

                return strikes.findIndex(s => s === strike);
            }""", strike_formatted)

            if isinstance(idx, int) and idx >= 0:
                print(f"[get_strike_index_only] تم العثور على {strike_formatted} عند idx={idx}")
                return idx

            print(f"[get_strike_index_only] لم يتم العثور على {strike_formatted} (محاولة {attempt})، إعادة المحاولة...")
            await asyncio.sleep(2)

        except Exception as e:
            print(f"[get_strike_index_only] خطأ أثناء المحاولة {attempt}: {e}")
            import traceback
            traceback.print_exc()
            if attempt == max_attempts:
                return None
            await asyncio.sleep(5)

    print(f"[get_strike_index_only] فشل العثور على {strike_formatted} بعد {max_attempts} محاولات")
    return None
async def process_strike(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    strike_input: str | None = None,
    contract_type_text: str | None = None,
) -> None:
    
    user_data = context.user_data
    is_company = user_data.get('is_company_mode', False)
    is_index = user_data.get('is_index_mode', False)
    timeframe = user_data.get('timeframe', 'daily') # جلب نوع التوقيت
    
    # تحديد التيكر واسم الرمز
    if is_company:
        target_ticker_id = user_data.get('company_ticker_id')
        symbol_name = user_data.get('selected_company')
        target_root = None 
    elif is_index:
        target_ticker_id = user_data.get('index_ticker_id')
        symbol_name = user_data.get('selected_index')
        target_root = INDEX_ROOT_SYMBOLS.get(symbol_name)
        if symbol_name == "SPX":
            symbol_name = "SPXW"
    else:
        target_ticker_id = TICKER_ID_SPX
        symbol_name = "SPXW"
        target_root = "SPXW"

    if not strike_input:
        strike_input = user_data.get('strike_input') or user_data.get('strike')
    if not strike_input:
        await update.message.reply_text("الرجاء إدخال الاستريك أولاً.")
        return

    strike_str = str(strike_input).strip().replace('$', '')
    try:
        strike_value = float(strike_str)
    except ValueError:
        await update.message.reply_text("الاستريك يجب أن يكون رقمًا صحيحًا.")
        return

    contract_type = None
    if contract_type_text:
        t = contract_type_text.strip().lower()
        if "call" in t or "🟢" in t:
            contract_type = "Calls"
        elif "put" in t or "🔴" in t:
            contract_type = "Puts"

    if not contract_type:
        contract_type = user_data.get('contract_type')

    if contract_type not in ("Calls", "Puts"):
        await update.message.reply_text("الرجاء اختيار نوع العقد (Calls أو Puts).")
        return

    is_calls = (contract_type == "Calls")
    direction = 'c' if is_calls else 'p'

    user_data['strike'] = strike_str
    user_data['contract_type'] = contract_type

    # === تحديد تاريخ الانتهاء بناءً على التوقيت ===
    target_expire_date = None
    use_next_day = False
    
    if timeframe == 'weekly':
        target_expire_date = get_weekly_expire_date()
    elif timeframe == 'monthly':
        target_expire_date = get_monthly_expire_date()
    else:
        # daily
        use_next_day = is_index

    try:
        async with make_client() as cl:
            chain = await fetch_option_chain(cl, target_ticker_id)

            try:
                available_expiries = sorted(set(
                    str(item.get("expireDate") or item.get("expirationDate") or item.get("expire_date"))
                    for item in chain
                    if item.get("expireDate") or item.get("expirationDate") or item.get("expire_date")
                ))

                print(f"[process_strike] timeframe={timeframe}")
                print(f"[process_strike] target_expire_date={target_expire_date}")
                print(f"[process_strike] available_expiries={available_expiries[:30]}")
            except Exception as e:
                print(f"تعذر طباعة تواريخ الانتهاء: {e}")

            contract = find_contract_in_chain(
                chain,
                strike_value,
                direction=direction,
                expire_date=target_expire_date,
                use_next_day_after_close=use_next_day,
                target_root_symbol=target_root
            )
            if not contract:
                await update.message.reply_text(
                    f"تعذر العثور على عقد للاستريك في سلسلة ({timeframe}).\n"
                    f"تاريخ الانتهاء المطلوب: {target_expire_date}\n"
                    f"المؤشر: {user_data.get('selected_index')}\n"
                    f"الجذر المطلوب: {target_root}\n"
                    f"الاستريك: {strike_value}"
                )
                return

            contract_ticker_id = contract["tickerId"]
            expire_date = contract.get("expireDate")
            quote = await fetch_option_quote(cl, contract_ticker_id)

        popup_data = quote_to_popup_data(quote, is_calls=is_calls, symbol_override=symbol_name)
        img_bio = create_image(popup_data, is_calls=is_calls)

        if is_calls:
            user_data['calls_img'] = img_bio
            user_data['calls_popup'] = popup_data
            user_data['puts_img'] = None
            user_data['puts_popup'] = None
        else:
            user_data['puts_img'] = img_bio
            user_data['puts_popup'] = popup_data
            user_data['calls_img'] = None
            user_data['calls_popup'] = None

        user_data['ticker_id'] = contract_ticker_id
        user_data['expire_date'] = expire_date
        user_data['direction'] = (quote.get("direction") or "").lower()

        caption = "🟢 Call 🟢" if is_calls else "🔴 Put 🔴"
        
        # إضافة نص توضيحي للصورة في حال كان أسبوعي أو شهري
        if timeframe == 'weekly':
            caption += "\nعقد أسبوعي"
        elif timeframe == 'monthly':
            caption += "\nعقد شهري"

        await update.message.reply_photo(
            photo=InputFile(img_bio, filename="contract.png"),
            caption=caption
        )

    except Exception as e:
        print(f"Error in process_strike: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text("تعذر جلب بيانات العقد. تأكد من الكوكيز.")
# إنشاء قفل لحماية ملف trades.json
json_lock = threading.Lock()

async def publish_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    user_data = context.user_data

    strike = user_data.get('strike')
    contract_type = user_data.get('contract_type')
    custom_text = user_data.get('custom_text', '')
    include_chart = user_data.get('include_chart', False)
    stop_loss = user_data.get('stop_loss')
    target_groups = user_data.get('target_groups', [])

    settings = get_settings()
    monitor_increase = settings.get('monitor_increase', 0.10)

    print(f"[publish_to_group] استخدام نسبة متابعة من الإعدادات: {monitor_increase}")
    logging.info(f"Starting publish_to_group: strike={strike}, type={contract_type}, groups={target_groups}")

    if not strike:
        await update.message.reply_text(
            "يرجى تحديد الاستريك أولاً باستخدام 'Search for Strike'.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                resize_keyboard=True
            )
        )
        return

    if not target_groups:
        await update.message.reply_text(
            "خطأ: لم يتم تحديد أي جروب لنشر الصفقة.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                resize_keyboard=True
            )
        )
        return

    try:
        img_bio = user_data.get('calls_img' if contract_type == "Calls" else 'puts_img')
        popup_data = user_data.get('calls_popup' if contract_type == "Calls" else 'puts_popup')

        if not img_bio or not popup_data:
            await update.message.reply_text(
                "خطأ: يجب البحث عن الاستريك أولاً للحصول على الصورة والبيانات",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                    resize_keyboard=True
                )
            )
            return

        # === 1. تحديد نوع العقد، التوقيت، والملفات ===
        is_company = user_data.get('is_company_mode', False)
        is_index = user_data.get('is_index_mode', False)
        timeframe = user_data.get('timeframe', 'daily')

        # إضافة البادئة للملفات الأسبوعية والشهرية
        prefix = ""
        if timeframe == 'weekly':
            prefix = "weekly_"
        elif timeframe == 'monthly':
            prefix = "monthly_"

        if is_company:
            ticker_name = user_data.get('selected_company')
            target_json = f"{prefix}company_trades.json"
            target_csv = f"{prefix}company_trades.csv"
            csv_fields = COMPANY_CSV_FIELDNAMES + ['Trade ID']

        elif is_index:
            ticker_name = user_data.get('selected_index')

            if not ticker_name or ticker_name not in INDICES_FILES:
                await update.message.reply_text(
                    "خطأ: لم يتم تحديد ملف المؤشر بشكل صحيح. ارجع للقائمة الرئيسية وحاول مرة أخرى.",
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                        resize_keyboard=True
                    )
                )
                return

            base_json = INDICES_FILES[ticker_name]["json"]
            base_csv = INDICES_FILES[ticker_name]["csv"]
            target_json = f"{prefix}{base_json}"
            target_csv = f"{prefix}{base_csv}"
            csv_fields = CSV_FIELDNAMES + ['Trade ID']

        else:
            ticker_name = "SPX"
            target_json = f"{prefix}trades.json"
            target_csv = f"{prefix}trades.csv"
            csv_fields = CSV_FIELDNAMES + ['Trade ID']

        img_bio.seek(0)
        img_data = img_bio.read()

        if not img_data:
            logging.error("Image BytesIO object is empty")
            await update.message.reply_text(
                "خطأ: الصورة فارغة أو تالفة، يرجى إعادة البحث عن الاستريك",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                    resize_keyboard=True
                )
            )
            return

        img_bio = io.BytesIO(img_data)
        img_bio.seek(0)

        entry_price = safe_float(popup_data['price'])
        stop_loss_price = entry_price - stop_loss if stop_loss is not None else None

        # ──────────────── التحقق من وجود نشر سابق لنفس العقد في نفس اليوم ────────────────
        is_repeat_today = False
        today_date = datetime.now(LOCAL_TZ).date()

        try:
            df = pd.read_csv(target_csv, encoding='utf-8-sig')
            df.columns = df.columns.str.strip()

            strike_column = 'Strike' if is_company else 'SPX Strike'

            if (
                'Date' in df.columns and
                strike_column in df.columns and
                'Type Contract' in df.columns
            ):
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date

                mask = (
                    (df[strike_column].astype(str).str.strip() == str(strike).strip()) &
                    (df['Type Contract'].astype(str).str.strip() == contract_type[:-1]) &
                    (df['Date'] == today_date)
                )

                if mask.any():
                    is_repeat_today = True

        except Exception as e:
            logging.warning(f"تعذر التحقق من التكرار في {target_csv}: {e}")
            is_repeat_today = False

        # ──────────────── بناء الـ caption مع التنبيه ────────────────
        caption = ""

        if is_repeat_today:
            caption += "🔄 "

        caption += f"{'🟢 Call 🟢' if contract_type == 'Calls' else '🔴 Put 🔴'}\n"

        if custom_text:
            caption += f"{custom_text}\n"

        if timeframe == 'weekly':
            tf_label = "الأسبوعي "
        elif timeframe == 'monthly':
            tf_label = "الشهري "
        else:
            tf_label = ""

        caption += (
            f"مراقبة العقد {tf_label}{strike}\n"
            f"\n✨ للإنضمام أضغط هنا 👇\n"
            f"@Spxinfobot"
        )
        if include_chart:
            caption += "\n(مع الشارت)"
        # إرسال الصورة إلى المجموعات
        for group_id in target_groups:
            try:
                await context.bot.send_photo(
                    chat_id=group_id,
                    photo=InputFile(img_bio, filename=f"{contract_type.lower()}.png"),
                    caption=caption
                )
                img_bio.seek(0)
                logging.info(f"Sent photo to group {group_id}")

            except Exception as e:
                logging.error(f"Error sending to group {group_id}: {e}")
                continue

        trade_id = str(uuid.uuid4())
        now_local = datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')

        entry_data = {
            'price': popup_data['price'],
            'open': popup_data['metrics'].get('Open', '--'),
            'mid': popup_data['metrics'].get('Mid', '0.00'),
            'prev close': popup_data['metrics'].get('Prev Close', '0.00'),
            'high': popup_data['metrics'].get('High', '--'),
            'low': popup_data['metrics'].get('Low', '--'),
            'break even': popup_data['metrics'].get('Break Even', '0.00'),
            'change': popup_data['change'],
            'changePerc': popup_data['changePerc'],
            'volume': popup_data['metrics'].get('Volume', '0')
        }

        ticker_id = user_data.get('ticker_id')
        expire_date = user_data.get('expire_date')
        direction_api = user_data.get('direction')

        trade_data = {
            'Trade ID': trade_id,
            'Time': now_local,
            'Strike': strike,
            'Type': contract_type,
            'Entry Price': entry_price,
            'Header': popup_data['header'],
            'Change': popup_data['change'],
            'Change Perc': popup_data['changePerc'],
            'Closed Time': popup_data['closedTime'],
            'SPX Banner': popup_data['spxBanner'],
            'entry_data': entry_data,
            'updates': [],
            'Highest Price': safe_float(popup_data['metrics'].get('High', '0.00')),
            'created_at': now_local,
            'closed_at': None,
            'group_ids': target_groups,
            'ticker_id': ticker_id,
            'expire_date': expire_date,
            'direction_api': direction_api,
            'is_company': is_company,
            'is_index': is_index,
            'ticker_name': ticker_name,
            'timeframe': timeframe
        }

        # === حفظ الصفقة في JSON الخاص بها ===
        trades_json = []

        if os.path.exists(target_json):
            try:
                with json_lock:
                    with open(target_json, 'r', encoding='utf-8') as f:
                        trades_json = json.load(f)

            except Exception as e:
                logging.error(f"Error reading {target_json}: {e}")

        if not any(trade['Trade ID'] == trade_id for trade in trades_json):
            trades_json.append(trade_data)

            try:
                with json_lock:
                    with open(target_json, 'w', encoding='utf-8') as f:
                        json.dump(trades_json, f, ensure_ascii=False, indent=2)

                logging.info(f"Successfully saved trade {trade_id} to JSON ({target_json})")

            except Exception as e:
                logging.error(f"Error saving trade {trade_id} to JSON: {e}")
                await update.message.reply_text(f"خطأ أثناء حفظ بيانات الصفقة في JSON: {e}")
                return

        # === حفظ الصفقة في CSV الخاص بها ===
        try:
            df_existing = pd.read_csv(target_csv)
            next_number = df_existing['Number'].max() + 1 if not df_existing.empty else 1

        except (FileNotFoundError, pd.errors.EmptyDataError):
            next_number = 1

        csv_trade_data = {
            'Number': next_number,
            'Date': datetime.now(LOCAL_TZ).strftime('%Y-%m-%d'),
            'Type Contract': contract_type[:-1],
            'Open': entry_price,
            'High': trade_data['Highest Price'],
            'السعر المحقق': '',
            'الربح بالعقد': '',
            'الخسارة بالعقد': ''
        }

        if is_company:
            csv_trade_data['Ticker'] = ticker_name
            csv_trade_data['Strike'] = strike
        else:
            # المؤشرات و SPX يستخدمون نفس شكل ملف SPX
            csv_trade_data['SPX Strike'] = strike

        try:
            try:
                df = pd.read_csv(target_csv)

            except (FileNotFoundError, pd.errors.EmptyDataError):
                df = pd.DataFrame(columns=csv_fields)

            if 'Trade ID' not in df.columns:
                df['Trade ID'] = ''

            new_row_df = pd.DataFrame([csv_trade_data])
            new_row_df['Trade ID'] = trade_id

            df = pd.concat([df, new_row_df], ignore_index=True)

            df.to_csv(
                target_csv,
                index=False,
                columns=csv_fields,
                encoding='utf-8-sig'
            )

            logging.info(f"Successfully saved trade {trade_id} to CSV ({target_csv})")

        except Exception as e:
            logging.error(f"Error saving trade {trade_id} to CSV: {e}")
            await update.message.reply_text(f"خطأ أثناء حفظ الصفقة في CSV: {e}")
            return

        # -----------------------------------------------------------

        # إضافة الصفقة إلى tracked_contracts
        if 'tracked_contracts' not in app.bot_data:
            app.bot_data['tracked_contracts'] = {}

        contract_key = trade_id

        app.bot_data['tracked_contracts'][contract_key] = {
            'trade_id': trade_id,
            'entry_price': entry_price,
            'last_notified_price': entry_price,
            'monitor_increase': monitor_increase,
            'stop_loss_price': stop_loss_price,
            'group_ids': target_groups,
            'user_id': update.effective_user.id,
            'retry_count': 0,
            'created_at': now_local,

            # حقول Webull للمتابعة عبر API
            'ticker_id': ticker_id,
            'expire_date': expire_date,
            'direction_api': direction_api,
            'strike': strike,
            'contract_type': contract_type,

            # حقول تمييز نوع الصفقة
            'is_company': is_company,
            'is_index': is_index,
            'ticker_name': ticker_name,
            'timeframe': timeframe,
        }

        logging.info(f"Added contract {contract_key} to tracked_contracts")

        # إضافة الصفقة إلى contract_queue مع نفس الحقول
        await app.bot_data['contract_queue'].put({
            'strike': strike,
            'contract_type': contract_type,
            'trade_id': trade_id,
            'entry_price': entry_price,
            'last_notified_price': entry_price,
            'monitor_increase': monitor_increase,
            'stop_loss_price': stop_loss_price,
            'group_ids': target_groups,
            'user_id': update.effective_user.id,
            'retry_count': 0,
            'context': context,
            'created_at': now_local,

            # حقول Webull
            'ticker_id': ticker_id,
            'expire_date': expire_date,
            'direction_api': direction_api,

            # حقول تمييز نوع الصفقة
            'is_company': is_company,
            'is_index': is_index,
            'ticker_name': ticker_name,
            'timeframe': timeframe,
        })

        logging.info(f"Added contract {contract_key} to contract_queue")

        await update.message.reply_text(
            "تم إرسال الصفقة إلى الجروب(ات) المحددة وبدء المتابعة!",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                resize_keyboard=True
            )
        )

    except Exception as e:
        logging.error(f"Error in publish_to_group: {e}", exc_info=True)

        await update.message.reply_text(
            f"خطأ أثناء النشر: {e}",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("العودة إلى القائمة الرئيسية")]],
                resize_keyboard=True
            )
        )
async def check_all_contracts_failed(app: Application, user_id):
    """
    فحص بسيط: هل كل العقود في tracked_contracts فشلت في آخر محاولة؟
    - يستخدم مع Webull API وليس Playwright.
    - يمنع إرسال رسائل كثيرة.
    """
    tracked = app.bot_data.get('tracked_contracts', {})
    failed = app.bot_data.get('failed_contracts', {})

    if not tracked:
        return

    # إذا عدد الفاشلين = عدد العقود → يوجد مشكلة عامة
    if len(failed) >= len(tracked):
        # إرسال تحذير للمستخدم مرة واحدة فقط خلال 3 دقائق
        last_warn = app.bot_data.get("last_global_fail_warning")
        now = datetime.now()

        if not last_warn or (now - last_warn).total_seconds() > 180:
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ مشكلة في الاتصال مع Webull API\nسيتم إعادة المحاولة تلقائياً.",
                )
            except:
                pass

            app.bot_data["last_global_fail_warning"] = now

        # إعادة المحاولة عبر إعادة تعبئة العقد إلى الطابور
        for ck, contract in tracked.items():
            await app.bot_data['contract_queue'].put(contract)

        # تفريغ الفشل بعد المعالجة
        app.bot_data['failed_contracts'] = {}


async def monitor_contracts_queue(app: Application):
    """
    حلقة خلفية تسحب العقود من contract_queue
    وتستدعي monitor_contract(app, contract) لكل عقد.
    """
    while True:
        try:
            # انتظار عقد جديد في الطابور
            contract = await app.bot_data['contract_queue'].get()

            try:
                # متابعة العقد (الدالة نفسها فيها sleep(10) للدورة)
                await monitor_contract(app, contract)
            finally:
                # تعليم أن هذا العقد تمّت معالجته
                app.bot_data['contract_queue'].task_done()

        except asyncio.CancelledError:
            print("Queue processing cancelled")
            break

        except Exception as e:
            print(f"Unexpected error in monitor_contracts_queue: {e}")
            import traceback
            traceback.print_exc()
            # في حال خطأ عام، انتظر قليلًا ثم تابع
            await asyncio.sleep(5)

async def _parse_num(s: str) -> float:
    try:
        return float(s.replace(',', '').strip())
    except:
        return float('nan')

async def _visible_strike_range(page):
    # يقرأ أول/آخر/أقرب صف للمنتصف
    data = await page.evaluate("""() => {
        const rows = [...document.querySelectorAll('div.midFrame tbody.strikes > tr')];
        const vals = rows.map(tr => {
            const el = tr.querySelector('td div.cell div.cellVal') || tr;
            const t = (el.textContent||'').trim();
            return t.replace(/[^0-9,]/g,'');
        }).filter(Boolean);
        // حدد صف قريب من منتصف الشاشة لقياس الحركة
        const midY = window.scrollY + window.innerHeight/2;
        let center = null, best = 1e9;
        rows.forEach((tr,i)=>{
          const r = tr.getBoundingClientRect();
          const cy = r.top + window.scrollY + r.height/2;
          const d = Math.abs(cy - midY);
          if (d < best) {best=d; center = i;}
        });
        return { first: vals[0]||null, last: vals.at(-1)||null, center: vals[center]||null, count: vals.length||0 };
    }""")
    return data  # {'first': '6,420', 'last':'6,680', 'center':'6,550', 'count': n}

async def _arrow_click(page, direction: str, times: int):
    # direction: 'left' أو 'right'
    # نحاول إيجاد آيقونة السهم. بدائل متعددة حسب نسخة الواجهة.
    await page.evaluate("""({dir, times})=>{
        const pick = () => {
          const q = (sel)=>document.querySelector(sel);
          // شيوعًا في Webull:
          let btn = q('i[class*="webull-arrow_left_"]');
          let brn = q('i[class*="webull-arrow_right_"]');
          if (!btn || !brn) {
            // بدائل
            btn = btn || [...document.querySelectorAll('i')].find(i => (i.className||'').includes('left'));
            brn = brn || [...document.querySelectorAll('i')].find(i => (i.className||'').includes('right'));
          }
          return {left: btn, right: brn};
        };
        const {left, right} = pick();
        const target = dir === 'left' ? left : right;
        if (!target) return;

        for (let k=0; k<times; k++){
          target.dispatchEvent(new MouseEvent('click', {bubbles:true}));
        }
    }""", {"dir": direction, "times": times})

async def fast_seek_strike(page, target_strike: str, hard_timeout_ms: int = 12000):
    import time, math
    target_val = await _parse_num(target_strike)
    t0 = time.time()*1000

    # دفعات تكيفية: كبيرة ثم أصغر
    bursts = [64, 32, 16, 8, 4, 2, 1]
    last_center = None

    while True:
        if (time.time()*1000 - t0) > hard_timeout_ms:
            raise Exception("انتهى وقت البحث عن الاستريك")

        vr = await _visible_strike_range(page)
        if not vr or not vr.get('count',0):
            await page.wait_for_timeout(100)
            continue

        first = await _parse_num(vr['first'] or 'NaN')
        last  = await _parse_num(vr['last']  or 'NaN')
        center= await _parse_num(vr['center'] or 'NaN')

        # داخل المدى الحالي
        if first <= target_val <= last:
            # ابنِ فهرس مؤقت وحدد الصف
            idx = await page.evaluate("""(t)=>{
                const rows = [...document.querySelectorAll('div.midFrame tbody.strikes > tr')];
                let hit = -1;
                for (let i=0;i<rows.length;i++){
                   const el = rows[i].querySelector('td div.cell div.cellVal') || rows[i];
                   const txt = (el.textContent||'').trim().replace(/[^0-9,]/g,'');
                   const a = txt.replace(/,/g,'');
                   if (a === t) { hit = i; break; }
                }
                return hit;
            }""", target_strike)
            if idx >= 0:
                # نوحّد الإطارين الثلاثة على هذا الصف
                await page.evaluate("""(i)=>{
                    const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
                    const wrap = s=>document.querySelector(s);
                    const m=wrap('div.midFrame .simplebar-content-wrapper');
                    const l=wrap('div.leftFrame .simplebar-content-wrapper');
                    const r=wrap('div.rightFrame .simplebar-content-wrapper');
                    const mRows=[...document.querySelectorAll('div.midFrame tbody.strikes > tr')];
                    const lRows=[...document.querySelectorAll('div.leftFrame  table.body > tbody > tr.row')];
                    const rRows=[...document.querySelectorAll('div.rightFrame table.body > tbody > tr.row')];
                    const mt=mRows[i], lt=lRows[i], rt=rRows[i];
                    if (m && mt) m.scrollTop = clamp(mt.offsetTop-60,0,m.scrollHeight);
                    if (l && lt) l.scrollTop = clamp(lt.offsetTop-60,0,l.scrollHeight);
                    if (r && rt) r.scrollTop = clamp(rt.offsetTop-60,0,r.scrollHeight);
                }""", idx)
                return idx
            # لم يُرسم الصف بعد رغم أنه ضمن المدى: مهلة قصيرة وأعد المحاولة
            await page.wait_for_timeout(60)
            continue

        # حدّد الاتجاه
        direction = 'left' if target_val < first else 'right'
        # تقدير المسافة بالقيمة لتحديد حجم الدفعة
        dist = min(abs(target_val - first), abs(target_val - last))
        # اختر burst
        step = bursts[0]
        if   dist > 400: step = bursts[0]
        elif dist > 200: step = bursts[1]
        elif dist > 120: step = bursts[2]
        elif dist > 60 : step = bursts[3]
        elif dist > 30 : step = bursts[4]
        elif dist > 10 : step = bursts[5]
        else:            step = bursts[6]

        await _arrow_click(page, direction, step)

        # انتظر تغيّر المركز فقط، لا networkidle
        changed = await page.wait_for_function(
            """(prev)=>{
                const rows = [...document.querySelectorAll('div.midFrame tbody.strikes > tr')];
                if (!rows.length) return false;
                const midY = window.scrollY + window.innerHeight/2;
                let center = null, best = 1e9;
                rows.forEach((tr,i)=>{
                  const r = tr.getBoundingClientRect();
                  const cy = r.top + window.scrollY + r.height/2;
                  const d = Math.abs(cy - midY);
                  if (d<best){best=d; center = i;}
                });
                const el = rows[center]?.querySelector('td div.cell div.cellVal') || rows[center];
                const cur = (el?.textContent||'').trim();
                return cur !== prev;
            }""",
            arg=vr['center'],
            timeout=2000
        ).catch(lambda _: None)

        # لو لم يتغير شيء، جرّب دفعة أصغر سريعًا
        if not changed:
            await _arrow_click(page, direction, max(1, step//2))
            await page.wait_for_timeout(40)


async def monitor_contract(app: Application, contract: dict):
    """
    متابعة عقود المؤشرات فقط:
    - يومي
    - أسبوعي
    - شهري

    هذه الدالة لا تلمس ملفات الشركات نهائياً.
    """

    max_retries = 15

    try:
        strike = contract['strike']
        contract_type = contract['contract_type']
        trade_id = contract['trade_id']
        entry_price = safe_float(contract['entry_price'])
        monitor_increase = safe_float(contract['monitor_increase'])
        stop_loss_price = contract.get('stop_loss_price')
        stop_loss_price = safe_float(stop_loss_price) if stop_loss_price is not None else None
        group_ids = contract.get('group_ids', [])
        user_id = contract.get('user_id')
        retry_count = contract.get('retry_count', 0)
        created_at = contract.get('created_at')

    except Exception as e:
        print(f"❌ بيانات العقد ناقصة داخل monitor_contract: {e}")
        return

    contract_key = trade_id

    tracked_contracts = app.bot_data.get('tracked_contracts', {})
    tracked_data = tracked_contracts.get(contract_key)

    if not tracked_data:
        print(f"ℹ️ العقد غير موجود في tracked_contracts، تخطي: {contract_key}")
        return

    # حماية مهمة جداً: هذا بوت مؤشرات فقط
    if contract.get('is_company', False) or tracked_data.get('is_company', False):
        print(f"⛔ تم تخطي صفقة شركة داخل بوت المؤشرات: {trade_id}")
        tracked_contracts.pop(contract_key, None)
        return

    # === المتغيرات الذكية للملفات والتوقيت: مؤشرات فقط ===
    ticker_name = (
        contract.get('ticker_name') or
        tracked_data.get('ticker_name') or
        "SPX"
    )

    timeframe = (
        contract.get('timeframe') or
        tracked_data.get('timeframe') or
        "daily"
    )

    if timeframe not in ["daily", "weekly", "monthly"]:
        timeframe = "daily"

    prefix = ""
    if timeframe == "weekly":
        prefix = "weekly_"
    elif timeframe == "monthly":
        prefix = "monthly_"

    # === تحديد ملفات المؤشر فقط ===
    index_file_data = INDICES_FILES.get(ticker_name)

    if not index_file_data:
        # احتياطي SPX القديم فقط، بدون شركات
        if ticker_name == "SPX":
            try:
                base_json = TRADES_JSON
                base_csv = TRADES_CSV
            except NameError:
                print("❌ لم يتم العثور على SPX داخل INDICES_FILES ولا توجد TRADES_JSON / TRADES_CSV")
                tracked_contracts.pop(contract_key, None)
                return
        else:
            print(f"❌ المؤشر {ticker_name} غير موجود داخل INDICES_FILES")
            tracked_contracts.pop(contract_key, None)
            return
    else:
        base_json = index_file_data["json"]
        base_csv = index_file_data["csv"]

    target_json = f"{prefix}{base_json}"
    target_csv = f"{prefix}{base_csv}"

    target_ticker_id = INDICES_TICKERS.get(ticker_name)

    if not target_ticker_id:
        if ticker_name == "SPX":
            target_ticker_id = 913354362
        else:
            print(f"❌ لا يوجد ticker_id للمؤشر {ticker_name} داخل INDICES_TICKERS")
            tracked_contracts.pop(contract_key, None)
            return

    target_root = INDEX_ROOT_SYMBOLS.get(
        ticker_name,
        "SPXW" if ticker_name == "SPX" else ticker_name
    )

    symbol_for_image = target_root if target_root == "SPXW" else ticker_name

    strike_formatted = (
        f"{strike[:1]},{strike[1:]}"
        if isinstance(strike, str) and len(strike) > 1
        else str(strike)
    )

    print(
        f"[monitor_contract] متابعة مؤشر فقط: {strike_formatted} ({contract_type}) "
        f"| Ticker: {ticker_name} | Timeframe: {timeframe} | ID: {trade_id}"
    )

    def read_trades_json():
        trades = []

        if os.path.exists(target_json):
            try:
                with open(target_json, 'r', encoding='utf-8') as f:
                    trades = json.load(f)

            except Exception as e:
                print(f"❌ خطأ قراءة JSON {target_json}: {e}")
                trades = []

        return trades

    def save_trades_json(trades):
        tmp_path = target_json + ".tmp"

        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(trades, f, ensure_ascii=False, indent=2)

        os.replace(tmp_path, target_json)

    def safe_num(value, default=0.0):
        try:
            n = safe_float(value)

            if n is None:
                return default

            try:
                if pd.isna(n):
                    return default
            except Exception:
                pass

            return float(n)

        except Exception:
            return default

    # لو الصفقة مغلقة مسبقاً أو شركة بالخطأ داخل JSON، لا نتابعها
    with json_lock:
        trades_json = read_trades_json()

        existing_trade = next(
            (
                t for t in trades_json
                if str(t.get('Trade ID', '')).strip() == str(trade_id).strip()
            ),
            None
        )

        if existing_trade:
            if existing_trade.get('closed_at'):
                print(f"ℹ️ الصفقة مغلقة مسبقاً، إزالة من المتابعة: {trade_id}")
                tracked_contracts.pop(contract_key, None)
                return

            if existing_trade.get('is_company', False):
                print(f"⛔ صفقة شركة موجودة بالخطأ داخل ملفات المؤشرات، تخطي: {trade_id}")
                tracked_contracts.pop(contract_key, None)
                return

    now = datetime.now(LOCAL_TZ)

    async def fetch_popup_with_retry() -> dict:
        last_error = None

        for attempt in range(2):
            try:
                async with make_client() as cl:
                    ticker_id = (
                        contract.get('ticker_id') or
                        tracked_data.get('ticker_id')
                    )

                    expire_date = (
                        contract.get('expire_date') or
                        tracked_data.get('expire_date')
                    )

                    if not ticker_id:
                        direction = 'c' if contract_type == "Calls" else 'p'

                        chain = await fetch_option_chain(cl, target_ticker_id)

                        found = find_contract_in_chain(
                            chain,
                            float(str(strike).replace(",", "")),
                            direction=direction,
                            expire_date=expire_date,
                            use_next_day_after_close=False,
                            target_root_symbol=target_root
                        )

                        if not found:
                            raise RuntimeError(
                                f"لم يتم العثور على العقد في السلسلة: "
                                f"{ticker_name} {strike} {contract_type}"
                            )

                        ticker_id = found.get("tickerId")

                        if not ticker_id:
                            raise RuntimeError("تم العثور على العقد لكن بدون tickerId")

                        tracked_data['ticker_id'] = ticker_id
                        contract['ticker_id'] = ticker_id

                        if 'expireDate' in found:
                            tracked_data['expire_date'] = found['expireDate']
                            contract['expire_date'] = found['expireDate']

                    quote = await fetch_option_quote(cl, int(ticker_id))

                    popup = quote_to_popup_data(
                        quote,
                        is_calls=(contract_type == "Calls"),
                        symbol_override=symbol_for_image
                    )

                    un_symbol = (
                        quote.get("unSymbol") or
                        quote.get("underlyingSymbol") or
                        ""
                    ).upper()

                    # لا نرفض لو Webull لم يرجع unSymbol، نرفض فقط لو رجع رمز مختلف
                    if target_root and un_symbol and un_symbol != target_root.upper():
                        raise RuntimeError(
                            f"العقد المجلوب غير مطابق للجذر المطلوب. "
                            f"المطلوب={target_root} / الموجود={un_symbol}"
                        )

                    if not popup or not popup.get('price'):
                        raise RuntimeError("بيانات العقد غير مكتملة أو السعر غير موجود.")

                    return popup

            except Exception as e:
                last_error = e
                print(f"⚠️ محاولة جلب بيانات العقد فشلت [{attempt + 1}/2]: {e}")

                if attempt == 0:
                    await asyncio.sleep(2)

        raise RuntimeError(str(last_error))

    async def update_csv_trade(current_price, is_stop_loss=False):
        async with csv_lock:
            try:
                if not os.path.exists(target_csv):
                    print(f"⚠️ ملف CSV غير موجود أثناء التحديث: {target_csv}")
                    return

                df = pd.read_csv(target_csv, encoding='utf-8-sig')
                df.columns = df.columns.str.strip()

                if "Trade ID" not in df.columns:
                    print(f"⚠️ لا يوجد Trade ID داخل {target_csv}")
                    return

                for col in ['السعر المحقق', 'High', 'الربح بالعقد', 'الخسارة بالعقد']:
                    if col not in df.columns:
                        df[col] = pd.NA

                df["Trade ID"] = df["Trade ID"].astype(str).str.strip()
                mask = df["Trade ID"] == str(trade_id).strip()

                if not mask.any():
                    print(f"⚠️ لم يتم العثور على الصفقة داخل CSV: {trade_id}")
                    return

                df.loc[mask, "السعر المحقق"] = f"{current_price:.2f}"

                old_high = safe_num(df.loc[mask, "High"].values[0], default=0.0)

                if current_price > old_high:
                    df.loc[mask, "High"] = f"{current_price:.2f}"

                net = (current_price - entry_price) * 100

                if is_stop_loss:
                    df.loc[mask, "الخسارة بالعقد"] = f"{abs(net):.2f}"
                    df.loc[mask, "الربح بالعقد"] = pd.NA

                else:
                    if net >= 0:
                        df.loc[mask, "الربح بالعقد"] = f"{net:.2f}"
                        df.loc[mask, "الخسارة بالعقد"] = pd.NA
                    else:
                        df.loc[mask, "الخسارة بالعقد"] = f"{abs(net):.2f}"
                        df.loc[mask, "الربح بالعقد"] = pd.NA

                df.to_csv(target_csv, index=False, encoding='utf-8-sig')
                print(f"✅ تم تحديث CSV للصفقة {trade_id} داخل {target_csv}")

            except Exception as e:
                print(f"❌ خطأ تحديث CSV للصفقة {trade_id}: {e}")

    def update_json_trade(current_price, popup_data, is_stop_loss=False):
        with json_lock:
            try:
                trades_json = read_trades_json()

                updated = False

                for trade in trades_json:
                    if str(trade.get('Trade ID', '')).strip() == str(trade_id).strip():
                        net = (current_price - entry_price) * 100

                        trade['السعر المحقق'] = f"{current_price:.2f}"
                        trade['Highest Notified Price'] = f"{max(current_price, safe_num(trade.get('Highest Notified Price', 0))):.2f}"
                        trade['timeframe'] = timeframe
                        trade['ticker_name'] = ticker_name
                        trade['is_index'] = True
                        trade['is_company'] = False

                        if is_stop_loss:
                            trade['Loss'] = f"{abs(net):.2f}"
                            trade['closed_at'] = now.strftime('%Y-%m-%d %H:%M:%S')

                            if 'Profit' in trade:
                                trade.pop('Profit', None)

                        else:
                            update_record = {
                                'time': now.strftime('%Y-%m-%d %H:%M:%S'),
                                'notified_price': f"{current_price:.2f}",
                                'price': popup_data.get('price'),
                                'header': popup_data.get('header'),
                                'change': popup_data.get('change'),
                                'changePerc': popup_data.get('changePerc'),
                                'closedTime': popup_data.get('closedTime'),
                                'spxBanner': popup_data.get('spxBanner'),
                                'metrics': popup_data.get('metrics', {}),
                            }

                            trade.setdefault('updates', []).append(update_record)

                        updated = True
                        break

                if updated:
                    save_trades_json(trades_json)
                    print(f"✅ تم تحديث JSON للصفقة {trade_id} داخل {target_json}")
                else:
                    print(f"⚠️ لم يتم العثور على الصفقة داخل JSON: {trade_id}")

            except Exception as e:
                print(f"❌ خطأ تحديث JSON للصفقة {trade_id}: {e}")

    try:
        popup_data = await fetch_popup_with_retry()

        current_price = safe_num(popup_data.get('price'), default=None)

        if current_price is None:
            raise RuntimeError("تعذر تحويل السعر الحالي إلى رقم.")

        last_notified_price = safe_num(
            tracked_data.get('last_notified_price', entry_price),
            default=entry_price
        )

        # ===================== وقف الخسارة =====================
        if stop_loss_price is not None and current_price <= stop_loss_price:
            print(f"🛑 تحقق وقف الخسارة للصفقة {trade_id}: current={current_price}, stop={stop_loss_price}")

            img_bio = create_image(
                popup_data,
                is_calls=(contract_type == "Calls"),
                use_right_panel_background=False
            )

            loss_amount = (entry_price - current_price) * 100

            update_json_trade(
                current_price=current_price,
                popup_data=popup_data,
                is_stop_loss=True
            )

            await update_csv_trade(
                current_price=current_price,
                is_stop_loss=True
            )

            caption = (
                f"وقف خسارة 🛑\n"
                f"المؤشر: {ticker_name}\n"
                f"الاستريك: {strike}\n"
                f"الدخول: {entry_price:.2f}\n"
                f"السعر الحالي: {current_price:.2f}\n"
                f"الخسارة: {abs(loss_amount):.2f} دولار"
            )

            for group_id in group_ids:
                try:
                    img_bio.seek(0)

                    await app.bot.send_photo(
                        chat_id=group_id,
                        photo=InputFile(img_bio, filename="stop_loss.png"),
                        caption=caption
                    )

                except Exception as e:
                    print(f"❌ فشل إرسال وقف الخسارة إلى {group_id}: {e}")

            tracked_contracts.pop(contract_key, None)
            return

        # ===================== تحديث الربح =====================
        price_diff = current_price - last_notified_price

        if price_diff >= monitor_increase and current_price > last_notified_price:
            print(
                f"📈 تحديث ربح للصفقة {trade_id}: "
                f"last={last_notified_price}, current={current_price}, diff={price_diff}"
            )

            img_bio = create_image(
                popup_data,
                is_calls=(contract_type == "Calls"),
                entry_price=entry_price,
                peak_price=current_price,
                use_right_panel_background=True
            )

            caption = (
                "⚠️ إدارة الأرباح أهم من الطمع\n"
                "يفضّل تأمين الصفقة والخروج عند +100$ ربح على الأقل 🔒💵\n\n"
                "✨ للإنضمام أضغط هنا 👇\n"
                "@Spxinfobot"
            )

            for group_id in group_ids:
                try:
                    img_bio.seek(0)

                    await app.bot.send_photo(
                        chat_id=group_id,
                        photo=InputFile(img_bio, filename="update.png"),
                        caption=caption
                    )

                except Exception as e:
                    print(f"❌ فشل إرسال تحديث الربح إلى {group_id}: {e}")

            tracked_contracts[contract_key]['last_notified_price'] = current_price
            tracked_contracts[contract_key]['retry_count'] = 0
            tracked_contracts[contract_key]['timeframe'] = timeframe
            tracked_contracts[contract_key]['ticker_name'] = ticker_name
            tracked_contracts[contract_key]['is_index'] = True
            tracked_contracts[contract_key]['is_company'] = False

            contract['last_notified_price'] = current_price
            contract['retry_count'] = 0
            contract['timeframe'] = timeframe
            contract['ticker_name'] = ticker_name
            contract['is_index'] = True
            contract['is_company'] = False

            await update_csv_trade(
                current_price=current_price,
                is_stop_loss=False
            )

            update_json_trade(
                current_price=current_price,
                popup_data=popup_data,
                is_stop_loss=False
            )

        else:
            # نجاح في الجلب بدون تحديث
            tracked_contracts[contract_key]['retry_count'] = 0
            contract['retry_count'] = 0

        # إعادة العقد للطابور طالما لم يُغلق
        if contract_key in tracked_contracts:
            await app.bot_data['contract_queue'].put(contract)

        await asyncio.sleep(1)

    except Exception as e:
        retry_count += 1

        print(
            f"❌ خطأ متابعة العقد {trade_id} | "
            f"المحاولة {retry_count}/{max_retries}: {e}"
        )

        if contract_key in tracked_contracts:
            tracked_contracts[contract_key]['retry_count'] = retry_count

        if retry_count < max_retries:
            contract['retry_count'] = retry_count

            if contract_key in tracked_contracts:
                await app.bot_data['contract_queue'].put(contract)

            await asyncio.sleep(1)

        else:
            print(f"🛑 تم إيقاف متابعة العقد بعد {max_retries} محاولات: {trade_id}")
            tracked_contracts.pop(contract_key, None)
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Asia/Riyadh")  # غيّرها إن لزم

def _parse_local(dt_str: str) -> datetime | None:
    try:
        # Time حفظته بدون TZ؛ اعتبره محليًا
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=LOCAL_TZ)
    except Exception:
        try:
            # fallback لتواريخ فقط
            return datetime.strptime(dt_str, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
        except Exception:
            return None

def _is_today_local(dt_str: str) -> bool:
    d = _parse_local(dt_str)
    if not d: 
        return False
    today = datetime.now(LOCAL_TZ).date()
    return d.date() == today

def format_duration_arabic(start_str: str, end_str: str) -> str:
    try:
        fmt = "%Y-%m-%d %H:%M:%S"
        start = datetime.strptime(start_str, fmt).replace(tzinfo=LOCAL_TZ)
        end = datetime.strptime(end_str, fmt).replace(tzinfo=LOCAL_TZ)
        delta = end - start
        if delta.total_seconds() < 60:
            return "أقل من دقيقة"
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        if hours == 0:
            return f"{minutes} دقيقة" if minutes <= 10 else f"{minutes} دقيقة"
        elif minutes == 0:
            return f"{hours} ساعة" if hours <= 10 else f"{hours} ساعة"
        else:
            return f"{hours} ساعة و {minutes} دقيقة"
    except:
        return "--"

from datetime import datetime, timedelta
SUMMARY_BG_PATH = r'C:\Users\Administrator\Desktop\talal\camel_spx_summary_bg.jpeg'


import asyncio
from datetime import datetime, timedelta
import json
import os
import pandas as pd
from PIL import Image
import io
# باقي الـ imports اللي موجودة عندك (مثل ContextTypes, json_lock, safe_float, create_image, إلخ)
def get_indices_trade_file_configs():
    """
    تجهيز ملفات المؤشرات فقط:
    - يومي
    - أسبوعي
    - شهري

    لا يتم إضافة أي ملف خاص بالشركات هنا نهائياً.
    """

    configs = []
    seen_csv_files = set()

    def add_config(csv_file, json_file, fieldnames, ticker_display, timeframe):
        if not csv_file or not json_file:
            return

        if csv_file in seen_csv_files:
            return

        seen_csv_files.add(csv_file)

        configs.append({
            "csv_file": csv_file,
            "json_file": json_file,
            "fieldnames": fieldnames,
            "ticker_display": ticker_display,
            "timeframe": timeframe,
        })

    # ملفات المؤشرات من INDICES_FILES فقط
    try:
        for ticker_name, f_data in INDICES_FILES.items():
            base_csv = f_data["csv"]
            base_json = f_data["json"]

            add_config(
                base_csv,
                base_json,
                CSV_FIELDNAMES,
                ticker_name,
                "daily"
            )

            add_config(
                f"weekly_{base_csv}",
                f"weekly_{base_json}",
                CSV_FIELDNAMES,
                ticker_name,
                "weekly"
            )

            add_config(
                f"monthly_{base_csv}",
                f"monthly_{base_json}",
                CSV_FIELDNAMES,
                ticker_name,
                "monthly"
            )

    except Exception as e:
        print(f"⚠️ تعذر تجهيز ملفات INDICES_FILES: {e}")

    # احتياطي لملف SPX القديم فقط، لأنه مؤشر وليس شركة
    try:
        add_config(
            TRADES_CSV,
            TRADES_JSON,
            CSV_FIELDNAMES,
            "SPX",
            "daily"
        )

        add_config(
            f"weekly_{TRADES_CSV}",
            f"weekly_{TRADES_JSON}",
            CSV_FIELDNAMES,
            "SPX",
            "weekly"
        )

        add_config(
            f"monthly_{TRADES_CSV}",
            f"monthly_{TRADES_JSON}",
            CSV_FIELDNAMES,
            "SPX",
            "monthly"
        )

    except NameError:
        pass

    return configs


async def clean_profit_loss_columns_for_today(context: ContextTypes.DEFAULT_TYPE):
    print("🧹 بدء تنظيف أعمدة الربح/الخسارة للصفقات المفتوحة للمؤشرات فقط...")

    tracked_contracts = context.application.bot_data.get('tracked_contracts', {})
    if not tracked_contracts:
        return

    # نأخذ فقط صفقات المؤشرات، ونستبعد أي صفقة شركة احتياطياً
    open_trade_ids = {
        str(data.get('trade_id')).strip()
        for data in tracked_contracts.values()
        if data.get('trade_id') and not data.get('is_company', False)
    }

    if not open_trade_ids:
        return

    files_configs = get_indices_trade_file_configs()

    all_csv_files = {
        cfg["csv_file"]
        for cfg in files_configs
        if cfg.get("csv_file")
    }

    for csv_file in all_csv_files:
        try:
            if not csv_file or not os.path.exists(csv_file):
                continue

            df = pd.read_csv(csv_file, encoding='utf-8-sig')
            df.columns = df.columns.str.strip()

            if 'Trade ID' not in df.columns:
                continue

            df['Trade ID'] = df['Trade ID'].astype(str).str.strip()

            mask_to_clean = df['Trade ID'].isin(open_trade_ids)

            if mask_to_clean.any():
                for col in ['الربح بالعقد', 'الخسارة بالعقد', 'السعر المحقق', 'High']:
                    if col in df.columns:
                        df.loc[mask_to_clean, col] = pd.NA

                df.to_csv(csv_file, index=False, encoding='utf-8-sig')
                print(f"✅ تم تنظيف الصفقات المفتوحة في ملف المؤشر: {csv_file}")

        except Exception as e:
            print(f"❌ خطأ أثناء تنظيف {csv_file}: {e}")


async def close_trades_today(context: ContextTypes.DEFAULT_TYPE):
    print(f"\n------------ [ بدء الإغلاق الشامل للمؤشرات فقط ] ------------")
    print(f"الوقت الحالي: {datetime.now(LOCAL_TZ).isoformat()}")

    print("⏳ انتظار 5 ثواني قبل تنظيف الأعمدة وبدء الإغلاق...")
    await asyncio.sleep(5)

    await clean_profit_loss_columns_for_today(context)

    public_delay_minutes = 5

    try:
        if os.path.exists("settings.json"):
            with open("settings.json", 'r', encoding='utf-8') as f:
                settings = json.load(f)
                public_delay_minutes = settings.get("public_delay_minutes", 5)

    except Exception as e:
        print(f"⚠️ تعذر قراءة settings.json، سيتم استخدام 5 دقائق: {e}")

    def build_popup(header, change, changePerc, closed_time, spx_banner, dct):
        def g(k, default='--'):
            if not dct:
                return default

            if k in dct:
                return dct.get(k, default)

            k_lower = str(k).lower()

            if k_lower in dct:
                return dct.get(k_lower, default)

            aliases = {
                'Prev Close': ['prev close', 'prev_close'],
                'Break Even': ['break even', 'break_even'],
                'Open Int': ['open int', 'open_int'],
                'Volume': ['volume'],
                'Open': ['open'],
                'Mid': ['mid'],
                'High': ['high'],
                'Low': ['low'],
                'price': ['price'],
            }

            for alt in aliases.get(k, []):
                if alt in dct:
                    return dct.get(alt, default)

            return default

        metrics = {
            'Open': g('Open'),
            'Mid': g('Mid', '0.00'),
            'Prev Close': g('Prev Close', '0.00'),
            'High': g('High', '--'),
            'Low': g('Low', '--'),
            'Break Even': g('Break Even', '0.00'),
            'Open Int': g('Open Int', '--'),
            'Volume': g('Volume', '0'),
        }

        return {
            'header': header,
            'price': g('price', '0.00'),
            'change': change,
            'changePerc': changePerc,
            'closedTime': closed_time,
            'spxBanner': spx_banner,
            'metrics': metrics
        }

    files_configs = get_indices_trade_file_configs()

    closed_contracts_keys = []
    sent_reports_count = 0

    now = datetime.now(LOCAL_TZ)
    today_local = now.date()
    yesterday_local = today_local - timedelta(days=1)
    send_public_at = now + timedelta(minutes=public_delay_minutes)

    PUBLIC_GROUP_ID = os.getenv('TELEGRAM_PUBLIC_GROUP_ID', '')

    for file_cfg in files_configs:
        csv_file = file_cfg["csv_file"]
        json_file = file_cfg["json_file"]
        fieldnames = file_cfg["fieldnames"]
        ticker_display = file_cfg["ticker_display"]
        timeframe = file_cfg["timeframe"]

        if timeframe == "daily":
            timeframe_label = "اليومية"
        elif timeframe == "weekly":
            timeframe_label = "الأسبوعية"
        elif timeframe == "monthly":
            timeframe_label = "الشهرية"
        else:
            timeframe_label = "اليومية"

        if not os.path.exists(csv_file):
            print(f"ℹ️ ملف المؤشر غير موجود، تخطي: {csv_file}")
            continue

        try:
            trades_df = pd.read_csv(
                csv_file,
                encoding='utf-8-sig',
                dtype={'Trade ID': str}
            )

            trades_df.columns = trades_df.columns.str.strip()

            if 'Date' not in trades_df.columns:
                print(f"⚠️ لا يوجد عمود Date في {csv_file}")
                continue

            if 'Trade ID' not in trades_df.columns:
                print(f"⚠️ لا يوجد عمود Trade ID في {csv_file}")
                continue

            for col in ['الربح بالعقد', 'الخسارة بالعقد', 'السعر المحقق', 'High']:
                if col not in trades_df.columns:
                    trades_df[col] = pd.NA

            trades_df['Date_dt'] = pd.to_datetime(trades_df['Date'], errors='coerce')
            trades_df['Date_only'] = trades_df['Date_dt'].dt.date

            profit_empty = trades_df['الربح بالعقد'].replace('', pd.NA).isna()
            loss_empty = trades_df['الخسارة بالعقد'].replace('', pd.NA).isna()

            open_mask = profit_empty & loss_empty

            if timeframe == 'daily':
                mask_target = (
                    (
                        (trades_df['Date_only'] == today_local) |
                        (trades_df['Date_only'] == yesterday_local)
                    ) &
                    open_mask
                )
            else:
                # الأسبوعي والشهري نأخذ الصفقات المفتوحة فقط
                # ثم نتحقق من expire_date داخل JSON قبل الإغلاق
                mask_target = open_mask

            if not mask_target.any():
                print(f"ℹ️ لا توجد صفقات مؤشرات مفتوحة للإغلاق في {csv_file}")
                continue

            open_trades_df = trades_df[mask_target].copy()
            print(f"→ سيتم فحص {len(open_trades_df)} صفقة مؤشرات في {csv_file}")

        except Exception as e:
            print(f"❌ خطأ أثناء معالجة ملف المؤشر {csv_file}: {e}")
            continue

        trades_json = []

        if os.path.exists(json_file):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    trades_json = json.load(f)

            except Exception as e:
                print(f"❌ خطأ قراءة {json_file}: {e}")
                trades_json = []

        def jfind(trade_id):
            return next(
                (
                    t for t in trades_json
                    if str(t.get('Trade ID', '')).strip() == str(trade_id).strip()
                ),
                None
            )

        for idx, row in open_trades_df.iterrows():
            trade_id = str(row.get('Trade ID', '')).strip()

            if not trade_id or trade_id.lower() == "nan":
                continue

            j_data = jfind(trade_id)

            if not j_data:
                print(f"⚠️ لم يتم العثور على صفقة المؤشر في JSON: {trade_id}")
                continue

            # حماية إضافية: لو وجدنا صفقة شركة بالخطأ داخل هذه الملفات لا نغلقها
            if j_data.get('is_company', False):
                print(f"⛔ تخطي صفقة شركة موجودة بالخطأ داخل ملفات المؤشرات: {trade_id}")
                continue

            if j_data.get('public_summary_sent', False):
                print(f"ℹ️ تم إرسال ملخص عام سابقًا لهذه الصفقة، تخطي: {trade_id}")
                continue

            # إغلاق الأسبوعي والشهري فقط عند وصول أو تجاوز تاريخ الانتهاء
            if timeframe in ['weekly', 'monthly']:
                expire_date = j_data.get('expire_date')

                if not expire_date:
                    print(f"ℹ️ صفقة {trade_id} لا تحتوي expire_date، تخطي الإغلاق.")
                    continue

                try:
                    expire_dt = pd.to_datetime(expire_date, errors='coerce').date()
                except Exception:
                    print(f"⚠️ تاريخ انتهاء غير مفهوم للصفقة {trade_id}: {expire_date}")
                    continue

                if not expire_dt or expire_dt > today_local:
                    print(f"ℹ️ لم يأتِ تاريخ انتهاء الصفقة {trade_id} بعد. expire_date={expire_date}")
                    continue

            entry_price = safe_float(row.get('Open'))

            group_ids = j_data.get('group_ids', [])

            if not isinstance(group_ids, list):
                group_ids = [group_ids] if group_ids else []

            updates = j_data.get('updates', [])
            peak_notified_price = entry_price
            best_update = None

            if updates:
                try:
                    best_update = max(
                        updates,
                        key=lambda x: safe_float(x.get('notified_price', 0))
                    )

                    peak_notified_price = safe_float(
                        best_update.get('notified_price', entry_price)
                    )

                except Exception as e:
                    print(f"⚠️ خطأ في قراءة تحديثات صفقة المؤشر {trade_id}: {e}")
                    best_update = None
                    peak_notified_price = entry_price

            net_profit_per_contract = (peak_notified_price - entry_price) * 100
            is_profit = net_profit_per_contract >= 50
            realized_price = peak_notified_price

            if is_profit:
                trades_df.loc[idx, 'الربح بالعقد'] = round(net_profit_per_contract, 2)
                j_data['Profit'] = f"{net_profit_per_contract:.2f}"

                if 'Loss' in j_data:
                    j_data.pop('Loss', None)

            else:
                loss_per_contract = entry_price * 100
                trades_df.loc[idx, 'الخسارة بالعقد'] = round(loss_per_contract, 2)
                j_data['Loss'] = f"{loss_per_contract:.2f}"

                if 'Profit' in j_data:
                    j_data.pop('Profit', None)

            trades_df.loc[idx, 'السعر المحقق'] = round(realized_price, 2)
            trades_df.loc[idx, 'High'] = round(realized_price, 2)

            j_data['السعر المحقق'] = f"{realized_price:.2f}"
            j_data['Highest Notified Price'] = f"{realized_price:.2f}"
            j_data['closed_at'] = now.strftime('%Y-%m-%d %H:%M:%S')
            j_data['timeframe'] = j_data.get('timeframe', timeframe)

            closed_contracts_keys.append(trade_id)

            title_name = j_data.get('ticker_name') or ticker_display
            title_prefix = f"عقود {title_name}"

            entry_adj = entry_price * 100
            highest_adj = realized_price * 100

            profit_perc = (
                ((highest_adj - entry_adj) / entry_adj) * 100
                if entry_adj > 0 else 0.0
            )

            if is_profit:
                caption = (
                    f"✨ صفقتنا اليوم ولله الحمد 🤩👏\n"
                    f"{title_prefix} {timeframe_label}\n"
                    f"بسعر {entry_adj:.0f} دولار حققت {highest_adj:.0f} دولار\n"
                    f"بسعر {entry_adj * 3.75:.0f} ريال حققت {highest_adj * 3.75:.0f} ريال\n"
                    f"نسبة الربح %{profit_perc:.1f}\n\n"
                    f"✨ للإنضمام أضغط هنا 👇\n"
                    f"@Spxinfobot"
                )
            else:
                caption = (
                    f"لم يحقق العقد أي ربح، وتم تسجيله كصفقة خاسرة ❌📉\n\n"
                    f"✨ للإنضمام أضغط هنا 👇\n"
                    f"@Spxinfobot"
                )

            entry_data = j_data.get('entry_data', {})

            entry_popup = build_popup(
                header=j_data.get('Header', ''),
                change=j_data.get('Change', ''),
                changePerc=j_data.get('Change Perc', ''),
                closed_time=j_data.get('Closed Time', ''),
                spx_banner=j_data.get('SPX Banner', ''),
                dct=entry_data
            )

            try:
                entry_img_bio = create_image(
                    entry_popup,
                    is_calls=(j_data.get('Type') == 'Calls'),
                    use_right_panel_background=False
                )

                if best_update:
                    high_img_bio = create_image_from_update(
                        update_data=best_update,
                        is_calls=(j_data.get('Type') == 'Calls'),
                        entry_popup=entry_popup,
                        entry_price=entry_price,
                        peak_price=realized_price
                    )
                else:
                    fallback_popup = entry_popup.copy()
                    fallback_popup['price'] = f"{realized_price:.2f}"

                    high_img_bio = create_image(
                        fallback_popup,
                        is_calls=(j_data.get('Type') == 'Calls'),
                        entry_price=entry_price,
                        peak_price=realized_price,
                        use_right_panel_background=False
                    )

            except TypeError:
                try:
                    entry_img_bio = create_image(
                        entry_popup,
                        is_calls=(j_data.get('Type') == 'Calls'),
                        use_right_panel_background=False
                    )

                    if best_update:
                        high_img_bio = create_image_from_update(
                            best_update,
                            (j_data.get('Type') == 'Calls'),
                            entry_popup,
                            entry_price,
                            realized_price
                        )
                    else:
                        fallback_popup = entry_popup.copy()
                        fallback_popup['price'] = f"{realized_price:.2f}"

                        high_img_bio = create_image(
                            fallback_popup,
                            is_calls=(j_data.get('Type') == 'Calls'),
                            entry_price=entry_price,
                            peak_price=realized_price,
                            use_right_panel_background=False
                        )

                except Exception as e:
                    print(f"❌ خطأ إنشاء صور الإغلاق للصفقة {trade_id}: {e}")
                    continue

            except Exception as e:
                print(f"❌ خطأ إنشاء صور الإغلاق للصفقة {trade_id}: {e}")
                continue

            try:
                entry_img_bio.seek(0)
                high_img_bio.seek(0)

                top_img = Image.open(entry_img_bio).convert('RGB')
                bot_img = Image.open(high_img_bio).convert('RGB')

                combined = Image.new(
                    'RGB',
                    (top_img.width, top_img.height + bot_img.height),
                    color=(10, 10, 15)
                )

                combined.paste(top_img, (0, 0))
                combined.paste(bot_img, (0, top_img.height))

                final_bio = io.BytesIO()
                combined.save(final_bio, format='PNG')
                final_image_bytes = final_bio.getvalue()

            except Exception as e:
                print(f"❌ خطأ في دمج الصورتين للصفقة {trade_id}: {e}")
                entry_img_bio.seek(0)
                final_image_bytes = entry_img_bio.getvalue()

            for group_id in group_ids:
                try:
                    bio = io.BytesIO(final_image_bytes)

                    await context.bot.send_photo(
                        chat_id=group_id,
                        photo=InputFile(bio, filename="summary.png"),
                        caption=caption
                    )

                    sent_reports_count += 1
                    print(f"✅ تم إرسال تقرير إغلاق المؤشر إلى {group_id} للصفقة {trade_id}")

                except Exception as e:
                    print(f"❌ فشل الإرسال إلى المجموعة {group_id} للصفقة {trade_id}: {e}")

            is_private_only = bool(group_ids and PUBLIC_GROUP_ID not in group_ids)

            if is_private_only and not j_data.get('public_summary_sent', False):
                public_caption = f"❤️ صفقات القناة الخاصة\n\n{caption}"

                task_data = {
                    'trade_id': trade_id,
                    'json_file': json_file,
                    'image_bytes': final_image_bytes,
                    'public_caption': public_caption,
                    'send_public_at': send_public_at
                }

                async def delayed_send(data=task_data):
                    try:
                        delay = max(
                            0,
                            (data['send_public_at'] - datetime.now(LOCAL_TZ)).total_seconds()
                        )

                        await asyncio.sleep(delay)

                        bio = io.BytesIO(data['image_bytes'])

                        await context.bot.send_photo(
                            chat_id=PUBLIC_GROUP_ID,
                            photo=InputFile(bio, filename="summary.png"),
                            caption=data['public_caption']
                        )

                        curr = []

                        if os.path.exists(data['json_file']):
                            with open(data['json_file'], 'r', encoding='utf-8') as f:
                                curr = json.load(f)

                        for t in curr:
                            if str(t.get('Trade ID')) == str(data['trade_id']):
                                t['public_summary_sent'] = True
                                t['public_summary_sent_at'] = datetime.now(LOCAL_TZ).isoformat()
                                break

                        with open(data['json_file'], 'w', encoding='utf-8') as f:
                            json.dump(curr, f, ensure_ascii=False, indent=2)

                        print(f"✅ تم إرسال الملخص المتأخر للقناة العامة للصفقة {data['trade_id']}")

                    except Exception as e:
                        print(f"❌ فشل الإرسال المتأخر للقناة العامة: {e}")

                asyncio.create_task(delayed_send())

        try:
            final_columns = fieldnames + ['Trade ID']

            for col in final_columns:
                if col not in trades_df.columns:
                    trades_df[col] = ''

            trades_df.to_csv(
                csv_file,
                index=False,
                columns=final_columns,
                encoding='utf-8-sig'
            )

            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(trades_json, f, ensure_ascii=False, indent=2)

            print(f"✅ تم حفظ تعديلات إغلاق المؤشرات في {csv_file} و {json_file}")

        except Exception as e:
            print(f"❌ خطأ في حفظ ملفات المؤشر {csv_file}: {e}")

    tracked_contracts = context.application.bot_data.get('tracked_contracts', {})

    for key in closed_contracts_keys:
        tracked_contracts.pop(key, None)

    print(f"------------ [ انتهاء إغلاق المؤشرات | تم إرسال {sent_reports_count} تقرير فوري ] ------------\n")
def create_image_from_update(update_data: dict, is_calls: bool, entry_popup: dict, entry_price: float, peak_price: float):
    """
    إنشاء صورة من بيانات التحديث مع الحفاظ على header من الدخول
    واستخدام الخلفية مع الجانب الأيمن + عرض نسبة الربح
    """
    popup_data = {
        'header': entry_popup.get('header', 'غير متاح'),
        'price': update_data.get('notified_price', '0.00'),
        'change': update_data.get('change', '+0.00'),
        'changePerc': update_data.get('changePerc', '+0.00%'),
        'spxBanner': entry_popup.get('spxBanner', 'SPX غير متاح'),
        'metrics': {
            'Open': update_data.get('open', '--'),
            'High': update_data.get('high', '--'),
            'Low': update_data.get('low', '--'),
            'Mid': update_data.get('mid', '0.00'),
            'Prev Close': update_data.get('prev close', '0.00'),
            'Break Even': update_data.get('break even', '0.00'),
            'Open Int': update_data.get('open int', update_data.get('Open Int', '--')),
            'Volume': update_data.get('volume', '0')
        }
    }
    # نستخدم الخلفية مع الجانب الأيمن + تمرير الأسعار لحساب نسبة الربح
    return create_image(
        data=popup_data,
        is_calls=is_calls,
        entry_price=entry_price,
        peak_price=peak_price,
        use_right_panel_background=False  # مهم جدًا لإظهار الجانب الأيمن ونسبة الربح
    )
async def setup_page(page):
    print("إعداد الصفحة...")
    await page.goto('https://app.webull.com/stocks')
    await page.wait_for_load_state('networkidle', timeout=60000)
    await page.locator('li[data-ticker-list-key="913354362"]').click(click_count=2)
    print("تم الضغط مرتين على SPX")
    await page.wait_for_timeout(700)
    await page.locator('li.Tabs__TabsTab-sc-14jya01-3 span', has_text='Options').click()
    print("تم الضغط على Options")
    await page.wait_for_timeout(2000)

    await page.wait_for_timeout(2000)
    dd = page.locator('[role="combobox"] span:has-text("10"), [role="combobox"] span:has-text("All")')
    count = await dd.count()
    print(f"تم العثور على {count} قوائم قد تحتوي '10/All'")

    selected_all = False
    for i in range(count):
        item = dd.nth(i)
        try:
            if await item.is_visible(timeout=5000):
                await item.click()
                await page.wait_for_selector('div[role="listbox"]', state='visible', timeout=10000)
                all_option = page.locator('button[role="option"]', has_text='All').first
                if await all_option.count() > 0 and await all_option.is_visible(timeout=5000):
                    await all_option.click()
                    selected_all = True
                    print("تم اختيار 'All'")
                    await page.wait_for_timeout(2000)
                    break
                else:
                    await page.keyboard.press('Escape')
                    await page.wait_for_timeout(300)
        except Exception as e:
            print(f"خطأ أثناء محاولة اختيار All في القائمة رقم {i+1}: {e}")

    if not selected_all:
        print("لم يتم العثور على خيار 'All' (متابعة بقيمتها الحالية).")

    await page.wait_for_timeout(2000)
    print("النقر على قائمة الإجراءات...")
    await page.locator('div.fixedleftCell i.webull-action_menu_').click(timeout=10000)
    await page.wait_for_selector('ol >> span:has-text("Bid")', state='visible', timeout=10000)
    print("تم فتح قائمة الإجراءات")

    menu_ol = page.locator('ol').first

    async def scroll_menu_to(text):
        try:
            await menu_ol.evaluate("el => el.scrollTop = 0")
            await page.wait_for_timeout(120)
            await menu_ol.evaluate("el => el.scrollTop = el.scrollHeight")
            await page.wait_for_timeout(120)
        except:
            pass
        target_span = page.locator(f'//ol//span[normalize-space()="{text}"]').first
        if await target_span.count() > 0:
            try:
                await target_span.scroll_into_view_if_needed()
            except:
                pass
        return page.locator(f'//ol//div[.//span[normalize-space()="{text}"]]').first

    for txt in ['Delta', 'Gamma', 'Vega', 'Theta', 'Break Even', 'Rho']:
        try:
            item_div = await scroll_menu_to(txt)
            if await item_div.count() > 0:
                await item_div.click(timeout=5000)
                print(f"تم النقر على '{txt}'")
                await page.wait_for_timeout(50)
            else:
                print(f"العنصر '{txt}' غير موجود - تخطٍ")
        except Exception as e:
            print(f"فشل النقر على '{txt}': {e} - تخطٍ")

    await page.locator('button:has-text("OK")').first.click(timeout=10000)
    print("تم النقر على OK")
    await page.wait_for_timeout(700)
    print("اكتمل إعداد الصفحة")
async def initialize_browser():
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        p = None
        try:
            print(f"Attempt {attempt}: Initializing browsers...")
            p = await async_playwright().start()
            # Browser for search
            search_browser = await p.chromium.launch(headless=False)
            search_context = await search_browser.new_context()
            cookies_file = 'cookies.json'
            if os.path.exists(cookies_file):
                with open(cookies_file, 'r') as f:
                    cookies = json.load(f)
                await search_context.add_cookies(cookies)
                print("Loaded cookies for search browser")
            search_page = await search_context.new_page()
            await setup_page(search_page)
            print(f"Attempt {attempt}: Search browser initialized successfully")

            # Browser for monitoring
            monitor_browser = await p.chromium.launch(headless=False)
            monitor_context = await monitor_browser.new_context()
            if os.path.exists(cookies_file):
                with open(cookies_file, 'r') as f:
                    cookies = json.load(f)
                await monitor_context.add_cookies(cookies)
                print("Loaded cookies for monitor browser")
            monitor_page = await monitor_context.new_page()
            await setup_page(monitor_page)
            print(f"Attempt {attempt}: Monitor browser initialized successfully")

            return {
                "playwright": p,
                "search_browser": search_browser,
                "search_context": search_context,
                "search_page": search_page,
                "monitor_browser": monitor_browser,
                "monitor_context": monitor_context,
                "monitor_page": monitor_page
            }

        except Exception as e:
            print(f"Error during browser initialization (Attempt {attempt}): {e}")
            try:
                if 'search_page' in locals() and not search_page.is_closed():
                    await search_page.close()
                if 'search_context' in locals():
                    await search_context.close()
                if 'search_browser' in locals():
                    await search_browser.close()
                if 'monitor_page' in locals() and not monitor_page.is_closed():
                    await monitor_page.close()
                if 'monitor_context' in locals():
                    await monitor_context.close()
                if 'monitor_browser' in locals():
                    await monitor_browser.close()
                if p:
                    await p.stop()
            except:
                pass
            if attempt == max_retries:
                raise Exception(f"Failed to initialize browsers after {max_retries} attempts: {e}")
            await asyncio.sleep(5)

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(
        f"[MYID] User ID: {update.effective_user.id} | "
        f"Name: {update.effective_user.full_name} | "
        f"Username: @{update.effective_user.username if update.effective_user.username else 'None'}"
    )
async def cleanup_resources(resources):
    try:
        if 'search_page' in resources and not resources["search_page"].is_closed():
            await resources["search_page"].close()
        if 'search_context' in resources:
            await resources["search_context"].close()
        if 'search_browser' in resources:
            await resources["search_browser"].close()
        if 'monitor_page' in resources and not resources["monitor_page"].is_closed():
            await resources["monitor_page"].close()
        if 'monitor_context' in resources:
            await resources["monitor_context"].close()
        if 'monitor_browser' in resources:
            await resources["monitor_browser"].close()
        if 'playwright' in resources:
            await resources["playwright"].stop()
    except Exception as e:
        print(f"Error during cleanup: {e}")
async def main():
    try:
        print("Starting bot initialization...")

        # إنشاء التطبيق بدون أي موارد Playwright
        app = Application.builder().token(TOKEN).build()

        # تهيئة بيانات البوت
        app.bot_data['contract_queue'] = asyncio.Queue()
        app.bot_data['failed_contracts'] = {}
        app.bot_data['queue_task'] = None
        app.bot_data['tracked_contracts'] = {}
        app.bot_data['current_schedule_time'] = None
        app.bot_data['current_monitor_increase'] = None

        # الهاندلرز كما هي
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(CommandHandler("myid", myid_command))

        # ──────────────────────────────────────────────────────────────
        #     Error Handler لتجاهل أخطاء الشبكة الشائعة بهدوء
        # ──────────────────────────────────────────────────────────────
        async def ignore_common_network_errors(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
            err = context.error

            # تجاهل الأخطاء الشائعة المتعلقة بالشبكة بدون طباعة traceback
            if isinstance(err, telegram.error.NetworkError):
                error_str = str(err).lower()

                if any(phrase in error_str for phrase in [
                    "remoteprotocolerror",
                    "server disconnected",
                    "connection broken",
                    "read timed out",
                    "httpx.remoteprotocolerror",
                ]):
                    return

            # إذا كان الخطأ غير متوقع → اطبعه بشكل طبيعي
            print(f"[Error Handler] {type(err).__name__}: {err}")
            # import traceback; traceback.print_exc()

        # ربط الـ error handler بالتطبيق
        app.add_error_handler(ignore_common_network_errors)
        # ──────────────────────────────────────────────────────────────

        # مهمة مراقبة طابور العقود
        app.bot_data['queue_task'] = asyncio.create_task(monitor_contracts_queue(app))

        print("Starting bot...")
        await app.initialize()

        # =================================================================
        # استرجاع العقود المفتوحة الأسبوعية والشهرية فقط عند إعادة التشغيل
        # =================================================================
        try:
            settings = get_settings()
            monitor_inc = settings.get('monitor_increase', 0.10)

            # ملفات JSON الأسبوعية والشهرية للمؤشرات فقط
            # لا نضيف ملفات الشركات هنا نهائياً
            json_files_to_check = []

            try:
                for f_data in INDICES_FILES.values():
                    base_json = f_data["json"]
                    json_files_to_check.append(f"weekly_{base_json}")
                    json_files_to_check.append(f"monthly_{base_json}")
            except Exception as e:
                print(f"⚠️ تعذر قراءة INDICES_FILES أثناء الاسترجاع: {e}")

            # احتياطي SPX القديم فقط لو لم يكن موجوداً داخل INDICES_FILES
            # هذا ليس شركات، فقط مؤشر SPX
            try:
                json_files_to_check.append(f"weekly_{TRADES_JSON}")
                json_files_to_check.append(f"monthly_{TRADES_JSON}")
            except NameError:
                pass

            # إزالة التكرار
            json_files_to_check = list(set(json_files_to_check))

            restored_count = 0

            for j_file in json_files_to_check:
                if not os.path.exists(j_file):
                    continue

                # تحديد timeframe من اسم الملف نفسه
                if os.path.basename(j_file).startswith("weekly_"):
                    file_timeframe = "weekly"
                elif os.path.basename(j_file).startswith("monthly_"):
                    file_timeframe = "monthly"
                else:
                    # حماية إضافية: لا نسترجع أي ملف يومي
                    continue

                try:
                    with open(j_file, 'r', encoding='utf-8') as f:
                        all_trades = json.load(f)

                except Exception as e:
                    print(f"❌ تعذر قراءة ملف الاسترجاع {j_file}: {e}")
                    continue

                if not isinstance(all_trades, list):
                    print(f"⚠️ الملف {j_file} لا يحتوي قائمة صفقات صحيحة.")
                    continue

                # جلب الصفقات المفتوحة فقط، مع تجاهل اليومي والشركات
                open_trades = []

                for t in all_trades:
                    if not isinstance(t, dict):
                        continue

                    # تجاهل المغلق
                    if t.get('closed_at'):
                        continue

                    # تجاهل الشركات نهائياً
                    if t.get('is_company', False):
                        continue

                    # إذا كانت الصفقة قديمة ولا تحتوي timeframe نستنتجه من اسم الملف
                    trade_timeframe = t.get('timeframe') or file_timeframe

                    # تجاهل اليومي تماماً
                    if trade_timeframe not in ['weekly', 'monthly']:
                        continue

                    open_trades.append((t, trade_timeframe))

                for t, trade_timeframe in open_trades:
                    t_id = str(t.get('Trade ID', '')).strip()

                    if not t_id or t_id.lower() == "nan":
                        continue

                    strike = t.get('Strike') or t.get('SPX Strike')
                    contract_type = t.get('Type')
                    entry_price = safe_float(t.get('Entry Price'))

                    if not strike or not contract_type or entry_price is None:
                        print(f"⚠️ تخطي صفقة ناقصة البيانات في {j_file}: {t_id}")
                        continue

                    last_price = safe_float(
                        t.get('Highest Notified Price', t.get('Entry Price', 0))
                    )

                    if last_price is None:
                        last_price = entry_price

                    group_ids = t.get('group_ids', [])

                    if not isinstance(group_ids, list):
                        group_ids = [group_ids] if group_ids else []

                    ticker_name = t.get('ticker_name', 'SPX')

                    contract_dict = {
                        'trade_id': t_id,
                        'strike': strike,
                        'contract_type': contract_type,
                        'entry_price': entry_price,
                        'last_notified_price': last_price,
                        'monitor_increase': monitor_inc,
                        'stop_loss_price': None,
                        'group_ids': group_ids,
                        'user_id': 0,
                        'retry_count': 0,

                        # بيانات Webull
                        'ticker_id': t.get('ticker_id'),
                        'expire_date': t.get('expire_date'),
                        'direction_api': t.get('direction_api'),

                        # بيانات عامة
                        'created_at': t.get('created_at'),

                        # حماية: مؤشرات فقط
                        'is_company': False,
                        'is_index': True,
                        'ticker_name': ticker_name,
                        'timeframe': trade_timeframe,
                    }

                    app.bot_data['tracked_contracts'][t_id] = contract_dict
                    await app.bot_data['contract_queue'].put(contract_dict)

                    restored_count += 1

            print(
                f"✅ تم استرجاع {restored_count} صفقة أسبوعية/شهرية للمتابعة بنجاح. "
                f"تم تجاهل اليومي والشركات."
            )

        except Exception as e:
            print(f"❌ حدث خطأ أثناء استرجاع الصفقات الأسبوعية/الشهرية المفتوحة: {e}")
            import traceback
            traceback.print_exc()
        # =================================================================

        # جدولة فحص تغييرات الإعدادات: وقت الإغلاق اليومي + نسبة المتابعة
        app.job_queue.run_repeating(
            check_schedule_changes_job,
            interval=10,
            first=0,
            name="schedule_checker"
        )

        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        try:
            while True:
                await asyncio.sleep(3600)

        except asyncio.CancelledError:
            print("Received shutdown signal, stopping bot...")
            raise

    except Exception as e:
        print(f"Error in main: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if 'app' in locals():
            try:
                # إلغاء مهمة الطابور إن كانت موجودة
                if app.bot_data.get('queue_task'):
                    app.bot_data['queue_task'].cancel()

                    try:
                        await app.bot_data['queue_task']

                    except asyncio.CancelledError:
                        print("Queue task cancelled")

                await app.updater.stop()
                await app.stop()
                await app.shutdown()

                print("Bot stopped and shut down")

            except Exception as e:
                print(f"Error during bot shutdown: {e}")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("KeyboardInterrupt received, cancelling tasks...")
        tasks = [task for task in asyncio.all_tasks(loop) if task is not asyncio.current_task(loop)]
        for task in tasks:
            task.cancel()
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(loop.shutdown_default_executor())
    finally:
        loop.close()
        print("Event loop closed")
