# ===============================================================
#  Ayman Activation Server + Admin Panel PRO (Bootstrap + Charts)
#  - REST API للبرنامج AutoClicker
#  - لوحة تحكم احترافية: Dashboard / Pending / Active / Banned / Settings / Logs / Device Details
#  - Ban / Unban / Renew / Pause / Unactivate / Delete
#  - Logs لكل عمليات الأدمن
#  - إرسال إيميل للعميل عند التفعيل / التجديد
# ===============================================================

from flask import (
    Flask, request, jsonify, render_template_string,
    redirect, url_for, session, flash
)
import hashlib
import json
import os
import re
from datetime import datetime, date, timedelta

# لإرسال الإيميلات
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ============================================================
#  إعدادات عامة
# ============================================================

DB_FILE = "clients_db.json"

# مفتاح التشفير المستخدم في توليد كود التفعيل
DEFAULT_SECRET_KEY = "AYMAN_SUPER_SECRET_2025"

# إعدادات الدخول للوحة الأدمن (يمكنك تغييرها من /admin/settings)
DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASS = "admin1234"   # أول مرة – غيّره من لوحة الإعدادات

# رقم الواتساب الافتراضي (يظهر للعميل في الردود)
DEFAULT_ADMIN_WHATSAPP = "07829004566"

# رابط صفحة التحميل (GitHub أو غيره)
DOWNLOAD_URL = "https://github.com/your-account/ayman-autoclicker"  # عدّل الرابط حسب مشروعك

# Flask app
app = Flask(__name__)
app.secret_key = "CHANGE_ME_SESSION_SECRET_AYMAN"  # غيّره في السيرفر (Render) إلى قيمة سرية


# ============================================================
#  دوال مساعدة للـ DB
# ============================================================

def now_iso():
    return datetime.utcnow().isoformat()


def load_db():
    """
    بنية ملف JSON:
    {
      "settings": {...},
      "clients": [ {...}, {...} ],
      "logs": [ {...}, ... ]
    }
    """

    # --- الإعدادات الافتراضية (تشمل SMTP) ---
    default_settings = {
        "admin_user": DEFAULT_ADMIN_USER,
        "admin_pass": DEFAULT_ADMIN_PASS,
        "secret_key": DEFAULT_SECRET_KEY,
        "default_plan": "M",
        "max_devices": 1000,
        "admin_whatsapp": DEFAULT_ADMIN_WHATSAPP,

        # === إعدادات الإيميل ===
        "email_enabled": False,      # تشغيل/إيقاف الإيميل
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_ssl": False,           # False = TLS / True = SSL
        "smtp_user": "",
        "smtp_password": "",
        "smtp_sender": "Ayman Software <noreply@ayman.com>",
        "admin_notify_email": ""
    }

    # --- إذا الملف غير موجود ---
    if not os.path.exists(DB_FILE):
        return {
            "settings": default_settings.copy(),
            "clients": [],
            "logs": []
        }

    # --- تحميل DB ---
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        return {
            "settings": default_settings.copy(),
            "clients": [],
            "logs": []
        }

    # --- تحويل الملف القديم (list فقط) ---
    if isinstance(data, list):
        return {
            "settings": default_settings.copy(),
            "clients": data,
            "logs": []
        }

    # تأكد من settings
    if "settings" not in data or not isinstance(data["settings"], dict):
        data["settings"] = default_settings.copy()
    else:
        for key, value in default_settings.items():
            if key not in data["settings"]:
                data["settings"][key] = value

    # تأكد من clients
    if "clients" not in data or not isinstance(data["clients"], list):
        data["clients"] = []

    # تأكد من logs
    if "logs" not in data or not isinstance(data["logs"], list):
        data["logs"] = []

    return data


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)


def add_log(db, action, machine_id=None, note="", level="info"):
    """
    إضافة سجل في logs (لا تستدعي save_db هنا، اتركه للمستدعي)
    """
    logs = db.setdefault("logs", [])
    logs.append({
        "time": now_iso(),
        "action": action,
        "machine_id": machine_id,
        "note": note,
        "level": level
    })
    # تقليل الحجم إذا كبر كثيراً
    if len(logs) > 1000:
        del logs[:-1000]


def normalize_machine_id(raw: str) -> str:
    raw = (raw or "").strip().upper()
    raw = re.sub(r"[^0-9A-F]", "", raw)
    return raw[:16]


def format_machine_id(mid: str) -> str:
    mid = normalize_machine_id(mid)
    if len(mid) < 16:
        mid = mid.ljust(16, "0")
    return f"{mid[:4]}-{mid[4:8]}-{mid[8:12]}-{mid[12:16]}"


def find_client_by_mid(clients, mid_norm):
    for c in clients:
        if c.get("machine_id") == mid_norm:
            return c
    return None


def generate_license_code(machine_id: str, plan: str, secret_key: str) -> str:
    base = f"{machine_id}{plan}{secret_key}"
    d = hashlib.sha256(base.encode("utf-8")).hexdigest()
    num = int(d, 16) % (10**16)
    return f"{num:016d}"


# ============================================================
#  نظام إرسال الإيميل SMTP
# ============================================================

import smtplib
import ssl
from email.message import EmailMessage

