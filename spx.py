# manual_spx_summary_sender.py
# سكريبت مستقل يُنشئ صورة مدمجة (دخول + قمة) ويرسلها إلى تيليجرام

import asyncio
import io
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot, InputFile
import pandas as pd

# ────────────────────────────────────────────────
#  ثوابت - غيّرها حسب بيئتك
# ────────────────────────────────────────────────

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

PUBLIC_GROUP_ID = os.getenv('TELEGRAM_PUBLIC_GROUP_ID', '')
PRIVATE_GROUP_ID = os.getenv('TELEGRAM_PRIVATE_GROUP_ID', '')

NORMAL_BG    = r"C:\Users\Administrator\Desktop\talal\camel_spx_normal.png"
RIGHT_BG     = r"C:\Users\Administrator\Desktop\talal\camel_spx_with_right.png"
FONT_PATH    = r"C:\Windows\Fonts\arialbd.ttf"

# ────────────────────────────────────────────────
# دالة safe_float (موجودة عندك)
# ────────────────────────────────────────────────

def safe_float(value, default=0.00):
    """تحويل آمن للقيم مع التعامل مع '--'"""
    if value == '--' or pd.isna(value) or value == '' or value is None:
        return default
    try:
        return float(str(value).replace(',', ''))
    except (ValueError, TypeError):
        return default

# ────────────────────────────────────────────────
# دالة create_image (كما أعطيتني إياها مع تعديل طفيف للتوافق)
# ────────────────────────────────────────────────

