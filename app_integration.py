# ╔══════════════════════════════════════════════════════════════╗
# ║  CAMEL SPX - Backend Integration Module                       ║
# ║  ----------------------------------------                     ║
# ║  هذا الملف يحتوي على كل الـ endpoints الجديدة التي تحتاجها     ║
# ║  الواجهة الجديدة (CAMEL SPX Platform 2026)                    ║
# ║                                                               ║
# ║  طريقة الاستخدام:                                              ║
# ║     في app.py الحالي أضف هذا السطر في نهاية الملف              ║
# ║     قبل if __name__ == '__main__':                            ║
# ║                                                               ║
# ║       from app_integration import register_integration        ║
# ║       register_integration(app, DATABASE_PATH, BASE_DIR)      ║
# ╚══════════════════════════════════════════════════════════════╝

import os
import io
import csv
import json
import time
import uuid
import sqlite3
import traceback
import requests
import pandas as pd
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    request, jsonify, session, redirect, url_for,
    render_template, send_file, abort
)


# ════════════════════════════════════════════════════════════════
#  المتغيرات العامة (سيتم تعبئتها من register_integration)
# ════════════════════════════════════════════════════════════════
_APP = None
_DB_PATH = None
_BASE_DIR = None
_BOT_TOKEN = None
_PUBLIC_GROUP_ID = None
_PRIVATE_GROUP_ID = None
_BOT_API_KEY = None


# ════════════════════════════════════════════════════════════════
#  أدوات مساعدة
# ════════════════════════════════════════════════════════════════
def _conn():
    """فتح اتصال بقاعدة البيانات مع row_factory للسهولة."""
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _login_required(fn):
    """ديكوريتور للتأكد من تسجيل الدخول."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        return fn(*args, **kwargs)
    return wrapper


def _bot_key_required(fn):
    """ديكوريتور للتحقق من API Key (للطلبات القادمة من البوت)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.headers.get('X-Bot-API-Key') != _BOT_API_KEY:
            return jsonify({'error': 'Unauthorized'}), 401
        return fn(*args, **kwargs)
    return wrapper


