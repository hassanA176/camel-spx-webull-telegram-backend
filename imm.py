from PIL import Image, ImageDraw, ImageFont
import io
# import pandas as pd   # إذا كنت تستخدم pd.isna في safe_float

FONT_PATH = r'C:\Windows\Fonts\arialbd.ttf'  # غيّر المسار إذا كان الخط عندك في مكان آخر

def safe_float(value, default=0.00):
    """تحويل آمن للقيم مع التعامل مع '--'"""
    if value in ['--', '', None] or (hasattr(value, 'isna') and value.isna()):
        return default
    try:
        return float(str(value).replace(',', ''))
    except (ValueError, TypeError):
        return default


def create_image(
    data,
    is_calls: bool,
    entry_price: float = 0.0,
    peak_price: float = 0.0,
    use_right_panel_background: bool = False,
    normal_bg_path: str = r'C:\Users\Administrator\Desktop\talal\camel_spx_normal.png',
    right_panel_bg_path: str = r'C:\Users\Administrator\Desktop\talal\camel_spx_with_right.png'
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
        font_header = ImageFont.truetype(FONT_PATH, 36)
        font_values = ImageFont.truetype(FONT_PATH, 38)
        font_profit = ImageFont.truetype(FONT_PATH, 50)
        font_peak = ImageFont.truetype(FONT_PATH, 50)
    except:
        font_price_big = font_header = font_values = font_profit = font_peak = ImageFont.load_default()
    
    # استخراج البيانات
    header_text = data.get('header', 'SPXW $0000 00 XXX 00 (w) Call 100')
    price = data.get('price', '0.00')
    change_perc = data.get('changePerc', '+0.00%')
    metrics = data.get('metrics', {})
    
    # ========================================
    # مواضع منفصلة تمامًا لكل خلفية
    # ========================================
    if use_right_panel_background:
        price_x = 80
        price_y = 150
        header_x = 110
        header_y = 80
        x_value_left = 330
        y_start_left = 345
        spacing_1 = 85
        spacing_2 = 85
        spacing_3 = 85
        x_right = img.width - 270
        y_entry = 410
        y_peak = 720
        y_profit = y_peak + 80

    else:
        price_x = 90
        price_y = 130
        header_x = 110
        header_y = 60
        x_value_left = 440
        y_start_left = 330
        spacing_1 = 110
        spacing_2 = 120
        spacing_3 = 110
    
    # === 1. السعر الكبير ===
    price_color = (12, 175, 130) if change_perc.startswith('+') else (254, 57, 87)
    draw.text((price_x, price_y), price, font=font_price_big, fill=price_color)
    
    # === 2. الـ Header ===
    gray_color = (69, 83, 94)
    green_color = (12, 175, 130)
    red_color = (254, 57, 87)
    if "Call" in header_text:
        parts = header_text.split("Call")
        text_before = parts[0]
        text_call = "Call"
        text_after = parts[1] if len(parts) > 1 else ""
        draw.text((header_x, header_y), text_before, font=font_header, fill=(0, 0, 0))
        w_before = draw.textlength(text_before, font=font_header)
        draw.text((header_x + w_before, header_y), text_call, font=font_header, fill=green_color)
        w_call = draw.textlength(text_call, font=font_header)
        draw.text((header_x + w_before + w_call, header_y), text_after, font=font_header, fill=(0, 0, 0))
    elif "Put" in header_text:
        parts = header_text.split("Put")
        text_before = parts[0]
        text_put = "Put"
        text_after = parts[1] if len(parts) > 1 else ""
        draw.text((header_x, header_y), text_before, font=font_header, fill=(0, 0, 0))
        w_before = draw.textlength(text_before, font=font_header)
        draw.text((header_x + w_before, header_y), text_put, font=font_header, fill=red_color)
        w_put = draw.textlength(text_put, font=font_header)
        draw.text((header_x + w_before + w_put, header_y), text_after, font=font_header, fill=(0, 0, 0))
    else:
        draw.text((header_x, header_y), header_text, font=font_header, fill=(0, 0, 0))
    
    # === 3. القيم اليسارية ===
    open_val = metrics.get('Open', '--')
    mid_val = metrics.get('Mid', '--')
    open_int_val = metrics.get('Open Int', '0')
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
    
    draw.text((x_value_left, y_positions_left[0]), str(open_val), font=font_values, fill=open_color)
    draw.text((x_value_left, y_positions_left[1]), str(mid_val), font=font_values, fill=(87, 93, 108))
    draw.text((x_value_left, y_positions_left[2]), str(open_int_val), font=font_values, fill=(87, 93, 108))
    draw.text((x_value_left, y_positions_left[3]), str(break_even_val), font=font_values, fill=(87, 93, 108))
    
    # === 4. الجانب الأيمن + نسبة الربح + الريال ===
    if use_right_panel_background and entry_price > 0:
        draw.text((x_right, y_entry), f"{entry_price:.2f}", font=font_values, fill=(69, 83, 94))
        
        profit_usd = (peak_price - entry_price) * 100
        peak_text = f"${profit_usd:,.0f}"
        draw.text((x_right, y_peak), peak_text, font=font_peak, fill=(255, 147, 0))
        
        # الريال
        profit_sar = profit_usd * 3.75
        sar_text = f"SAR {profit_sar:,.0f}"
        
        peak_text_bbox = draw.textbbox((0, 0), peak_text, font=font_peak)
        peak_text_width = peak_text_bbox[2] - peak_text_bbox[0]
        
        sar_bbox = draw.textbbox((0, 0), sar_text, font=font_values)
        sar_text_width = sar_bbox[2] - sar_bbox[0]
        
        sar_x = x_right + (peak_text_width - sar_text_width) // 2
        sar_x = max(sar_x, x_right - 50)
        
        draw.text((sar_x-50, y_profit), sar_text, font=font_peak, fill=(255, 147, 0))
        
        # نسبة الربح (كما كانت)
        profit_percentage = ((peak_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
        profit_text = f"{profit_percentage:+.1f}%"
        profit_color = (12, 175, 130) if profit_percentage >= 0 else (254, 57, 87)
        
        text_bbox = draw.textbbox((0, 0), profit_text, font=font_profit)
        text_width = text_bbox[2] - text_bbox[0]
        profit_x = x_right + (peak_text_width - text_width) // 2
        profit_x = max(profit_x, x_right - 50)
        
        draw.text((profit_x, y_profit - 550), profit_text, font=font_profit, fill=profit_color)
    
    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    return bio


# ───────────────────────────────────────────────────────────────
#                 كود اختبار بأرقام وهمية
# ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    fake_data = {
        "header": "SPX  5850  21 MAR 25  (w)  Call",
        "price": "14.65",
        "changePerc": "+92.4%",
        "metrics": {
            "Open": "8.20",
            "Mid": "14.70",
            "Open Int": "3412",
            "Break Even": "5864.65",
            "Prev Close": "7.62"
        }
    }

    # أرقام وهمية للتجربة
    result_image = create_image(
        data=fake_data,
        is_calls=True,
        entry_price=3.85,
        peak_price=11.20,
        use_right_panel_background=True,
        # غيّر المسارات إذا لزم الأمر
    )

    # حفظ الصورة لتراها فوراً
    with open("test_profit_sar.png", "wb") as f:
        f.write(result_image.getvalue())

    print("تم حفظ الصورة باسم:  test_profit_sar.png")
    print("القيم المستخدمة في التجربة:")
    print(f"  Entry price     :  3.85")
    print(f"  Peak price      : 11.20")
    print(f"  Profit USD      : ${(11.20 - 3.85) * 100:,.0f}")
    print(f"  Profit SAR      : {((11.20 - 3.85) * 100 * 3.75):,.0f} ريال")
    print(f"  Profit percent  : {((11.20 - 3.85) / 3.85 * 100):+.1f}%")