def send_email_smtp(to_email: str, subject: str, body: str, settings: dict):
    """
    يرسل رسالة إيميل عبر SMTP.
    """

    if not settings.get("email_enabled"):
        return False

    smtp_user = settings.get("smtp_user")
    smtp_pass = settings.get("smtp_password")
    smtp_server = settings.get("smtp_server")
    smtp_port = int(settings.get("smtp_port", 587))
    smtp_ssl = settings.get("smtp_ssl", False)
    smtp_sender = settings.get("smtp_sender", smtp_user)

    if not smtp_user or not smtp_pass or not smtp_server:
        return False  # إعدادات ناقصة

    msg = EmailMessage()
    msg["From"] = smtp_sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        if smtp_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

        else:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

        # إرسال نسخة إلى المطور
        dev_email = settings.get("admin_notify_email")
        if dev_email:
            msg2 = EmailMessage()
            msg2["From"] = smtp_sender
            msg2["To"] = dev_email
            msg2["Subject"] = f"[Copy] {subject}"
            msg2.set_content(body)
            server.send_message(msg2)

        return True

    except Exception as e:
        print("SMTP Error:", e)
        return False


# ============================================================
#  إرسال الإيميل للعميل عند التفعيل / التجديد
# ============================================================

def send_activation_email(client: dict, settings: dict, is_renew: bool = False):
    to_email = (client.get("email") or "").strip()
    if not to_email:
        return

    name = client.get("name") or "عميلنا الكريم"
    machine_id_disp = client.get("machine_id_display") or "-"
    plan = client.get("plan", "M")
    expire_date = client.get("expire_date") or "-"
    license_code = client.get("license_code") or "-"
    whatsapp = settings.get("admin_whatsapp", DEFAULT_ADMIN_WHATSAPP)

    plan_text = "شهري (30 يوم)" if plan == "M" else "سنوي (365 يوم)"

    subject = (
        "تم تفعيل اشتراكك في Ayman Auto Clicker"
        if not is_renew else
        "تم تجديد اشتراكك في Ayman Auto Clicker"
    )

    body = f"""
مرحباً {name}،

تم {'تفعيل' if not is_renew else 'تجديد'} اشتراكك في برنامج Ayman Auto Clicker.

البيانات:
- Machine ID: {machine_id_disp}
- الخطة: {plan_text}
- كود التفعيل: {license_code}
- ينتهي في: {expire_date}

رابط التحميل:
{DOWNLOAD_URL}

للدعم الفني:
واتساب: {whatsapp}

تحياتنا،
Ayman Software
"""

    send_email_smtp(to_email, subject, body, settings)


# ============================================================
#  Authentication (لوحة الأدمن)
# ============================================================

def is_logged_in():
    return session.get("admin_logged_in") is True


def login_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for("admin_login"))
        return func(*args, **kwargs)

    return wrapper


# ============================================================
#  صفحات بسيطة
# ============================================================

@app.route("/")
def home():
    return "<h2>Ayman Activation Server Running ✔</h2><p>اذهب إلى <a href='/admin'>لوحة التحكم</a></p>"


# ============================================================
#  1) API: طلب تفعيل من داخل البرنامج
# ============================================================

@app.route("/api/request_activation", methods=["POST"])
def api_request_activation():
    db = load_db()
    settings = db["settings"]
    clients = db["clients"]

    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    raw_mid = (data.get("machine_id") or "").strip()
    plan = (data.get("plan") or settings.get("default_plan", "M")).strip().upper()
    version = (data.get("version") or "").strip()
    system_info = data.get("system") or {}

    if not raw_mid:
        return jsonify({"status": "error", "message": "machine_id مفقود"}), 400

    if plan not in ("M", "Y"):
        plan = settings.get("default_plan", "M")

    mid_norm = normalize_machine_id(raw_mid)

    client = find_client_by_mid(clients, mid_norm)
    now = now_iso()

    # لو العميل موجود
    if client:
        if client.get("status") == "banned":
            return jsonify({
                "status": "banned",
                "message": "هذا الجهاز محظور من قبل النظام."
            }), 403

        current_status = client.get("status")

        if current_status == "active":
            changed = False
            if name and name != (client.get("name") or ""):
                changed = True
            if email and email != (client.get("email") or ""):
                changed = True
            if phone and phone != (client.get("phone") or ""):
                changed = True

            if changed:
                client["suspicious_count"] = client.get("suspicious_count", 0) + 1

            client["version"] = version or client.get("version", "")
            client["system_info"] = system_info or client.get("system_info", {})
            client["last_request_at"] = now
            client["updated_at"] = now

        else:
            changed = False
            if name and name != client.get("name"):
                changed = True
            if email and email != client.get("email"):
                changed = True
            if phone and phone != client.get("phone"):
                changed = True

            if changed:
                client["suspicious_count"] = client.get("suspicious_count", 0) + 1

            client["name"] = name or client.get("name", "")
            client["email"] = email or client.get("email", "")
            client["phone"] = phone or client.get("phone", "")
            client["plan"] = plan
            client["version"] = version or client.get("version", "")
            client["system_info"] = system_info or client.get("system_info", {})
            client["last_request_at"] = now
            client["updated_at"] = now

            if client.get("status") in (None, "", "not_found", "rejected", "expired", "paused"):
                client["status"] = "pending"

    else:
        new_client = {
            "id": len(clients) + 1,
            "name": name,
            "email": email,
            "phone": phone,
            "machine_id": mid_norm,
            "machine_id_display": format_machine_id(mid_norm),
            "plan": plan,
            "license_code": None,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "expire_date": None,
            "notes": "",
            "version": version,
            "system_info": system_info,
            "suspicious_count": 0,
            "last_request_at": now,
            "banned_reason": None
        }
        clients.append(new_client)

    add_log(db, "api_request_activation", mid_norm, note="جهاز أرسل طلب تفعيل")
    save_db(db)

    return jsonify({
        "status": "pending",
        "message": "تم استلام طلب التفعيل. سيتم مراجعته من قِبل المطوّر.",
        "whatsapp": settings.get("admin_whatsapp", DEFAULT_ADMIN_WHATSAPP)
    })