def create_image(
    data,
    is_calls: bool,
    entry_price: float = 0.0,
    peak_price: float = 0.0,
    use_right_panel_background: bool = False,
    normal_bg_path: str = NORMAL_BG,
    right_panel_bg_path: str = RIGHT_BG
) -> io.BytesIO:
    # اختيار الخلفية
    bg_path = right_panel_bg_path if use_right_panel_background else normal_bg_path
    try:
        img = Image.open(bg_path).convert("RGBA")
        print(f"تم تحميل الخلفية: {bg_path} | الحجم: {img.size}")
    except Exception as e:
        print(f"فشل تحميل {bg_path}: {e}")
        img = Image.new('RGBA', (800, 600), (0, 0, 0, 255))

    draw = ImageDraw.Draw(img)

    # الخطوط
    try:
        font_price_big = ImageFont.truetype(FONT_PATH, 150)
        font_header    = ImageFont.truetype(FONT_PATH, 36)
        font_values    = ImageFont.truetype(FONT_PATH, 38)
        font_profit    = ImageFont.truetype(FONT_PATH, 45)
        font_peak      = ImageFont.truetype(FONT_PATH, 50)
    except:
        font_price_big = font_header = font_values = font_profit = font_peak = ImageFont.load_default()

    # استخراج البيانات
    header_text = data.get('header', 'SPXW $0000 00 XXX 00 (w) Call 100')
    price       = data.get('price', '0.00')
    change_perc = data.get('changePerc', '+0.00%')
    metrics     = data.get('metrics', {})

    # تحديد المواضع حسب نوع الخلفية
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
        y_entry       = 450
        y_peak        = 750
        y_profit      = y_peak - 470
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

    # السعر الكبير (لون أخضر/أحمر بناءً على changePerc)
    price_color = (12, 175, 130) if change_perc.startswith('+') else (254, 57, 87)
    draw.text((price_x, price_y), price, font=font_price_big, fill=price_color)

    # الـ Header (Call بالأخضر، Put بالأحمر)
    gray_color   = (69, 83, 94)
    green_color  = (12, 175, 130)
    red_color    = (254, 57, 87)

    if "Call" in header_text:
        parts = header_text.split("Call")
        text_before = parts[0]
        text_call   = "Call"
        text_after  = parts[1] if len(parts) > 1 else ""
        draw.text((header_x, header_y), text_before, font=font_header, fill=(0,0,0))
        w_before = draw.textlength(text_before, font=font_header)
        draw.text((header_x + w_before, header_y), text_call, font=font_header, fill=green_color)
        w_call = draw.textlength(text_call, font=font_header)
        draw.text((header_x + w_before + w_call, header_y), text_after, font=font_header, fill=(0,0,0))
    elif "Put" in header_text:
        parts = header_text.split("Put")
        text_before = parts[0]
        text_put    = "Put"
        text_after  = parts[1] if len(parts) > 1 else ""
        draw.text((header_x, header_y), text_before, font=font_header, fill=(0,0,0))
        w_before = draw.textlength(text_before, font=font_header)
        draw.text((header_x + w_before, header_y), text_put, font=font_header, fill=red_color)
        w_put = draw.textlength(text_put, font=font_header)
        draw.text((header_x + w_before + w_put, header_y), text_after, font=font_header, fill=(0,0,0))
    else:
        draw.text((header_x, header_y), header_text, font=font_header, fill=(0,0,0))

    # القيم اليسارية
    open_val       = metrics.get('Open', '--')
    mid_val        = metrics.get('Mid', '--')
    open_int_val   = metrics.get('Open Int', '0')
    break_even_val = metrics.get('Break Even', '--')

    try:
        open_float = safe_float(open_val)
        prev_close = safe_float(metrics.get('Prev Close', '0.00'))
        open_color = (12, 175, 130) if open_float > prev_close else (254, 57, 87) if open_float < prev_close else (0, 0, 0)
    except:
        open_color = (0, 0, 0)

    y_positions_left = [
        y_start_left,
        y_start_left + spacing_1,
        y_start_left + spacing_1 + spacing_2,
        y_start_left + spacing_1 + spacing_2 + spacing_3
    ]

    draw.text((x_value_left, y_positions_left[0]), str(open_val),       font=font_values, fill=open_color)
    draw.text((x_value_left, y_positions_left[1]), str(mid_val),        font=font_values, fill=(87, 93, 108))
    draw.text((x_value_left, y_positions_left[2]), str(open_int_val),   font=font_values, fill=(87, 93, 108))
    draw.text((x_value_left, y_positions_left[3]), str(break_even_val), font=font_values, fill=(87, 93, 108))

    # الجانب الأيمن (يظهر فقط إذا use_right_panel_background=True)
    if use_right_panel_background and entry_price > 0:
        # Entry Price
        draw.text((x_right, y_entry), f"{entry_price:.2f}", font=font_values, fill=(69, 83, 94))
        
        # Peak Price المعدّل (*100)
        peak_display = (peak_price - entry_price) * 100
        peak_text = f"${peak_display:.0f}"
        draw.text((x_right, y_peak), peak_text, font=font_peak, fill=(255, 147, 0))
        
        # نسبة الربح
        profit_percentage = ((peak_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
        profit_text = f"{profit_percentage:+.1f}%"
        profit_color = (12, 175, 130) if profit_percentage >= 0 else (254, 57, 87)

        text_bbox = draw.textbbox((0, 0), profit_text, font=font_profit)
        text_width = text_bbox[2] - text_bbox[0]
        peak_text_bbox = draw.textbbox((0, 0), peak_text, font=font_peak)
        peak_text_width = peak_text_bbox[2] - peak_text_bbox[0]
        profit_x = x_right + (peak_text_width - text_width) // 2
        profit_x = max(profit_x, x_right - 50)

        draw.text((profit_x, y_profit), profit_text, font=font_profit, fill=profit_color)

    # حفظ الصورة
    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    return bio


# ────────────────────────────────────────────────
# دالة إنشاء الكابشن
# ────────────────────────────────────────────────

def make_summary_caption(entry_price: float, peak_price: float) -> str:
    entry_adj   = entry_price * 100
    peak_adj    = peak_price  * 100
    profit_perc = ((peak_adj - entry_adj) / entry_adj * 100) if entry_adj > 0 else 0.0
    riyal_rate  = 3.75

    return (
        f"صفقتنا اليوم ولله الحمد 🤩👏\n"
        f"عقود SPX اليومية\n"
        f"بسعر {entry_adj:.0f} دولار حققت {peak_adj:.0f} دولار\n"
        f"بسعر {entry_adj * riyal_rate:.0f} ريال حققت {peak_adj * riyal_rate:.0f} ريال\n"
        f"نسبة الربح %{profit_perc:.1f}\n\n"
        f"✨ للإنضمام أضغط هنا 👇\n"
        f"@Spxinfobot"
    )


# ────────────────────────────────────────────────
# الدالة الرئيسية المستقلة
# ────────────────────────────────────────────────

async def send_manual_combined_summary(
    entry_price: float,
    peak_price: float,
    entry_metrics: dict,               # بيانات الصورة الأولى (Open, Mid, ...)
    peak_metrics: dict,                # بيانات الصورة الثانية (Open, Mid, ...)
    is_call: bool = True,
    strike: str = "6500",
    expiry: str = "14 Nov 25",
    target: str = "AB",
):
    direction = "Call" if is_call else "Put"
    header = f"SPXW ${strike} {expiry}   (w) {direction}  100"

    # بيانات أساسية مشتركة (change / changePerc يمكن أن تختلف لاحقاً)
    base_popup = {
        "header": header,
        "change": "+0.00",          # يمكن تمرير قيم حقيقية لاحقاً
        "changePerc": "+0.00%",
        "closedTime": f"Open {datetime.now().strftime('%m/%d %H:%M')} EST",
        "spxBanner": "SPXW",
    }

    # 1. صورة الدخول (بدون الجانب الأيمن)
    entry_popup = base_popup.copy()
    entry_popup["price"] = f"{entry_price:.2f}"
    entry_popup["metrics"] = entry_metrics
    entry_bio = create_image(
        data=entry_popup,
        is_calls=is_call,
        use_right_panel_background=False
    )

    # 2. صورة القمة (مع الجانب الأيمن + حساب الربح + ألوان التغيير)
    peak_popup = base_popup.copy()
    peak_popup["price"] = f"{peak_price:.2f}"
    # هنا نضع changePerc حقيقي لتحديد لون السعر الكبير
    change_value = peak_price - entry_price
    change_perc_str = f"{change_value:+.2f}"
    peak_popup["changePerc"] = f"{change_value:+.4f}%"   # لتحديد اللون الأخضر/أحمر
    peak_popup["metrics"] = peak_metrics

    peak_bio = create_image(
        data=peak_popup,
        is_calls=is_call,
        entry_price=entry_price,
        peak_price=peak_price,
        use_right_panel_background = False
    )

    # 3. دمج الصورتين رأسياً
    try:
        top_img = Image.open(entry_bio).convert("RGB")
        bot_img = Image.open(peak_bio).convert("RGB")

        combined_height = top_img.height + bot_img.height
        combined = Image.new("RGB", (top_img.width, combined_height), color=(10, 10, 15))
        combined.paste(top_img, (0, 0))
        combined.paste(bot_img, (0, top_img.height))

        final_bio = io.BytesIO()
        combined.save(final_bio, format="PNG")
        final_bio.seek(0)
    except Exception as e:
        print(f"خطأ أثناء دمج الصورتين: {e}")
        final_bio = entry_bio   # fallback

    # 4. الكابشن
    caption = make_summary_caption(entry_price, peak_price)

    # 5. تحديد المجموعات
    groups = []
    t = target.upper()
    if "A" in t: groups.append(PRIVATE_GROUP_ID)
    if "B" in t: groups.append(PUBLIC_GROUP_ID)

    if not groups:
        print("لم يتم تحديد أي مجموعة صالحة")
        return

    # 6. الإرسال
    bot = Bot(token=TELEGRAM_TOKEN)

    for gid in groups:
        try:
            await bot.send_photo(
                chat_id=gid,
                photo=InputFile(final_bio, filename="spx_summary.png"),
                caption=caption,
                parse_mode=None
            )
            print(f"تم الإرسال إلى {gid}")
            final_bio.seek(0)
        except Exception as e:
            print(f"فشل الإرسال إلى {gid} → {e}")


# ────────────────────────────────────────────────
# مثال استخدام
# ────────────────────────────────────────────────

async def run_example():
    # بيانات الصورة الأولى (الدخول)
    entry_metrics = {
        "Open": "25.90",           # قد يكون مختلفاً أو نفس القيمة
        "Mid": "1.08",
        "Prev Close": "4.30",
        "High": "41.50",
        "Low": "0.90",
        "Break Even": "6960.05",
        "Open Int": "1890",
        "Volume": "24500"
    }

    # بيانات الصورة الثانية (القمة / الخروج)
    peak_metrics = {
        "Open": "25.90",           # قد يكون مختلفاً أو نفس القيمة
        "Mid": "5.70",
        "Prev Close": "4.30",
        "High": "57.96",
        "Low": "1.80",
        "Break Even": "6965.10",
        "Open Int": "--",
        "Volume": "24500"
    }

    await send_manual_combined_summary(
        entry_price = 1.1,
        peak_price  = 12.0,
        entry_metrics = entry_metrics,
        peak_metrics  = peak_metrics,
        is_call     = True,
        strike      = "6920",
        expiry      = "06 Feb 26",
        target      = "AB"          # أو "A" أو "AB"
    )


if __name__ == "__main__":
    asyncio.run(run_example())