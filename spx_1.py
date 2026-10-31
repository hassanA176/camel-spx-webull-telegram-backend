import requests
import time
import hmac
import hashlib
import json

# ==========================================
# 1. إعدادات الاختبار
# ==========================================
# رابط الويب هوك الخاص بك (تأكد أنه يعمل)
WEBHOOK_URL = "https://camelspx.com/webhook"

# الرقم السري الذي وضعناه في app.py
SECRET = os.getenv('WEBHOOK_SECRET', '')

# ==========================================
# 2. البيانات الوهمية (كأنها قادمة من StreamPay)
# ==========================================
payload = {
    "event_type": "PAYMENT_SUCCEEDED",
    "data": {
        "metadata": {
            # 🔴 ضع الآيدي الخاص بك في تليجرام لتصلك رسالة التفعيل
            "chat_id": "1388399007", 
            
            # 🔴 ضع ID أي باقة حقيقية موجودة عندك في الداشبورد
            "package_id": "a2910027-f997-4158-a4d5-e24915a5b790", 
            
            "full_name": "طلال (اختبار)",
            "username": "talal_test",
            "phone_number": "0500000000"
        }
    }
}

# تحويل البيانات لصيغة JSON
raw_body = json.dumps(payload).encode('utf-8')

# ==========================================
# 3. صناعة التشفير (نفس خوارزمية StreamPay بالضبط)
# ==========================================
timestamp = str(int(time.time()))
message = f"{timestamp}.{raw_body.decode('utf-8')}"
signature = hmac.new(SECRET.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
signature_header = f"t={timestamp},v1={signature}"

# إعداد الهيدر (Headers)
headers = {
    "Content-Type": "application/json",
    "X-Webhook-Signature": signature_header
}

# ==========================================
# 4. إرسال الطلب للسيرفر
# ==========================================
print(f"🚀 جاري إرسال الطلب لاختبار الويب هوك: {WEBHOOK_URL} ...\n")

try:
    response = requests.post(WEBHOOK_URL, data=raw_body, headers=headers, timeout=10)
    print("✅ تم الإرسال! الرد من سيرفرك هو:")
    print("رمز الحالة (Status Code):", response.status_code)
    print("النتيجة (Response):", response.text)
except requests.exceptions.ConnectionError:
    print("❌ خطأ: لا يمكن الوصول للسيرفر! (الموقع لا يعمل أو البورت مغلق).")
except Exception as e:
    print("❌ خطأ آخر:", str(e))