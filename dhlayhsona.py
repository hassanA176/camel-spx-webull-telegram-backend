import pandas as pd
from flask import Flask, render_template, request, jsonify
import os, traceback, requests, base64, io, json
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)

# --- إعدادات أساسية ---
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_ID = "1388399007"
DATA_FILE_PATH = os.getenv("TRADES_DATA_PATH", os.path.join(os.path.dirname(__file__), "trades.csv"))
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- إعدادات ---
import json, os
from json import JSONDecodeError

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')
DEFAULT_SETTINGS = {"opacity": 10}

def get_settings():
    # أنشئ الملف إذا لم يوجد
    if not os.path.exists(SETTINGS_FILE):
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS
    # جرّب القراءة، ولو فشلت أعد تهيئة الملف بقيم افتراضية
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # تحقق من النوع والقيم
            if not isinstance(data, dict):
                raise JSONDecodeError("not a dict", "", 0)
            data['opacity'] = int(max(0, min(100, int(data.get('opacity', 10)))))
            return data
    except (JSONDecodeError, ValueError, TypeError):
        # إصلاح تلقائي للملف التالف
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS

def save_settings(settings_data: dict):
    # تأكيد الحدود
    opacity = int(max(0, min(100, int(settings_data.get('opacity', 10)))))
    safe = {"opacity": opacity}
    # كتابة ذرّية بسيطة: اكتب إلى ملف مؤقت ثم استبدل
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(safe, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, SETTINGS_FILE)

# --- تحميل البيانات ---
def load_df(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt"):
        return pd.read_csv(path, encoding="utf-8-sig", sep=None, engine="python")
    elif ext in (".xlsx", ".xls"):
        return pd.read_excel(path, engine="openpyxl")
    else:
        raise ValueError(f"امتداد غير مدعوم: {ext}")

def get_data_from_excel(start_date=None, end_date=None):
    df = load_df(DATA_FILE_PATH)
    df.columns = df.columns.str.strip()

    # number: إذا لم يوجد Number أنشئ تسلسل 1..n
    if 'Number' in df.columns:
        df['number'] = df['Number']
    else:
        df['number'] = pd.RangeIndex(start=1, stop=len(df) + 1)

    # date/time
    date_col = 'Date' if 'Date' in df.columns else ('Time' if 'Time' in df.columns else None)
    df['date_obj'] = pd.to_datetime(df[date_col], errors='coerce') if date_col else pd.NaT
    df['date'] = df['date_obj'].dt.strftime('%Y/%m/%d')

    # type
    if 'Type Contract' in df.columns:
        df['type'] = df['Type Contract'].astype(str).str.upper().str.strip()
    elif 'Type' in df.columns:
        df['type'] = df['Type'].astype(str).str.upper().str.strip()
    else:
        df['type'] = pd.NA

    # strike
    if 'SPX Strike' in df.columns:
        df['strike'] = df['SPX Strike']
    elif 'Strike' in df.columns:
        df['strike'] = df['Strike']
    else:
        df['strike'] = pd.NA

    # open
    if 'Open' in df.columns:
        df['open'] = df['Open']
    elif 'Entry Price' in df.columns:
        df['open'] = df['Entry Price']
    else:
        df['open'] = pd.NA

    # close_price: إن لم يوجد العمود العربي استخدم High
    if 'السعر المحقق' in df.columns:
        df['close_price'] = df['السعر المحقق']
    elif 'High' in df.columns:
        df['close_price'] = df['High']
    else:
        df['close_price'] = pd.NA

    # Profit/Loss
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

    # تنظيف القيم الرقمية
    for col in ['profit', 'loss']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(r'[\$,]', '', regex=True).str.strip(),
                                errors='coerce').fillna(0)

    # تصفية بالتواريخ إن وُجدت
    if start_date: df = df[df['date_obj'] >= pd.to_datetime(start_date)]
    if end_date:   df = df[df['date_obj'] <= pd.to_datetime(end_date)]

    # حساب PnL
    df['pnl'] = df['profit'] - df['loss']

    # أعمدة العرض مع تعبئة المفقود
    display_cols = ['number', 'date', 'type', 'strike', 'open', 'close_price', 'profit', 'loss', 'pnl']
    for c in display_cols:
        if c not in df.columns: df[c] = pd.NA

    return df[display_cols]

def format_currency(value):
    if pd.isna(value) or not isinstance(value, (int, float)): return "$0.00"
    return f"${value:,.2f}"

@app.context_processor
def utility_processor(): return dict(format_currency=format_currency)