# ============================================================
#  2) API: تحقق من حالة التفعيل
# ============================================================

@app.route("/api/check_status", methods=["GET"])
def api_check_status():
    db = load_db()
    clients = db["clients"]

    raw_mid = request.args.get("machine_id", "").strip()
    if not raw_mid:
        return jsonify({"status": "error", "message": "machine_id مفقود"}), 400

    mid_norm = normalize_machine_id(raw_mid)
    client = find_client_by_mid(clients, mid_norm)

    if not client:
        return jsonify({"status": "not_found", "message": "لا يوجد هذا الجهاز في النظام."})

    status = client.get("status", "pending")
    expire_str = client.get("expire_date")
    expire_dt = None
    if expire_str:
        try:
            expire_dt = datetime.strptime(expire_str, "%Y-%m-%d").date()
        except:
            expire_dt = None

    today = date.today()
    if status == "active" and expire_dt and today > expire_dt:
        status = "expired"
        client["status"] = "expired"
        client["updated_at"] = now_iso()
        save_db(db)

    if status == "banned":
        return jsonify({
            "status": "banned",
            "message": client.get("banned_reason", "تم حظر هذا الجهاز."),
            "name": client.get("name"),
            "email": client.get("email"),
            "phone": client.get("phone"),
            "suspicious_count": client.get("suspicious_count", 0)
        })

    return jsonify({
        "status": status,
        "plan": client.get("plan"),
        "license_code": client.get("license_code"),
        "expire_date": client.get("expire_date"),
        "name": client.get("name"),
        "email": client.get("email"),
        "phone": client.get("phone"),
        "suspicious_count": client.get("suspicious_count", 0)
    })


# ============================================================
#  3) لوحة الأدمن – Login
# ============================================================

LOGIN_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>تسجيل دخول الأدمن</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<div class="container" style="max-width: 420px; margin-top: 80px;">
  <div class="card shadow">
    <div class="card-header text-center bg-primary text-white">
      <h5 class="mb-0">لوحة إدارة التفعيل - تسجيل دخول</h5>
    </div>
    <div class="card-body">
      {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for cat, msg in messages %}
          <div class="alert alert-{{cat}} py-1 my-1">{{ msg }}</div>
        {% endfor %}
      {% endif %}
      {% endwith %}
      <form method="post">
        <div class="mb-3">
          <label class="form-label">اسم المستخدم</label>
          <input type="text" name="username" class="form-control" autofocus>
        </div>
        <div class="mb-3">
          <label class="form-label">كلمة المرور</label>
          <input type="password" name="password" class="form-control">
        </div>
        <button class="btn btn-primary w-100">دخول</button>
      </form>
    </div>
  </div>