def log_audit(user, action, target='', details='', ip=None):
    """تسجيل حدث في سجل الأدمن. يُستدعى من أي مكان."""
    try:
        with _conn() as c:
            c.execute(
                """INSERT INTO audit_log (user, action, target, ip, ts, details)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user, action, target,
                 ip or (request.remote_addr if request else None),
                 datetime.now().isoformat(),
                 details if isinstance(details, str) else json.dumps(details, ensure_ascii=False))
            )
    except Exception as e:
        print(f"[audit_log] error: {e}")


# ════════════════════════════════════════════════════════════════
#  إنشاء الجداول الجديدة
# ════════════════════════════════════════════════════════════════
def init_new_tables():
    """ينشئ الجداول الجديدة عند الإقلاع. آمن للتشغيل المتكرر."""
    with _conn() as c:
        # طلبات السحب
        c.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                beneficiary_name TEXT,
                iban TEXT,
                bank_name TEXT,
                status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
                note TEXT,
                requested_at TEXT NOT NULL,
                processed_at TEXT,
                processed_by TEXT,
                receipt_path TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_w_status ON withdrawals(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_w_chat ON withdrawals(chat_id)")

        # سجل الأدمن
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                action TEXT NOT NULL,        -- create | edit | delete | payment | login | warning
                target TEXT,                  -- اسم الكائن المتأثر
                ip TEXT,
                ts TEXT NOT NULL,
                details TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_a_action ON audit_log(action)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_a_ts ON audit_log(ts)")

        # رصيد المحفظة (للعملاء)
        c.execute("""
            CREATE TABLE IF NOT EXISTS wallet_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                amount REAL NOT NULL,         -- موجب = إضافة، سالب = خصم
                source TEXT NOT NULL,         -- referral_bonus | withdrawal | manual | refund
                description TEXT,
                created_at TEXT NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_wl_chat ON wallet_ledger(chat_id)")

        # طلبات التفعيل اليدوي (للأدمن - يفعّل بدون دفع إلكتروني)
        c.execute("""
            CREATE TABLE IF NOT EXISTS manual_activations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                package_id TEXT NOT NULL,
                amount REAL,
                payment_method TEXT,
                activated_by TEXT,
                activated_at TEXT NOT NULL,
                note TEXT
            )
        """)

        c.commit()
    print("✅ تم إنشاء/تحديث جداول: withdrawals, audit_log, wallet_ledger, manual_activations")


# ════════════════════════════════════════════════════════════════
#  تجهيز بيانات الصفقات للـ Dashboard JS (نفس schema الواجهة)
# ════════════════════════════════════════════════════════════════
def _trades_to_json_for_dashboard(df):
    """
    يحوّل DataFrame الصفقات إلى الـ schema التي تتوقعها dashboard.html:
       {date, dayOfWeek, hour, minute, duration, side, strike, entry, peak, pnl}
    """
    if df is None or df.empty:
        return []

    out = []
    for _, row in df.iterrows():
        # تاريخ الصفقة (yyyy-mm-dd)
        dt = row.get('date_obj')
        try:
            dt = pd.to_datetime(dt) if not pd.isna(dt) else None
        except Exception:
            dt = None

        if dt is None:
            # fallback: استخدم row['date']
            try:
                dt = pd.to_datetime(row.get('date'))
            except Exception:
                continue

        # المدة بالدقائق (من entry_time → close_time إن وُجدا)
        duration_min = 0
        dur = row.get('duration')
        if isinstance(dur, str) and ':' in dur:
            try:
                h, m = dur.split(':')[:2]
                duration_min = int(h) * 60 + int(m)
            except Exception:
                duration_min = 0

        # PnL — يستخدم profit بدلاً من loss إذا كانت رابحة
        try:
            pnl_val = float(row.get('pnl', 0) or 0)
        except (ValueError, TypeError):
            pnl_val = 0.0

        try:
            strike_val = int(float(row.get('strike', 0) or 0))
        except (ValueError, TypeError):
            strike_val = 0

        try:
            entry_val = float(row.get('open', 0) or 0)
        except (ValueError, TypeError):
            entry_val = 0.0

        try:
            peak_val = float(row.get('close_price', 0) or 0)
        except (ValueError, TypeError):
            peak_val = entry_val

        side_raw = str(row.get('type', '')).upper().strip()
        side = 'CALL' if 'CALL' in side_raw else ('PUT' if 'PUT' in side_raw else 'CALL')

        out.append({
            'date': dt.strftime('%Y-%m-%d'),
            'dayOfWeek': int(dt.weekday()),  # 0=Mon ... 6=Sun (مثل dashboard.html تماماً)
            'hour': int(dt.hour),
            'minute': int(dt.minute),
            'duration': duration_min,
            'side': side,
            'strike': strike_val,
            'entry': round(entry_val, 2),
            'peak': round(peak_val, 2),
            'pnl': round(pnl_val, 2),
        })

    return out


def _clients_to_json_for_ui():
    """
    يجلب العملاء من users.db ويحولهم لـ schema clients.html:
       {id, name, phone, code, referrer, refs, paid, pkg, pkgLabel, end, status, avatarColor}
    """
    with _conn() as c:
        rows = c.execute("""
            SELECT chat_id, name, username, phone_number, paid,
                   subscription_package, subscription_end, total_paid_amount,
                   is_frozen, frozen_days_remaining,
                   referral_code, referred_by_code, referral_count, first_seen
            FROM users ORDER BY first_seen DESC
        """).fetchall()

    out = []
    now = datetime.now()
    avatar_palette = ['cy', 'go', 'gr', 'pu']  # cyan/gold/green/purple
    for i, r in enumerate(rows):
        d = dict(r)
        sub_end_str = d.get('subscription_end')
        status = 'inactive'
        end_iso = ''
        if sub_end_str:
            try:
                sub_end_dt = datetime.fromisoformat(sub_end_str)
                end_iso = sub_end_dt.strftime('%Y-%m-%d')
                if d.get('is_frozen'):
                    status = 'frozen'
                elif sub_end_dt > now:
                    status = 'active'
                else:
                    status = 'expired'
            except (ValueError, TypeError):
                pass

        # تخمين ذكي للـ pkg (low-tier / premium / vip) من اسم الباقة
        pkg_label = d.get('subscription_package') or 'لا يوجد'
        pkg_lower = pkg_label.lower()
        if 'vip' in pkg_lower or 'بلاتيني' in pkg_label or 'بلاتين' in pkg_label:
            pkg = 'vip'
        elif 'ذهب' in pkg_label or 'gold' in pkg_lower or 'premium' in pkg_lower:
            pkg = 'premium'
        else:
            pkg = 'standard'

        out.append({
            'id': f"C{d['chat_id']}",
            'chat_id': d['chat_id'],
            'name': d.get('name') or d.get('username') or f"عميل {d['chat_id']}",
            'phone': d.get('phone_number') or '',
            'code': d.get('referral_code') or '',
            'referrer': d.get('referred_by_code'),
            'refs': int(d.get('referral_count') or 0),
            'paid': float(d.get('total_paid_amount') or 0),
            'pkg': pkg,
            'pkgLabel': pkg_label,
            'end': end_iso,
            'status': status,
            'isFrozen': bool(d.get('is_frozen')),
            'frozenDaysRemaining': d.get('frozen_days_remaining'),
            'avatarColor': avatar_palette[i % len(avatar_palette)],
        })

    return out


# ════════════════════════════════════════════════════════════════
#  Telegram helpers
# ════════════════════════════════════════════════════════════════
def _send_telegram_message(chat_id, text, parse_mode='HTML'):
    """إرسال رسالة لشخص أو مجموعة على تيليجرام."""
    try:
        url = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
        payload = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode,
                   'disable_web_page_preview': True}
        r = requests.post(url, json=payload, timeout=15)
        return r.ok
    except Exception as e:
        print(f"[telegram] failed: {e}")
        return False