# --- Routes ---
@app.route('/')
def dashboard():
    try:
        settings = get_settings()
        logo_url = None

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        df = get_data_from_excel(start_date, end_date)

        if os.listdir(app.config['UPLOAD_FOLDER']):
            filename = os.listdir(app.config['UPLOAD_FOLDER'])[0]
            logo_url = f'/static/uploads/{filename}'

        # كل ما يلي مُحوَّل لأنواع بايثون الأصلية
        total_profit = float(df['profit'].sum())
        total_loss  = float(df['loss'].sum())
        total_pnl   = float(df['pnl'].sum())

        call_trades = int((df['type'] == 'CALL').sum())
        put_trades  = int((df['type'] == 'PUT').sum())

        # سجلات نظيفة (بايثون types) بدل dict مباشر
        import json
        table_data = json.loads(df.to_json(orient='records'))

        overall_stats = {
            'pnl': float(df['pnl'].sum()),
            'number': int(df['number'].count())
        }

        chart_labels    = [f"Trade #{int(n)}" for n in df['number'].tolist()]
        chart_pnl_data  = [float(x) if x == x else 0.0 for x in df['pnl'].tolist()]  # NaN→0
        chart_type_data = [call_trades, put_trades]

        return render_template(
            'index.html',
            table_data=table_data,
            total_profit=total_profit,
            total_loss=total_loss,
            total_pnl=total_pnl,
            overall_stats=overall_stats,
            call_trades=call_trades,
            put_trades=put_trades,
            chart_labels=chart_labels,
            chart_pnl_data=chart_pnl_data,
            chart_type_data=chart_type_data,
            start_date=start_date,
            end_date=end_date,
            logo_url=logo_url,
            saved_opacity=int(settings.get('opacity', 10))
        )
    except Exception as e:
        print(traceback.format_exc())
        return f"<h1>حدث خطأ:</h1><p>{e}</p>", 500


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

@app.route('/save_opacity', methods=['POST'])
def save_opacity():
    data = request.get_json()
    opacity = data.get('opacity')
    if opacity is None:
        return jsonify({'status': 'error', 'message': 'لم يتم توفير قيمة الشفافية'}), 400
    settings = get_settings()
    settings['opacity'] = int(opacity)
    save_settings(settings)
    return jsonify({'status': 'ok', 'message': 'تم حفظ الشفافية'})

@app.route('/process_and_send', methods=['POST'])
def process_and_send():
    if 'image' not in request.files:
        return jsonify({'status': 'error', 'message': 'الرجاء إرسال الصورة تحت مفتاح "image"'}), 400
    if not os.listdir(app.config['UPLOAD_FOLDER']):
        return jsonify({'status': 'error', 'message': 'لا توجد علامة مائية محفوظة. يرجى رفع واحدة أولاً.'}), 400
    base_image_file = request.files['image']
    try:
        settings = get_settings()
        opacity_value = settings.get('opacity', 10) / 100.0
        watermark_filename = os.listdir(app.config['UPLOAD_FOLDER'])[0]
        watermark_path = os.path.join(app.config['UPLOAD_FOLDER'], watermark_filename)

        base_image = Image.open(base_image_file.stream).convert("RGBA")
        watermark = Image.open(watermark_path).convert("RGBA")

        w_ratio = (base_image.width * 0.5) / watermark.width
        new_w, new_h = int(watermark.width * w_ratio), int(watermark.height * w_ratio)
        watermark = watermark.resize((new_w, new_h), Image.Resampling.LANCZOS)

        alpha = watermark.getchannel('A').point(lambda i: int(i * opacity_value))
        watermark.putalpha(alpha)

        paste_x = (base_image.width - new_w) // 2
        paste_y = (base_image.height - new_h) // 2
        base_image.paste(watermark, (paste_x, paste_y), watermark)

        final_image_io = io.BytesIO()
        base_image.save(final_image_io, format='PNG')
        final_image_io.seek(0)

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        files = {'photo': final_image_io}
        payload = {'chat_id': CHAT_ID, 'caption': "تمت معالجة الصورة وإضافة العلامة المائية"}
        response = requests.post(url, files=files, data=payload)
        if response.status_code == 200:
            return jsonify({'status': 'ok', 'message': 'تم معالجة الصورة وإرسالها بنجاح!'})
        return jsonify({'status': 'error', 'message': f'خطأ من تليجرام: {response.text}'}), 500
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': f'حدث خطأ أثناء معالجة الصورة: {str(e)}'}), 500

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

        w_ratio = (base_image.width * 0.5) / watermark.width
        new_w, new_h = int(watermark.width * w_ratio), int(watermark.height * w_ratio)
        watermark = watermark.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        alpha = watermark.getchannel('A')
        alpha = alpha.point(lambda i: int(i * opacity_value))
        watermark.putalpha(alpha)

        paste_x = (base_image.width - new_w) // 2
        paste_y = (base_image.height - new_h) // 2
        base_image.paste(watermark, (paste_x, paste_y), watermark)

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
@app.route('/send_telegram', methods=['POST'])
def send_telegram():
    try:
        data = request.get_json()
        image_b64 = data['image_data']
        caption_text = data['caption']
        header, encoded = image_b64.split(",", 1)
        image_bytes = base64.b64decode(encoded)
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        files = {'photo': io.BytesIO(image_bytes)}
        payload = {'chat_id': CHAT_ID, 'caption': caption_text, 'parse_mode': 'Markdown'}
        response = requests.post(url, files=files, data=payload)
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500
    if response.status_code == 200:
        return jsonify({'status': 'ok', 'message': 'تم الإرسال بنجاح!'})
    return jsonify({'status': 'error', 'message': f'خطأ من تليجرام: {response.text}'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)