</div>
</body>
</html>
"""

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    db = load_db()
    settings = db["settings"]

    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")

        if u == settings.get("admin_user") and p == settings.get("admin_pass"):
            session["admin_logged_in"] = True
            add_log(db, "admin_login_success", None, note=f"Login by {u}", level="info")
            save_db(db)
            return redirect(url_for("admin_dashboard"))
        else:
            add_log(db, "admin_login_failed", None, note=f"Failed login with user={u}", level="warning")
            save_db(db)
            flash("بيانات الدخول غير صحيحة", "danger")

    return render_template_string(LOGIN_TEMPLATE)


@app.route("/admin/logout")
def admin_logout():
    db = load_db()
    add_log(db, "admin_logout", None, note="Admin logged out", level="info")
    save_db(db)
    session.clear()
    return redirect(url_for("admin_login"))


# ============================================================
#  4) لوحة الأدمن – Dashboard PRO
# ============================================================

DASHBOARD_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>لوحة التفعيل PRO - Ayman</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
  <style>
    body { background:#f5f5f5; }
    .status-pending { background-color:#fff8e1; }
    .status-active  { background-color:#e8f5e9; }
    .status-banned  { background-color:#ffebee; }
    .status-expired { background-color:#fff3e0; }
    .status-paused  { background-color:#e3f2fd; }
    .sidebar {
      min-height: 100vh;
      background: #212529;
      color: #fff;
    }
    .sidebar a {
      color: #ddd;
      text-decoration: none;
      display: block;
      padding: 8px 12px;
      border-radius: 4px;
      margin-bottom: 4px;
    }
    .sidebar a.active, .sidebar a:hover {
      background: #495057;
      color: #fff;
    }
  </style>
</head>
<body>
<nav class="navbar navbar-dark bg-dark">
  <div class="container-fluid">
    <span class="navbar-brand">لوحة تفعيل AutoClicker PRO</span>
    <div class="d-flex">
      <a href="{{ url_for('admin_settings') }}" class="btn btn-outline-light btn-sm mx-1">الإعدادات</a>
      <a href="{{ url_for('admin_logs') }}" class="btn btn-outline-info btn-sm mx-1">السجلات (Logs)</a>
      <a href="{{ url_for('admin_logout') }}" class="btn btn-outline-warning btn-sm mx-1">خروج</a>
    </div>
  </div>
</nav>

<div class="container-fluid">
  <div class="row">
    <!-- Sidebar -->
    <div class="col-md-2 sidebar p-3">
      <h6 class="text-uppercase text-muted">القائمة</h6>
      <a href="{{ url_for('admin_dashboard') }}" class="active">Dashboard</a>
      <a href="#pending">طلبات التفعيل (Pending)</a>
      <a href="#active">الأجهزة المفعّلة (Active)</a>
      <a href="#banned">الأجهزة المحظورة (Banned)</a>
      <a href="{{ url_for('admin_logs') }}">سجلات النظام (Logs)</a>
      <a href="{{ url_for('admin_settings') }}">إعدادات السيرفر</a>
    </div>

    <!-- Main content -->
    <div class="col-md-10 py-3">

      {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for cat, msg in messages %}
          <div class="alert alert-{{cat}} py-1 my-1">{{ msg }}</div>
        {% endfor %}
      {% endif %}
      {% endwith %}

      <!-- كروت الإحصائيات -->
      <div class="row mb-3">
        <div class="col-md-2">
          <div class="card text-bg-warning mb-2">
            <div class="card-body py-2">
              <div class="d-flex justify-content-between">
                <span>Pending</span>
                <strong>{{ pending_count }}</strong>
              </div>
            </div>
          </div>
        </div>
        <div class="col-md-2">
          <div class="card text-bg-success mb-2">
            <div class="card-body py-2">
              <div class="d-flex justify-content-between">
                <span>Active</span>
                <strong>{{ active_count }}</strong>
              </div>
            </div>
          </div>
        </div>
        <div class="col-md-2">
          <div class="card text-bg-danger mb-2">
            <div class="card-body py-2">
              <div class="d-flex justify-content-between">
                <span>Banned</span>
                <strong>{{ banned_count }}</strong>
              </div>
            </div>
          </div>
        </div>
        <div class="col-md-2">
          <div class="card text-bg-secondary mb-2">
            <div class="card-body py-2">
              <div class="d-flex justify-content-between">
                <span>Expired</span>
                <strong>{{ expired_count }}</strong>
              </div>
            </div>
          </div>
        </div>
        <div class="col-md-2">
          <div class="card text-bg-info mb-2">
            <div class="card-body py-2">
              <div class="d-flex justify-content-between">
                <span>Paused</span>
                <strong>{{ paused_count }}</strong>
              </div>
            </div>
          </div>
        </div>
        <div class="col-md-2">
          <div class="card text-bg-dark mb-2">
            <div class="card-body py-2">
              <div class="d-flex justify-content-between">
                <span>Total</span>
                <strong>{{ total_count }}</strong>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- مخطط Chart.js -->
      <div class="card mb-3">
        <div class="card-header">مخطط حالة الأجهزة</div>
        <div class="card-body">
          <canvas id="statusChart" height="80"></canvas>
        </div>
      </div>

      <!-- تبويبات -->
      <ul class="nav nav-tabs" id="myTab" role="tablist">
        <li class="nav-item" role="presentation">
          <button class="nav-link active" id="pending-tab" data-bs-toggle="tab" data-bs-target="#pending" type="button" role="tab">طلبات التفعيل (Pending)</button>
        </li>
        <li class="nav-item" role="presentation">
          <button class="nav-link" id="active-tab" data-bs-toggle="tab" data-bs-target="#active" type="button" role="tab">الأجهزة المفعّلة (Active)</button>
        </li>
        <li class="nav-item" role="presentation">
          <button class="nav-link" id="banned-tab" data-bs-toggle="tab" data-bs-target="#banned" type="button" role="tab">الأجهزة المحظورة (Banned)</button>
        </li>
      </ul>

      <div class="tab-content mt-3">
        <!-- Pending -->
        <div class="tab-pane fade show active" id="pending" role="tabpanel">
          <div class="table-responsive">
            <table class="table table-sm table-hover align-middle">
              <thead class="table-light">
                <tr>
                  <th>#</th>
                  <th>الاسم</th>
                  <th>البريد</th>
                  <th>الهاتف</th>
                  <th>Machine ID</th>
                  <th>الخطة</th>
                  <th>طلب في</th>
                  <th>إجراءات</th>
                </tr>
              </thead>
              <tbody>
              {% for c in pending %}
                <tr class="status-pending">
                  <td>{{ loop.index }}</td>
                  <td>{{ c.name }}</td>
                  <td>{{ c.email }}</td>
                  <td>{{ c.phone }}</td>
                  <td>
                    <a href="{{ url_for('admin_device', mid=c.machine_id) }}">{{ c.machine_id_display }}</a>
                  </td>
                  <td>{{ c.plan }}</td>
                  <td>{{ c.created_at }}</td>
                  <td>
                    <form class="d-inline" method="post" action="{{ url_for('admin_action') }}">
                      <input type="hidden" name="machine_id" value="{{ c.machine_id }}">
                      <input type="hidden" name="action" value="activate">
                      <button class="btn btn-success btn-sm">تفعيل 30/365 حسب الخطة</button>
                    </form>
                    <form class="d-inline" method="post" action="{{ url_for('admin_action') }}">
                      <input type="hidden" name="machine_id" value="{{ c.machine_id }}">
                      <input type="hidden" name="action" value="reject">
                      <button class="btn btn-secondary btn-sm">رفض</button>
                    </form>
                    <form class="d-inline" method="post" action="{{ url_for('admin_action') }}">
                      <input type="hidden" name="machine_id" value="{{ c.machine_id }}">
                      <input type="hidden" name="action" value="ban">
                      <input type="hidden" name="reason" value="Suspicious or fake data">
                      <button class="btn btn-danger btn-sm">حظر</button>
                    </form>
                  </td>
                </tr>
              {% endfor %}
              </tbody>
            </table>
          </div>
        </div>

        <!-- Active -->
        <div class="tab-pane fade" id="active" role="tabpanel">
          <div class="table-responsive">
            <table class="table table-sm table-hover align-middle">
              <thead class="table-light">
                <tr>
                  <th>#</th>
                  <th>الاسم</th>
                  <th>البريد</th>
                  <th>Machine ID</th>
                  <th>الخطة</th>
                  <th>ينتهي في</th>
                  <th>محاولات تلاعب</th>
                  <th>إجراءات</th>
                </tr>
              </thead>
              <tbody>
              {% for c in active %}
                <tr class="status-active">
                  <td>{{ loop.index }}</td>
                  <td>{{ c.name }}</td>
                  <td>{{ c.email }}</td>
                  <td>
                    <a href="{{ url_for('admin_device', mid=c.machine_id) }}">{{ c.machine_id_display }}</a>
                  </td>
                  <td>{{ c.plan }}</td>
                  <td>{{ c.expire_date }}</td>
                  <td>{{ c.suspicious_count or 0 }}</td>
                  <td>
                    <form class="d-inline" method="post" action="{{ url_for('admin_action') }}">
                      <input type="hidden" name="machine_id" value="{{ c.machine_id }}">
                      <input type="hidden" name="action" value="renew">
                      <button class="btn btn-primary btn-sm">تجديد (نفس الخطة)</button>
                    </form>
                    <form class="d-inline" method="post" action="{{ url_for('admin_action') }}">
                      <input type="hidden" name="machine_id" value="{{ c.machine_id }}">
                      <input type="hidden" name="action" value="pause">
                      <button class="btn btn-warning btn-sm">إيقاف مؤقت</button>
                    </form>
                    <form class="d-inline" method="post" action="{{ url_for('admin_action') }}">
                      <input type="hidden" name="machine_id" value="{{ c.machine_id }}">
                      <input type="hidden" name="action" value="unactivate">
                      <button class="btn btn-secondary btn-sm">إلغاء التفعيل</button>
                    </form>
                    <form class="d-inline" method="post" action="{{ url_for('admin_action') }}">
                      <input type="hidden" name="machine_id" value="{{ c.machine_id }}">
                      <input type="hidden" name="action" value="ban">
                      <input type="hidden" name="reason" value="Banned from Admin Panel">
                      <button class="btn btn-danger btn-sm">حظر</button>
                    </form>
                  </td>
                </tr>
              {% endfor %}
              </tbody>
            </table>
          </div>
        </div>

        <!-- Banned -->
        <div class="tab-pane fade" id="banned" role="tabpanel">
          <div class="table-responsive">
            <table class="table table-sm table-hover align-middle">
              <thead class="table-light">
                <tr>
                  <th>#</th>
                  <th>الاسم</th>
                  <th>Machine ID</th>
                  <th>السبب</th>
                  <th>آخر تحديث</th>
                  <th>إجراءات</th>
                </tr>
              </thead>
              <tbody>
              {% for c in banned %}
                <tr class="status-banned">
                  <td>{{ loop.index }}</td>
                  <td>{{ c.name }}</td>
                  <td>
                    <a href="{{ url_for('admin_device', mid=c.machine_id) }}">{{ c.machine_id_display }}</a>
                  </td>
                  <td>{{ c.banned_reason or "-" }}</td>
                  <td>{{ c.updated_at or c.created_at }}</td>
                  <td>
                    <form class="d-inline" method="post" action="{{ url_for('admin_action') }}">
                      <input type="hidden" name="machine_id" value="{{ c.machine_id }}">
                      <input type="hidden" name="action" value="unban">
                      <button class="btn btn-success btn-sm">إلغاء الحظر</button>
                    </form>
                    <form class="d-inline" method="post" action="{{ url_for('admin_action') }}"
                          onsubmit="return confirm('هل أنت متأكد من الحذف النهائي لهذا الجهاز من النظام؟');">
                      <input type="hidden" name="machine_id" value="{{ c.machine_id }}">
                      <input type="hidden" name="action" value="delete">
                      <button class="btn btn-outline-danger btn-sm">حذف نهائي</button>
                    </form>
                  </td>
                </tr>
              {% endfor %}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
  const statusData = {{ status_counts|tojson }};
  const ctx = document.getElementById('statusChart').getContext('2d');
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Pending', 'Active', 'Banned', 'Expired', 'Paused'],
      datasets: [{
        label: 'عدد الأجهزة',
        data: [
          statusData.pending,
          statusData.active,
          statusData.banned,
          statusData.expired,
          statusData.paused
        ]
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: { beginAtZero: true }
      }
    }
  });
</script>
</body>
</html>
"""