# ════════════════════════════════════════════════════════════════
#  التسجيل في تطبيق Flask
# ════════════════════════════════════════════════════════════════
def register_integration(app, database_path, base_dir,
                         bot_token=None, public_group=None,
                         private_group=None, bot_api_key='1234',
                         get_data_fn=None, get_settings_fn=None, save_settings_fn=None):
    """
    يربط كل الـ endpoints الجديدة بتطبيق Flask القائم.

    Parameters
    ----------
    app : Flask
    database_path : str  مسار users.db
    base_dir : str       المجلد الجذري للمشروع
    bot_token, public_group, private_group : str  بيانات تيليجرام
    bot_api_key : str    مفتاح الـ API للبوت
    get_data_fn : callable  دالة قراءة الصفقات (get_data_from_excel من app.py)
    get_settings_fn / save_settings_fn : callables  دوال الإعدادات
    """
    global _APP, _DB_PATH, _BASE_DIR, _BOT_TOKEN
    global _PUBLIC_GROUP_ID, _PRIVATE_GROUP_ID, _BOT_API_KEY
    _APP = app
    _DB_PATH = database_path
    _BASE_DIR = base_dir
    _BOT_TOKEN = bot_token
    _PUBLIC_GROUP_ID = public_group
    _PRIVATE_GROUP_ID = private_group
    _BOT_API_KEY = bot_api_key

    # حقن دوال app.py الموجودة (نستخدمها بدون تكرارها)
    if get_data_fn is None or get_settings_fn is None or save_settings_fn is None:
        raise ValueError("يجب تمرير get_data_fn و get_settings_fn و save_settings_fn")

    # تهيئة الجداول
    init_new_tables()

    # ════════════════════════════════════════════════════
    #  1) الصفحة الرئيسية للوحة الإدارة (الـ SPA shell)
    # ════════════════════════════════════════════════════
    @app.route('/admin')
    def admin_shell():
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        # نعرض index.html (الـ shell الذي يحتوي على الـ iframe والـ sidebar)
        return render_template('index.html')

    # خدمة الصفحات الفرعية (تُحمَّل داخل الـ iframe)
    @app.route('/admin/<page>.html')
    def admin_page(page):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        allowed_pages = {
            'dashboard', 'clients', 'subscriptions', 'withdrawals',
            'referrals', 'notifications', 'imagegen', 'botpreview',
            'auditlog', 'settings'
        }
        if page not in allowed_pages:
            abort(404)
        return render_template(f'{page}.html')

    @app.route('/client-area')
    def client_shell():
        # لوحة العميل (Telegram WebApp). تحقق المصادقة في endpoints منفصلة
        return render_template('index.html', client_mode=True)

    @app.route('/client-area/<page>.html')
    def client_page(page):
        allowed = {'client-dashboard', 'client-trades', 'client-subscription',
                   'client-wallet', 'client-referral', 'client-themes'}
        if page not in allowed:
            abort(404)
        return render_template(f'{page}.html')

    # ════════════════════════════════════════════════════
    #  2) API: الصفقات (Dashboard)
    # ════════════════════════════════════════════════════
    @app.route('/api/trades')
    @_login_required
    def api_trades():
        try:
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            limit = request.args.get('limit', type=int)

            df = get_data_fn(start_date, end_date)
            data = _trades_to_json_for_dashboard(df)
            if limit:
                data = data[-limit:]

            return jsonify({
                'status': 'ok',
                'count': len(data),
                'trades': data
            })
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/trades/recent')
    @_login_required
    def api_trades_recent():
        """آخر N صفقات (للاستخدام في imagegen.html)."""
        try:
            n = request.args.get('n', 12, type=int)
            df = get_data_fn(None, None)
            data = _trades_to_json_for_dashboard(df)
            recent = data[-n:][::-1]  # أحدث أولاً
            return jsonify({'status': 'ok', 'trades': recent})
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/dashboard/stats')
    @_login_required
    def api_dashboard_stats():
        """ملخص KPIs لتعبئة بطاقات Dashboard بسرعة بدون تحميل كل الصفقات."""
        try:
            df = get_data_fn(
                request.args.get('start_date'),
                request.args.get('end_date')
            )
            if df is None or df.empty:
                return jsonify({'status': 'ok', 'empty': True})

            total_profit = float(df['profit'].sum())
            total_loss = float(df['loss'].sum())
            total_pnl = float(df['pnl'].sum())
            n = len(df)
            wins = int((df['pnl'] >= 50).sum())
            losses = n - wins
            win_rate = round((wins / n * 100), 2) if n > 0 else 0
            profit_factor = round(total_profit / total_loss, 2) if total_loss > 0 else 0

            return jsonify({
                'status': 'ok',
                'totalTrades': n,
                'wins': wins,
                'losses': losses,
                'winRate': win_rate,
                'totalProfit': total_profit,
                'totalLoss': total_loss,
                'netPnl': total_pnl,
                'profitFactor': profit_factor,
                'callTrades': int((df['type'] == 'CALL').sum()),
                'putTrades': int((df['type'] == 'PUT').sum()),
            })
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # ════════════════════════════════════════════════════
    #  3) API: العملاء
    # ════════════════════════════════════════════════════
    @app.route('/api/clients')
    @_login_required
    def api_clients():
        try:
            clients = _clients_to_json_for_ui()
            # إحصاءات
            now = datetime.now()
            active = sum(1 for c in clients if c['status'] == 'active')
            frozen = sum(1 for c in clients if c['status'] == 'frozen')
            expired = sum(1 for c in clients if c['status'] == 'expired')
            revenue = sum(c['paid'] for c in clients)

            return jsonify({
                'status': 'ok',
                'clients': clients,
                'stats': {
                    'total': len(clients),
                    'active': active,
                    'frozen': frozen,
                    'expired': expired,
                    'revenue': revenue,
                }
            })
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/clients/<int:chat_id>')
    @_login_required
    def api_client_detail(chat_id):
        try:
            with _conn() as c:
                row = c.execute(
                    "SELECT * FROM users WHERE chat_id = ?", (chat_id,)
                ).fetchone()
                if not row:
                    return jsonify({'status': 'error', 'message': 'Client not found'}), 404

                # سجل المحفظة
                ledger = c.execute("""
                    SELECT * FROM wallet_ledger
                    WHERE chat_id = ? ORDER BY created_at DESC LIMIT 50
                """, (chat_id,)).fetchall()

                # طلبات السحب
                withdrawals = c.execute("""
                    SELECT * FROM withdrawals
                    WHERE chat_id = ? ORDER BY requested_at DESC LIMIT 20
                """, (chat_id,)).fetchall()

            return jsonify({
                'status': 'ok',
                'client': dict(row),
                'ledger': [dict(x) for x in ledger],
                'withdrawals': [dict(x) for x in withdrawals],
            })
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # ════════════════════════════════════════════════════
    #  4) API: الاشتراكات
    # ════════════════════════════════════════════════════
    @app.route('/api/subscriptions')
    @_login_required
    def api_subscriptions():
        """قائمة الاشتراكات + إحصاءات."""
        try:
            with _conn() as c:
                rows = c.execute("""
                    SELECT chat_id, name, username, subscription_package,
                           subscription_end, total_paid_amount, is_frozen,
                           paid, first_seen
                    FROM users
                    WHERE subscription_package IS NOT NULL AND paid = 1
                    ORDER BY subscription_end DESC
                """).fetchall()

            now = datetime.now()
            subs = []
            kpis = {'active': 0, 'expired': 0, 'frozen': 0,
                    'revenue': 0.0, 'thisMonth': 0}

            for r in rows:
                d = dict(r)
                end_str = d.get('subscription_end')
                status = 'unknown'
                end_iso = ''
                if end_str:
                    try:
                        end_dt = datetime.fromisoformat(end_str)
                        end_iso = end_dt.strftime('%Y-%m-%d')
                        if d.get('is_frozen'):
                            status = 'frozen'
                            kpis['frozen'] += 1
                        elif end_dt > now:
                            status = 'active'
                            kpis['active'] += 1
                        else:
                            status = 'expired'
                            kpis['expired'] += 1
                    except (ValueError, TypeError):
                        pass
                subs.append({
                    'chatId': d['chat_id'],
                    'name': d.get('name') or d.get('username') or f"عميل {d['chat_id']}",
                    'package': d.get('subscription_package'),
                    'end': end_iso,
                    'paid': float(d.get('total_paid_amount') or 0),
                    'status': status,
                    'firstSeen': d.get('first_seen'),
                })
                kpis['revenue'] += float(d.get('total_paid_amount') or 0)

                # هل هذا الاشتراك بدأ هذا الشهر؟
                if d.get('first_seen'):
                    try:
                        fs = datetime.fromisoformat(d['first_seen'])
                        if fs.year == now.year and fs.month == now.month:
                            kpis['thisMonth'] += 1
                    except (ValueError, TypeError):
                        pass

            settings = get_settings_fn()
            return jsonify({
                'status': 'ok',
                'subscriptions': subs,
                'packages': settings.get('packages', []),
                'kpis': kpis,
            })
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/subscriptions/manual', methods=['POST'])
    @_login_required
    def api_subscription_manual():
        """تفعيل اشتراك يدوياً للأدمن (بدون مرور بـ StreamPay)."""
        try:
            data = request.get_json(force=True) or {}
            chat_id = int(data.get('chat_id'))
            package_id = data.get('package_id')
            amount = float(data.get('amount', 0))
            payment_method = data.get('payment_method', 'manual')
            note = data.get('note', '')

            settings = get_settings_fn()
            package = next((p for p in settings.get('packages', [])
                            if str(p.get('id')) == str(package_id)), None)
            if not package:
                return jsonify({'status': 'error', 'message': 'الباقة غير موجودة'}), 404

            duration_days = int(package['duration_days'])
            end_date = datetime.now() + timedelta(days=duration_days)

            with _conn() as c:
                # هل العميل موجود؟
                exists = c.execute(
                    "SELECT chat_id FROM users WHERE chat_id = ?", (chat_id,)
                ).fetchone()

                if exists:
                    c.execute("""
                        UPDATE users
                        SET subscription_package = ?,
                            subscription_end = ?,
                            paid = 1,
                            is_frozen = 0,
                            frozen_days_remaining = NULL,
                            total_paid_amount = COALESCE(total_paid_amount,0) + ?
                        WHERE chat_id = ?
                    """, (package['name'], end_date.isoformat(), amount, chat_id))
                else:
                    c.execute("""
                        INSERT INTO users
                        (chat_id, name, paid, subscription_package, subscription_end,
                         first_seen, total_paid_amount, is_frozen)
                        VALUES (?, ?, 1, ?, ?, ?, ?, 0)
                    """, (chat_id, f"عميل {chat_id}", package['name'],
                          end_date.isoformat(), datetime.now().isoformat(), amount))

                c.execute("""
                    INSERT INTO manual_activations
                    (chat_id, package_id, amount, payment_method, activated_by, activated_at, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (chat_id, package_id, amount, payment_method,
                      session.get('username', 'admin'),
                      datetime.now().isoformat(), note))
                c.commit()

            log_audit(session.get('username', 'admin'), 'create',
                      f'subscription:{chat_id}',
                      details=f"manual activation: {package['name']} for {amount}")
            return jsonify({'status': 'ok', 'subscription_end': end_date.isoformat()})
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # ════════════════════════════════════════════════════
    #  5) API: طلبات السحب (Withdrawals)
    # ════════════════════════════════════════════════════
    @app.route('/api/withdrawals')
    @_login_required
    def api_withdrawals():
        try:
            status = request.args.get('status')  # pending | approved | rejected | None=all
            q = "SELECT w.*, u.name, u.username, u.phone_number FROM withdrawals w " \
                "LEFT JOIN users u ON u.chat_id = w.chat_id"
            params = ()
            if status:
                q += " WHERE w.status = ?"
                params = (status,)
            q += " ORDER BY w.requested_at DESC"

            with _conn() as c:
                rows = c.execute(q, params).fetchall()

            kpis = {'pending': 0, 'approved': 0, 'rejected': 0, 'totalPaid': 0.0}
            with _conn() as c:
                for r in c.execute("SELECT status, COUNT(*) c, SUM(amount) s FROM withdrawals GROUP BY status"):
                    if r['status'] == 'pending':
                        kpis['pending'] = r['c']
                    elif r['status'] == 'approved':
                        kpis['approved'] = r['c']
                        kpis['totalPaid'] = float(r['s'] or 0)
                    elif r['status'] == 'rejected':
                        kpis['rejected'] = r['c']

            return jsonify({
                'status': 'ok',
                'withdrawals': [dict(r) for r in rows],
                'kpis': kpis,
            })
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/withdrawals', methods=['POST'])
    def api_withdrawal_create():
        """
        إنشاء طلب سحب — يستدعى إما من جانب العميل (مع verify_telegram_init_data)
        أو من الأدمن (نيابة عن عميل).
        """
        try:
            # نقبل من العميل عبر التيليجرام أو الأدمن من الجلسة
            data = request.get_json(force=True) or {}
            chat_id = int(data.get('chat_id'))
            amount = float(data.get('amount', 0))

            if amount < 200:
                return jsonify({'status': 'error',
                                'message': 'الحد الأدنى للسحب 200 ر.س'}), 400

            beneficiary = (data.get('beneficiary_name') or '').strip()
            iban = (data.get('iban') or '').strip()
            bank = (data.get('bank_name') or '').strip()

            if not beneficiary or not iban:
                return jsonify({'status': 'error',
                                'message': 'اسم المستفيد و IBAN مطلوبان'}), 400

            # تحقق من وجود رصيد كافٍ
            with _conn() as c:
                bal_row = c.execute("""
                    SELECT COALESCE(SUM(amount), 0) AS bal
                    FROM wallet_ledger WHERE chat_id = ?
                """, (chat_id,)).fetchone()
                balance = float(bal_row['bal'])

                if balance < amount:
                    return jsonify({'status': 'error',
                                    'message': f'الرصيد غير كافٍ. متاح: {balance:.2f}'}), 400

                cursor = c.execute("""
                    INSERT INTO withdrawals
                    (chat_id, amount, beneficiary_name, iban, bank_name,
                     status, requested_at)
                    VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """, (chat_id, amount, beneficiary, iban, bank,
                      datetime.now().isoformat()))
                wid = cursor.lastrowid
                c.commit()

            log_audit(f'client:{chat_id}', 'create', f'withdrawal:{wid}',
                      details=f'requested {amount}')
            return jsonify({'status': 'ok', 'id': wid})
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/withdrawals/<int:wid>/approve', methods=['POST'])
    @_login_required
    def api_withdrawal_approve(wid):
        try:
            data = request.get_json(silent=True) or {}
            note = data.get('note', '')
            receipt = data.get('receipt_path', '')

            with _conn() as c:
                w = c.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)).fetchone()
                if not w:
                    return jsonify({'status': 'error', 'message': 'غير موجود'}), 404
                if w['status'] != 'pending':
                    return jsonify({'status': 'error',
                                    'message': f"الطلب حالته {w['status']} بالفعل"}), 400

                c.execute("""
                    UPDATE withdrawals SET status='approved', processed_at=?,
                                            processed_by=?, note=?, receipt_path=?
                    WHERE id=?
                """, (datetime.now().isoformat(),
                      session.get('username', 'admin'),
                      note, receipt, wid))

                # خصم من المحفظة
                c.execute("""
                    INSERT INTO wallet_ledger
                    (chat_id, amount, source, description, created_at)
                    VALUES (?, ?, 'withdrawal', ?, ?)
                """, (w['chat_id'], -float(w['amount']),
                      f'سحب رقم #{wid}', datetime.now().isoformat()))
                c.commit()

            # إشعار العميل
            if _BOT_TOKEN:
                _send_telegram_message(
                    w['chat_id'],
                    f"✅ تم اعتماد طلب السحب الخاص بك بمبلغ <b>{w['amount']:.2f} ر.س</b>\n"
                    f"سيصل المبلغ خلال أيام العمل."
                )

            log_audit(session.get('username', 'admin'), 'payment',
                      f'withdrawal:{wid}', details=f'approved {w["amount"]}')
            return jsonify({'status': 'ok'})
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/withdrawals/<int:wid>/reject', methods=['POST'])
    @_login_required
    def api_withdrawal_reject(wid):
        try:
            data = request.get_json(silent=True) or {}
            note = data.get('note', 'مرفوض')

            with _conn() as c:
                w = c.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)).fetchone()
                if not w:
                    return jsonify({'status': 'error', 'message': 'غير موجود'}), 404
                if w['status'] != 'pending':
                    return jsonify({'status': 'error',
                                    'message': f"الطلب حالته {w['status']} بالفعل"}), 400

                c.execute("""
                    UPDATE withdrawals SET status='rejected', processed_at=?,
                                            processed_by=?, note=?
                    WHERE id=?
                """, (datetime.now().isoformat(),
                      session.get('username', 'admin'), note, wid))
                c.commit()

            if _BOT_TOKEN:
                _send_telegram_message(
                    w['chat_id'],
                    f"❌ تم رفض طلب السحب الخاص بك بمبلغ {w['amount']:.2f} ر.س\n"
                    f"السبب: {note}"
                )

            log_audit(session.get('username', 'admin'), 'warning',
                      f'withdrawal:{wid}', details=f'rejected: {note}')
            return jsonify({'status': 'ok'})
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # ════════════════════════════════════════════════════
    #  6) API: الإحالات (Referrals)
    # ════════════════════════════════════════════════════
    @app.route('/api/referrals')
    @_login_required
    def api_referrals():
        try:
            with _conn() as c:
                # كل العملاء الذين عندهم إحالات (referrer)
                referees = c.execute("""
                    SELECT u.chat_id, u.name, u.username, u.referred_by_code,
                           u.first_seen, u.total_paid_amount, u.subscription_package,
                           r.chat_id AS referrer_id, r.name AS referrer_name,
                           r.username AS referrer_username
                    FROM users u
                    LEFT JOIN users r ON r.referral_code = u.referred_by_code
                    WHERE u.referred_by_code IS NOT NULL
                          AND u.referred_by_code != ''
                    ORDER BY u.first_seen DESC
                """).fetchall()

                # أفضل المُحيلين
                leaders = c.execute("""
                    SELECT chat_id, name, username, referral_code,
                           referral_count, total_paid_amount
                    FROM users
                    WHERE referral_count > 0
                    ORDER BY referral_count DESC LIMIT 10
                """).fetchall()

            settings = get_settings_fn()
            ref_settings = settings.get('referral_settings',
                                        {'first_time_bonus': 10, 'renewal_bonus': 3})

            return jsonify({
                'status': 'ok',
                'referrals': [dict(r) for r in referees],
                'leaders': [dict(r) for r in leaders],
                'settings': ref_settings,
                'kpis': {
                    'total': len(referees),
                    'topReferrer': dict(leaders[0]) if leaders else None,
                }
            })
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # ════════════════════════════════════════════════════
    #  7) API: الإشعارات الجماعية (Notifications)
    # ════════════════════════════════════════════════════
    @app.route('/api/notifications/segments')
    @_login_required
    def api_notification_segments():
        """يعيد عدد المستلمين في كل شريحة (للأزرار)."""
        try:
            now = datetime.now()
            soon = now + timedelta(days=7)
            with _conn() as c:
                total = c.execute("SELECT COUNT(*) c FROM users").fetchone()['c']
                expired = c.execute("""
                    SELECT COUNT(*) c FROM users
                    WHERE subscription_end IS NOT NULL
                      AND datetime(subscription_end) < ?
                """, (now.isoformat(),)).fetchone()['c']
                expiring = c.execute("""
                    SELECT COUNT(*) c FROM users
                    WHERE subscription_end IS NOT NULL
                      AND datetime(subscription_end) BETWEEN ? AND ?
                """, (now.isoformat(), soon.isoformat())).fetchone()['c']
                vip = c.execute("""
                    SELECT COUNT(*) c FROM users
                    WHERE subscription_package LIKE '%VIP%'
                       OR subscription_package LIKE '%بلاتين%'
                """).fetchone()['c']

            return jsonify({
                'status': 'ok',
                'segments': {
                    'all': total,
                    'expired': expired,
                    'expiring': expiring,
                    'vip': vip,
                }
            })
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/notifications/send', methods=['POST'])
    @_login_required
    def api_notification_send():
        """
        إرسال إشعار جماعي.
        Body: {title, message, link?, segment: all|expired|expiring|vip|custom_ids,
               custom_ids?: [int], send_via: telegram }
        """
        try:
            data = request.get_json(force=True) or {}
            title = data.get('title', '').strip()
            message = data.get('message', '').strip()
            link = data.get('link', '')
            segment = data.get('segment', 'all')
            custom_ids = data.get('custom_ids', [])

            if not message:
                return jsonify({'status': 'error',
                                'message': 'نص الإشعار مطلوب'}), 400

            # جلب قائمة المستلمين حسب الشريحة
            now = datetime.now()
            soon = now + timedelta(days=7)
            with _conn() as c:
                if segment == 'custom_ids':
                    recipients = [int(x) for x in custom_ids if str(x).isdigit()]
                elif segment == 'expired':
                    rs = c.execute("""
                        SELECT chat_id FROM users
                        WHERE subscription_end IS NOT NULL
                          AND datetime(subscription_end) < ?
                    """, (now.isoformat(),)).fetchall()
                    recipients = [r['chat_id'] for r in rs]
                elif segment == 'expiring':
                    rs = c.execute("""
                        SELECT chat_id FROM users
                        WHERE subscription_end IS NOT NULL
                          AND datetime(subscription_end) BETWEEN ? AND ?
                    """, (now.isoformat(), soon.isoformat())).fetchall()
                    recipients = [r['chat_id'] for r in rs]
                elif segment == 'vip':
                    rs = c.execute("""
                        SELECT chat_id FROM users
                        WHERE subscription_package LIKE '%VIP%'
                           OR subscription_package LIKE '%بلاتين%'
                    """).fetchall()
                    recipients = [r['chat_id'] for r in rs]
                else:  # all
                    rs = c.execute("SELECT chat_id FROM users").fetchall()
                    recipients = [r['chat_id'] for r in rs]

            # بناء النص النهائي
            final_text = f"<b>{title}</b>\n\n{message}" if title else message
            if link:
                final_text += f"\n\n🔗 <a href=\"{link}\">اضغط هنا</a>"

            # إرسال (مع تأخير بسيط لتجنب rate limit)
            sent = 0
            failed = 0
            for cid in recipients:
                ok = _send_telegram_message(cid, final_text)
                if ok:
                    sent += 1
                else:
                    failed += 1
                time.sleep(0.04)  # ~25 msg/s

            log_audit(session.get('username', 'admin'), 'create',
                      f'notification:{segment}',
                      details=f'sent={sent} failed={failed}')

            return jsonify({
                'status': 'ok',
                'segment': segment,
                'total_recipients': len(recipients),
                'sent': sent,
                'failed': failed,
            })
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # ════════════════════════════════════════════════════
    #  8) API: سجل الأدمن (Audit Log)
    # ════════════════════════════════════════════════════
    @app.route('/api/auditlog')
    @_login_required
    def api_auditlog():
        try:
            action = request.args.get('action')  # filter
            q = request.args.get('q', '').strip()
            limit = request.args.get('limit', 200, type=int)

            sql = "SELECT * FROM audit_log"
            conds = []
            params = []
            if action and action != 'all':
                conds.append("action = ?")
                params.append(action)
            if q:
                conds.append("(user LIKE ? OR target LIKE ? OR details LIKE ? OR ip LIKE ?)")
                params.extend([f"%{q}%"] * 4)
            if conds:
                sql += " WHERE " + " AND ".join(conds)
            sql += " ORDER BY ts DESC LIMIT ?"
            params.append(limit)

            with _conn() as c:
                rows = c.execute(sql, params).fetchall()

            # إحصائيات
            with _conn() as c:
                stats = {}
                for r in c.execute("SELECT action, COUNT(*) c FROM audit_log GROUP BY action"):
                    stats[r['action']] = r['c']

            return jsonify({
                'status': 'ok',
                'logs': [dict(r) for r in rows],
                'stats': stats,
            })
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/auditlog/export')
    @_login_required
    def api_auditlog_export():
        try:
            with _conn() as c:
                rows = c.execute(
                    "SELECT * FROM audit_log ORDER BY ts DESC"
                ).fetchall()

            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(['id', 'user', 'action', 'target', 'ip', 'ts', 'details'])
            for r in rows:
                writer.writerow([r['id'], r['user'], r['action'],
                                 r['target'], r['ip'], r['ts'], r['details']])

            buf.seek(0)
            return send_file(
                io.BytesIO(buf.getvalue().encode('utf-8-sig')),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f"auditlog_{datetime.now():%Y%m%d_%H%M%S}.csv"
            )
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # ════════════════════════════════════════════════════
    #  9) API: لوحة العميل (Client-side)
    # ════════════════════════════════════════════════════
    # ملاحظة: في الإنتاج يجب التحقق من Telegram WebApp initData hash.
    # هنا نستخدم chat_id من query string + التحقق أنه موجود في قاعدة البيانات.
    # يُستحسن إضافة JWT أو HMAC في وقت لاحق.

    def _verify_client(chat_id):
        """تحقق سطحي من أن العميل موجود."""
        with _conn() as c:
            r = c.execute("SELECT chat_id FROM users WHERE chat_id = ?",
                          (chat_id,)).fetchone()
            return r is not None

    @app.route('/api/client/me')
    def api_client_me():
        try:
            chat_id = int(request.args.get('chat_id', 0))
            if not _verify_client(chat_id):
                return jsonify({'status': 'error', 'message': 'not found'}), 404

            with _conn() as c:
                row = c.execute(
                    "SELECT * FROM users WHERE chat_id = ?", (chat_id,)
                ).fetchone()
                bal_row = c.execute("""
                    SELECT COALESCE(SUM(amount), 0) AS bal
                    FROM wallet_ledger WHERE chat_id = ?
                """, (chat_id,)).fetchone()

            d = dict(row)
            d['wallet_balance'] = float(bal_row['bal'])
            return jsonify({'status': 'ok', 'me': d})
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/client/wallet')
    def api_client_wallet():
        try:
            chat_id = int(request.args.get('chat_id', 0))
            if not _verify_client(chat_id):
                return jsonify({'status': 'error', 'message': 'not found'}), 404

            with _conn() as c:
                ledger = c.execute("""
                    SELECT * FROM wallet_ledger
                    WHERE chat_id = ? ORDER BY created_at DESC LIMIT 100
                """, (chat_id,)).fetchall()
                bal_row = c.execute("""
                    SELECT COALESCE(SUM(amount), 0) AS bal
                    FROM wallet_ledger WHERE chat_id = ?
                """, (chat_id,)).fetchone()

            return jsonify({
                'status': 'ok',
                'balance': float(bal_row['bal']),
                'ledger': [dict(x) for x in ledger]
            })
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/client/trades')
    def api_client_trades():
        """الصفقات للعميل — نفس صفقات الـ Dashboard لكن read-only."""
        try:
            chat_id = int(request.args.get('chat_id', 0))
            if not _verify_client(chat_id):
                return jsonify({'status': 'error', 'message': 'not found'}), 404

            limit = request.args.get('limit', 50, type=int)
            df = get_data_fn(None, None)
            data = _trades_to_json_for_dashboard(df)[-limit:][::-1]
            return jsonify({'status': 'ok', 'trades': data})
        except Exception as e:
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': str(e)}), 500

    print("✅ تم تسجيل كل الـ endpoints الجديدة:")
    print("   📊 /api/trades, /api/trades/recent, /api/dashboard/stats")
    print("   👥 /api/clients, /api/clients/<id>")
    print("   💎 /api/subscriptions, /api/subscriptions/manual")
    print("   💸 /api/withdrawals (+approve/reject)")
    print("   🤝 /api/referrals")
    print("   🔔 /api/notifications/send, /api/notifications/segments")
    print("   📋 /api/auditlog (+export)")
    print("   👤 /api/client/me, /wallet, /trades")
    print("   🖥️ /admin (SPA shell), /admin/<page>.html")
    print("   📱 /client-area (Telegram WebApp)")
