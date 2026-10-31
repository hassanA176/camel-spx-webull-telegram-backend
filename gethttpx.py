import asyncio
import json
import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Response

COOKIES_FILE = "cookies.json"
OUTPUT_FILE = "webull_option_network_capture.json"

# الـ endpoints التي تهمّنا
TARGET_ENDPOINTS = [
    "/api/quote/option/strategy/list",
    "/api/quote/option/quotes/queryBatch",
]

# صفحة البداية (يمكنك تغييرها لاحقًا)
START_URL = "https://app.webull.com"


def load_cookies(path: str = COOKIES_FILE):
    """تحميل cookies من الملف كما أرسلته تمامًا (List من العناصر)."""
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text)

    if isinstance(data, list):
        cookies_list = data
    elif isinstance(data, dict) and "cookies" in data and isinstance(data["cookies"], list):
        cookies_list = data["cookies"]
    else:
        raise RuntimeError("صيغة cookies.json غير مدعومة. يجب أن تكون قائمة أو كائن فيه key اسمه 'cookies'.")

    return cookies_list


def is_target_url(url: str) -> bool:
    """هل هذا الـ URL من الـ endpoints التي نريد مراقبتها؟"""
    return any(endpoint in url for endpoint in TARGET_ENDPOINTS)


async def main():
    cookies_list = load_cookies()

    captured = []  # هنا سنحفظ كل طلب/استجابة مهمة

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        await context.add_cookies(cookies_list)
        page = await context.new_page()

        print("فتح المتصفح باستخدام cookies.json ...")
        await page.goto(START_URL, wait_until="load")
        print(f"تم فتح: {START_URL}")

        print("\n[1] انتظر 30 ثانية (تحضير/تحميل أولي قبل البدء في المراقبة)...")
        await page.wait_for_timeout(30_000)

        async def handle_response(resp: Response):
            """كل Response للـ endpoints المستهدفة يتم تخزينها هنا."""
            if not is_target_url(resp.url):
                return

            req = resp.request

            try:
                body_text = await resp.text()
            except Exception:
                body_text = ""

            entry = {
                "ts": datetime.datetime.utcnow().isoformat(),
                "url": resp.url,
                "status": resp.status,
                "method": req.method,
                "request_headers": dict(req.headers),
                "request_post_data": req.post_data,  # لـ POST (مثل strategy/list)
                "response_headers": dict(resp.headers),
                "response_body_text": body_text,
            }
            captured.append(entry)

            print(
                f"[+] Captured {req.method} {resp.url} "
                f"status={resp.status} body_len={len(body_text)}"
            )

        # نبدأ المراقبة الآن فقط (بعد الـ 30 ثانية)
        context.on("response", lambda r: asyncio.create_task(handle_response(r)))

        print(
            "\n[2] الآن افتح يدويًا صفحة الـ options في Webull "
            "واختر SPX وغيّر الاستريك/الـ expiry كما تريد.\n"
            "سيتم التقاط أي طلب لـ option/strategy/list و quotes/queryBatch "
            "لمدة 60 ثانية تقريبًا..."
        )

        # فترة المراقبة (يمكنك تعديلها مثلاً إلى 120 ثانية لو احتجت وقت أطول)
        await page.wait_for_timeout(60_000)

        # حفظ كل ما تم التقاطه
        out_path = Path(OUTPUT_FILE)
        out_path.write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\nتم حفظ {len(captured)} طلب/استجابة في الملف: {out_path.resolve()}")

        # للتسهيل: عرض آخر طلب للـ option/strategy/list فقط كمعاينة سريعة
        strategy_entries = [e for e in captured if "/api/quote/option/strategy/list" in e["url"]]
        if strategy_entries:
            last = strategy_entries[-1]
            print("\nآخر طلب /api/quote/option/strategy/list تم التقاطه:")
            print(json.dumps(last, ensure_ascii=False, indent=2))
        else:
            print("\nلم يتم التقاط أي طلب /api/quote/option/strategy/list خلال فترة المراقبة.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