@app.route("/admin")
@login_required
def admin_dashboard():
    db = load_db()
    clients = db["clients"]

    pending = [c for c in clients if c.get("status") == "pending"]
    active  = [c for c in clients if c.get("status") == "active"]
    banned  = [c for c in clients if c.get("status") == "banned"]
    expired = [c for c in clients if c.get("status") == "expired"]
    paused  = [c for c in clients if c.get("status") == "paused"]

    status_counts = {
        "pending": len(pending),
        "active": len(active),
        "banned": len(banned),
        "expired": len(expired),
        "paused": len(paused),
        "total": len(clients)
    }

    return render_template_string(
        DASHBOARD_TEMPLATE,
        pending=pending,
        active=active,
        banned=banned,
        pending_count=len(pending),
        active_count=len(active),
        banned_count=len(banned),
        expired_count=len(expired),
        paused_count=len(paused),
        total_count=len(clients),
        status_counts=status_counts
    )


# ============================================================
#  5) صفحة تفاصيل جهاز
# ============================================================

DEVICE_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>تفاصيل الجهاز</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<nav class="navbar navbar-dark bg-dark">
  <div class="container-fluid">
    <span class="navbar-brand">تفاصيل الجهاز</span>
    <a href="{{ url_for('admin_dashboard') }}" class="btn btn-outline-light btn-sm">رجوع للوحة</a>
  </div>
</nav>
<div class="container my-3">
  {% if client %}
    <div class="card mb-3">
      <div class="card-header">
        {{ client.name or "عميل بدون اسم" }} — {{ client.machine_id_display }}
      </div>
      <div class="card-body">
        <p><strong>الحالة:</strong> {{ client.status }}</p>
        <p><strong>البريد:</strong> {{ client.email }}</p>
        <p><strong>الهاتف:</strong> {{ client.phone }}</p>
        <p><strong>الخطة:</strong> {{ client.plan }}</p>
        <p><strong>كود التفعيل:</strong> {{ client.license_code or "-" }}</p>
        <p><strong>ينتهي في:</strong> {{ client.expire_date or "-" }}</p>
        <p><strong>محاولات تلاعب:</strong> {{ client.suspicious_count or 0 }}</p>
        <p><strong>سبب الحظر:</strong> {{ client.banned_reason or "-" }}</p>
        <p><strong>آخر طلب:</strong> {{ client.last_request_at or "-" }}</p>
        <p><strong>تم الإنشاء:</strong> {{ client.created_at }}</p>
      </div>
    </div>
    <div class="card">
      <div class="card-header">
        معلومات النظام (System Info)
      </div>
      <div class="card-body">
        {% if client.system_info %}
          <pre style="white-space: pre-wrap; direction:ltr; text-align:left;">
{{ client.system_info | tojson(indent=2) }}
          </pre>
        {% else %}
          <p class="text-muted">لا توجد معلومات نظام محفوظة لهذا الجهاز.</p>
        {% endif %}
      </div>
    </div>
  {% else %}
    <div class="alert alert-danger mt-3">هذا الجهاز غير موجود.</div>
  {% endif %}
</div>
</body>
</html>
"""

@app.route("/admin/device/<mid>")
@login_required
def admin_device(mid):
    db = load_db()
    clients = db["clients"]
    mid_norm = normalize_machine_id(mid)
    client = find_client_by_mid(clients, mid_norm)
    return render_template_string(DEVICE_TEMPLATE, client=client)


# ============================================================
#  6) إعدادات اللوحة (Settings)
# ============================================================

SETTINGS_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>إعدادات السيرفر</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
</head>
<body class="bg-light">

<nav class="navbar navbar-dark bg-dark">
  <div class="container-fluid">
    <span class="navbar-brand">إعدادات السيرفر</span>
    <a href="{{ url_for('admin_dashboard') }}" class="btn btn-outline-light btn-sm">رجوع</a>
  </div>
</nav>

<div class="container my-4">

  {% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    {% for cat, msg in messages %}
      <div class="alert alert-{{cat}} py-1 my-1">{{ msg }}</div>
    {% endfor %}
  {% endif %}
  {% endwith %}

  <form method="post" class="card shadow p-3">

    <h5>بيانات الأدمن</h5>
    <div class="mb-3">
      <label class="form-label">اسم المستخدم</label>
      <input type="text" name="admin_user" class="form-control" value="{{ settings.admin_user }}">
    </div>

    <div class="mb-3">
      <label class="form-label">كلمة المرور</label>
      <input type="text" name="admin_pass" class="form-control" value="{{ settings.admin_pass }}">
    </div>

    <hr>
    <h5>إعدادات التفعيل (Secret Key)</h5>

    <div class="mb-3">
      <label class="form-label">SECRET_KEY</label>
      <input type="text" name="secret_key" class="form-control" value="{{ settings.secret_key }}">
    </div>

    <div class="mb-3">
      <label class="form-label">الخطة الافتراضية</label>
      <select name="default_plan" class="form-select">
        <option value="M" {% if settings.default_plan == 'M' %}selected{% endif %}>شهري</option>
        <option value="Y" {% if settings.default_plan == 'Y' %}selected{% endif %}>سنوي</option>
      </select>
    </div>

    <hr>
    <h5>إعدادات SMTP (إرسال الإيميل)</h5>

    <div class="form-check form-switch mb-3">
      <input class="form-check-input" type="checkbox" name="email_enabled" {% if settings.email_enabled %}checked{% endif %}>
      <label class="form-check-label">تفعيل إرسال الإيميل</label>
    </div>

    <div class="mb-3">
      <label class="form-label">SMTP Server</label>
      <input type="text" name="smtp_server" class="form-control" value="{{ settings.smtp_server }}">
    </div>

    <div class="mb-3">
      <label class="form-label">SMTP Port</label>
      <input type="number" name="smtp_port" class="form-control" value="{{ settings.smtp_port }}">
    </div>

    <div class="mb-3">
      <label class="form-label">SMTP User (البريد الذي يرسل منه)</label>
      <input type="text" name="smtp_user" class="form-control" value="{{ settings.smtp_user }}">
    </div>

    <div class="mb-3">
      <label class="form-label">SMTP Password</label>
      <input type="password" name="smtp_password" class="form-control" value="{{ settings.smtp_password }}">
    </div>

    <div class="mb-3">
      <label class="form-label">إرسال نسخة للمطور (اختياري)</label>
      <input type="text" name="admin_notify_email" class="form-control" value="{{ settings.admin_notify_email }}">
    </div>

    <div class="form-check form-switch mb-3">
      <input class="form-check-input" type="checkbox" name="smtp_ssl" {% if settings.smtp_ssl %}checked{% endif %}>
      <label class="form-check-label">استخدام SMTP_SSL (إن لم تفعّل سيتم استخدام STARTTLS)</label>
    </div>

    <button class="btn btn-primary mt-2">حفظ الإعدادات</button>

    <a href="{{ url_for('test_smtp') }}" class="btn btn-secondary mt-2">اختبار الإيميل</a>

  </form>

</div>
</body>
</html>
"""

@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
def admin_settings():
    db = load_db()
    settings = db["settings"]

    if request.method == "POST":
        settings["admin_user"] = request.form.get("admin_user", settings["admin_user"])
        settings["admin_pass"] = request.form.get("admin_pass", settings["admin_pass"])

        settings["secret_key"] = request.form.get("secret_key", settings["secret_key"])
        settings["default_plan"] = request.form.get("default_plan", settings["default_plan"])

        settings["email_enabled"] = True if request.form.get("email_enabled") == "on" else False
        settings["smtp_server"] = request.form.get("smtp_server", settings["smtp_server"])
        settings["smtp_port"] = int(request.form.get("smtp_port", settings["smtp_port"]))
        settings["smtp_user"] = request.form.get("smtp_user", settings["smtp_user"])
        settings["smtp_password"] = request.form.get("smtp_password", settings["smtp_password"])
        settings["smtp_ssl"] = True if request.form.get("smtp_ssl") == "on" else False
        settings["admin_notify_email"] = request.form.get("admin_notify_email", settings["admin_notify_email"])

        add_log(db, "admin_update_settings", None, note="تم تعديل إعدادات السيرفر", level="info")
        save_db(db)
        flash("تم حفظ الإعدادات بنجاح ✔", "success")
        return redirect(url_for("admin_settings"))

    return render_template_string(SETTINGS_TEMPLATE, settings=settings)


# ============================================================
#  7) إجراءات الأدمن (تفعيل، تجديد، حظر، إلخ)
# ============================================================

@app.route("/admin/action", methods=["POST"])
@login_required
def admin_action():
    db = load_db()
    settings = db["settings"]
    clients = db["clients"]

    raw_mid = request.form.get("machine_id", "")
    action = request.form.get("action", "")
    reason = request.form.get("reason", "").strip()
    days_custom = request.form.get("days", "").strip()

    mid_norm = normalize_machine_id(raw_mid)
    client = find_client_by_mid(clients, mid_norm)
    if not client:
        flash("الجهاز غير موجود", "danger")
        return redirect(url_for("admin_dashboard"))

    secret_key = settings.get("secret_key", DEFAULT_SECRET_KEY)
    today = date.today()
    now = now_iso()

    def calc_days(plan):
        if days_custom:
            try:
                return int(days_custom)
            except:
                return 30
        return 30 if plan == "M" else 365

    if action == "activate":
        plan = client.get("plan") or settings.get("default_plan", "M")
        days = calc_days(plan)
        exp = today + timedelta(days=days)
        code = generate_license_code(client["machine_id"], plan, secret_key)
        client["status"] = "active"
        client["plan"] = plan
        client["license_code"] = code
        client["expire_date"] = exp.isoformat()
        client["updated_at"] = now
        send_activation_email(client, settings, is_renew=False)
        add_log(db, "activate", client["machine_id"], note=f"تفعيل الجهاز حتى {exp.isoformat()}", level="success")
        flash("تم تفعيل الجهاز وتم إرسال إيميل للعميل (إن وُجد بريد).", "success")

    elif action == "renew":
        plan = client.get("plan") or settings.get("default_plan", "M")
        days = calc_days(plan)
        base_date = today
        if client.get("expire_date"):
            try:
                base_date = datetime.strptime(client["expire_date"], "%Y-%m-%d").date()
            except:
                base_date = today
        exp = base_date + timedelta(days=days)
        code = generate_license_code(client["machine_id"], plan, secret_key)
        client["status"] = "active"
        client["license_code"] = code
        client["plan"] = plan
        client["expire_date"] = exp.isoformat()
        client["updated_at"] = now
        send_activation_email(client, settings, is_renew=True)
        add_log(db, "renew", client["machine_id"], note=f"تجديد الاشتراك حتى {exp.isoformat()}", level="info")
        flash("تم تجديد الاشتراك وتم إرسال إيميل للعميل (إن وُجد بريد).", "success")

    elif action == "pause":
        client["status"] = "paused"
        client["updated_at"] = now
        add_log(db, "pause", client["machine_id"], note="إيقاف مؤقت للجهاز", level="warning")
        flash("تم إيقاف الجهاز مؤقتاً (Paused)", "warning")

    elif action == "unactivate":
        client["status"] = "expired"
        client["updated_at"] = now
        add_log(db, "unactivate", client["machine_id"], note="إلغاء التفعيل وتحويله إلى Expired", level="info")
        flash("تم إلغاء تفعيل الجهاز (تحويله إلى Expired)", "secondary")

    elif action == "reject":
        client["status"] = "rejected"
        client["updated_at"] = now
        add_log(db, "reject", client["machine_id"], note="رفض طلب التفعيل", level="info")
        flash("تم رفض طلب التفعيل", "secondary")

    elif action == "ban":
        client["status"] = "banned"
        client["banned_reason"] = reason or "Banned from Admin Panel"
        client["license_code"] = None
        client["expire_date"] = None
        client["updated_at"] = now
        add_log(db, "ban", client["machine_id"], note=f"حظر الجهاز. السبب: {client['banned_reason']}", level="danger")
        flash("تم حظر الجهاز", "danger")

    elif action == "unban":
        client["status"] = "pending"
        client["banned_reason"] = None
        client["updated_at"] = now
        add_log(db, "unban", client["machine_id"], note="إلغاء الحظر. حالة الجهاز الآن Pending", level="success")
        flash("تم إلغاء الحظر. حالة الجهاز الآن Pending", "success")

    elif action == "delete":
        try:
            clients.remove(client)
            add_log(db, "delete", mid_norm, note="حذف نهائي للجهاز من قاعدة البيانات", level="warning")
            flash("تم حذف الجهاز نهائيًا من قاعدة البيانات.", "warning")
        except ValueError:
            flash("تعذر حذف هذا الجهاز (غير موجود في القائمة).", "danger")

    else:
        flash("إجراء غير معروف", "danger")

    save_db(db)
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/test_smtp")
@login_required
def test_smtp():
    db = load_db()
    settings = db["settings"]

    test_email = settings.get("admin_notify_email") or settings.get("smtp_user")

    if not test_email:
        flash("لا يوجد بريد لإرسال الاختبار. ضع بريد مطوّر أو SMTP User.", "danger")
        return redirect(url_for("admin_settings"))

    ok = send_email_smtp(
        test_email,
        "اختبار SMTP - Ayman Activation Server",
        "هذه رسالة اختبار من سيرفر Ayman Auto Clicker.\nإذا وصلتك بنجاح فالإعدادات صحيحة.",
        settings
    )

    if ok:
        add_log(db, "test_smtp_ok", None, note=f"SMTP Test OK -> {test_email}", level="success")
        flash(f"✔ تم إرسال رسالة اختبار إلى {test_email}", "success")
    else:
        add_log(db, "test_smtp_fail", None, note="SMTP Test Failed", level="danger")
        flash("✖ فشل في الإرسال. تأكد من إعدادات SMTP.", "danger")

    save_db(db)
    return redirect(url_for("admin_settings"))


# ============================================================
#  8) صفحة السجلات (Logs)
# ============================================================

LOGS_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>سجلات السيرفر (Logs)</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<nav class="navbar navbar-dark bg-dark">
  <div class="container-fluid">
    <span class="navbar-brand">سجلات السيرفر (Logs)</span>
    <a href="{{ url_for('admin_dashboard') }}" class="btn btn-outline-light btn-sm">رجوع للوحة</a>
  </div>
</nav>

<div class="container my-3">
  <div class="card">
    <div class="card-header">
      آخر {{ logs|length }} عملية
    </div>
    <div class="card-body p-0">
      <div class="table-responsive">
        <table class="table table-sm table-striped mb-0">
          <thead class="table-light">
            <tr>
              <th>#</th>
              <th>الوقت (UTC)</th>
              <th>العملية</th>
              <th>Machine ID</th>
              <th>الوصف</th>
              <th>المستوى</th>
            </tr>
          </thead>
          <tbody>
          {% for log in logs %}
            <tr>
              <td>{{ loop.index }}</td>
              <td>{{ log.time }}</td>
              <td>{{ log.action }}</td>
              <td>{{ log.machine_id or "-" }}</td>
              <td>{{ log.note or "-" }}</td>
              <td>{{ log.level or "-" }}</td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>
</body>
</html>
"""

@app.route("/admin/logs")
@login_required
def admin_logs():
    db = load_db()
    logs = db.get("logs", [])
    # نعرض آخر 200 فقط
    logs = logs[-200:]
    return render_template_string(LOGS_TEMPLATE, logs=logs)


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
