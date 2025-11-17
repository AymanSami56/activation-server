# ===============================================================
#  Ayman Activation Server + Admin Panel (Bootstrap)
#  - REST API للبرنامج AutoClicker
#  - لوحة تحكم كاملة: Pending / Active / Banned / Settings / Details
#  - يدعم Ban / Unban / Renew / Pause / Unactivate
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


# ------------------ إعدادات عامة ------------------

DB_FILE = "clients_db.json"

# مفتاح التشفير المستخدم في توليد كود التفعيل
DEFAULT_SECRET_KEY = "AYMAN_SUPER_SECRET_2025"

# إعدادات الدخول للوحة الأدمن (يمكنك تغييرها من /admin/settings)
DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASS = "admin1234"   # أول مرة – غيّره من لوحة الإعدادات

# رقم الواتساب الافتراضي (يظهر للعميل في الردود)
DEFAULT_ADMIN_WHATSAPP = "07829004566"

# ------------------ إعدادات البريد (SMTP) ------------------
# ✉ عدّل هذه القيم لاحقًا كما تريد
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "aimen.same2000@gmail.com"  # حساب الإرسال
SMTP_PASS = "CHANGE_ME_APP_PASSWORD"    # ضع هنا App Password من جوجل
SMTP_USE_TLS = True

# رابط صفحة التحميل (GitHub أو غيره)
DOWNLOAD_URL = "https://github.com/your-account/ayman-autoclicker"  # عدّل الرابط حسب مشروعك

# Flask app
app = Flask(__name__)
app.secret_key = "CHANGE_ME_SESSION_SECRET_AYMAN"  # غيّره في السيرفر (Render) إلى قيمة سرية


# ============================================================
#  دوال مساعدة للـ DB
# ============================================================

def load_db():
    """
    بنية ملف JSON:
    {
      "settings": {...},
      "clients": [ {...}, {...} ]
    }
    لو كان ملف قديم (مجرد list) نحوله تلقائيًا.
    """

    # --- الإعدادات الافتراضية الجديدة (تشمل SMTP) ---
    default_settings = {
        "admin_user": DEFAULT_ADMIN_USER,
        "admin_pass": DEFAULT_ADMIN_PASS,
        "secret_key": DEFAULT_SECRET_KEY,
        "default_plan": "M",
        "max_devices": 1000,
        "admin_whatsapp": DEFAULT_ADMIN_WHATSAPP,

        # === إعدادات الإيميل الجديدة ===
        "email_enabled": False,       # تشغيل/إيقاف إرسال الإيميل
        "smtp_server": "",
        "smtp_port": 465,
        "smtp_ssl": True,            # True = SMTP_SSL / False = STARTTLS
        "smtp_user": "",
        "smtp_password": "",
        "admin_notify_email": ""      # اختياري – رسالة نسخة إلى المطوّر
    }

    # --- لو لا يوجد ملف DB ننشئ واحد جديد ---
    if not os.path.exists(DB_FILE):
        return {
            "settings": default_settings.copy(),
            "clients": []
        }

    # --- محاولة تحميل الملف ---
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {
            "settings": default_settings.copy(),
            "clients": []
        }

    # --- لو كان الملف القديم عبارة عن قائمة فقط ---
    if isinstance(data, list):
        return {
            "settings": default_settings.copy(),
            "clients": data
        }

    # --- تأكد من وجود settings ---
    if "settings" not in data or not isinstance(data["settings"], dict):
        data["settings"] = default_settings.copy()
    else:
        # أكمل المفاتيح الناقصة
        for key, value in default_settings.items():
            if key not in data["settings"]:
                data["settings"][key] = value

    # --- تأكد من وجود clients ---
    if "clients" not in data or not isinstance(data["clients"], list):
        data["clients"] = []

    return data


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)


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
    base = f"{machine_id}{plan}{secret_key}}"
    d = hashlib.sha256(base.encode("utf-8")).hexdigest()
    num = int(d, 16) % (10**16)
    return f"{num:016d}"


def now_iso():
    return datetime.utcnow().isoformat()



# ============================================================
#  إرسال الإيميل للعميل عند التفعيل / التجديد
# ============================================================

def send_activation_email(client: dict, settings: dict, is_renew: bool = False):
    """
    يرسل رسالة إيميل للعميل تحتوي:
    - اسم العميل
    - Machine ID
    - خطة الاشتراك
    - كود التفعيل
    - تاريخ انتهاء الاشتراك
    - رابط التحميل
    """
    to_email = (client.get("email") or "").strip()
    if not to_email:
        # لا يوجد إيميل → لا ترسل شيء
        return

    subject = "تفعيل اشتراك Ayman Auto Clicker" if not is_renew else "تجديد اشتراك Ayman Auto Clicker"

    name = client.get("name") or "عميلنا الكريم"
    machine_id_disp = client.get("machine_id_display") or format_machine_id(client.get("machine_id", ""))
    plan = client.get("plan", "M")
    plan_text = "شهري (30 يوم)" if plan == "M" else "سنوي (365 يوم)"
    expire_date = client.get("expire_date") or "-"
    license_code = client.get("license_code") or "-"

    whatsapp = settings.get("admin_whatsapp", DEFAULT_ADMIN_WHATSAPP)

    text_body = f"""
السلام عليكم {name}،

شكراً لاستخدامك برنامج Ayman Auto Clicker.

تم {'تفعيل' if not is_renew else 'تجديد'} اشتراكك بنجاح وفق البيانات التالية:

- Machine ID: {machine_id_disp}
- خطة الاشتراك: {plan_text}
- كود التفعيل: {license_code}
- تاريخ انتهاء الاشتراك: {expire_date}

يمكنك تحميل أو تحديث البرنامج من الرابط التالي:
{DOWNLOAD_URL}

لأي استفسار أو مشكلة تقنية يمكنك التواصل على الواتساب:
{whatsapp}

تحياتنا،
Ayman Software
"""

    msg = f"Subject: {subject}\r\n"
    msg += "From: Ayman Software <" + SMTP_USER + ">\r\n"
    msg += f"To: {to_email}\r\n"
    msg += "Content-Type: text/plain; charset=utf-8\r\n"
    msg += "\r\n"
    msg += text_body

    try:
        if SMTP_USE_TLS:
            context = ssl.create_default_context()
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls(context=context)
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_USER, [to_email], msg.encode("utf-8"))
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_USER, [to_email], msg.encode("utf-8"))
    except Exception as e:
        # لا نكسر اللوحة إذا فشل الإرسال – فقط نطبع في اللوج
        print("SMTP ERROR:", e)


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
def index():
    return "Ayman Activation Server ✔ Online"


# ============================================================
#  1) API: طلب تفعيل من داخل البرنامج
#      AutoClicker_final.py → POST /api/request_activation
# ============================================================

@app.route("/api/request_activation", methods=["POST"])
def api_request_activation():
    """
    JSON:
      {
        "name": "...",
        "email": "...",
        "phone": "...",
        "machine_id": "XXXX-XXXX-XXXX-XXXX",
        "plan": "M" or "Y",
        "version": "3.2.0",
        "system": {...}   # system info from client
      }
    """
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
        # لو محظور → لا نقبل طلبات جديدة
        if client.get("status") == "banned":
            return jsonify({
                "status": "banned",
                "message": "هذا الجهاز محظور من قبل النظام."
            }), 403

        current_status = client.get("status")

        # -----------------------------
        # تجميد بيانات العميل بعد التفعيل
        # -----------------------------
        if current_status == "active":
            # إذا حاول يغيّر الاسم/الإيميل/الهاتف → نعتبره تلاعب فقط
            changed = False
            if name and name != (client.get("name") or ""):
                changed = True
            if email and email != (client.get("email") or ""):
                changed = True
            if phone and phone != (client.get("phone") or ""):
                changed = True

            if changed:
                client["suspicious_count"] = client.get("suspicious_count", 0) + 1

            # لا نغيّر بيانات الهوية بعد التفعيل
            # فقط نحدّث معلومات النظام والإصدار وتاريخ الطلب
            client["version"] = version or client.get("version", "")
            client["system_info"] = system_info or client.get("system_info", {})
            client["last_request_at"] = now
            client["updated_at"] = now

        else:
            # الجهاز غير مفعّل بعد → مسموح تحديث البيانات
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
        # عميل جديد
        new_client = {
            "id": len(clients) + 1,
            "name": name,
            "email": email,
            "phone": phone,
            "machine_id": mid_norm,
            "machine_id_display": format_machine_id(mid_norm),
            "plan": plan,
            "license_code": None,
            "status": "pending",    # pending / active / expired / banned / paused / rejected
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

    save_db(db)

    return jsonify({
        "status": "pending",
        "message": "تم استلام طلب التفعيل. سيتم مراجعته من قِبل المطوّر.",
        "whatsapp": settings.get("admin_whatsapp", DEFAULT_ADMIN_WHATSAPP)
    })


# ============================================================
#  2) API: تحقق من حالة التفعيل
#      AutoClicker_final.py → GET /api/check_status
# ============================================================

@app.route("/api/check_status", methods=["GET"])
def api_check_status():
    """
    GET /api/check_status?machine_id=XXXX
    يرجع:
      {
        "status": "active|pending|expired|banned|not_found|paused|rejected",
        "plan": ...,
        "license_code": ...,
        "expire_date": "YYYY-MM-DD",
        "name": "...",
        "email": "...",
        "phone": "...",
        "suspicious_count": int
      }
    """
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

    # فحص انتهاء الاشتراك
    today = date.today()
    if status == "active" and expire_dt and today > expire_dt:
        status = "expired"
        client["status"] = "expired"
        client["updated_at"] = now_iso()
        save_db(db)

    # الحظر
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
            return redirect(url_for("admin_dashboard"))
        else:
            flash("بيانات الدخول غير صحيحة", "danger")

    return render_template_string(LOGIN_TEMPLATE)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# ============================================================
#  4) لوحة الأدمن – Dashboard
# ============================================================

DASHBOARD_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>لوحة التفعيل - Ayman</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
  <style>
    body { background:#f5f5f5; }
    .status-pending { background-color:#fff8e1; }
    .status-active  { background-color:#e8f5e9; }
    .status-banned  { background-color:#ffebee; }
    .status-expired { background-color:#fff3e0; }
    .status-paused  { background-color:#e3f2fd; }
  </style>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark">
  <div class="container-fluid">
    <span class="navbar-brand">لوحة تفعيل AutoClicker</span>
    <div class="d-flex">
      <a href="{{ url_for('admin_settings') }}" class="btn btn-outline-light btn-sm mx-1">الإعدادات</a>
      <a href="{{ url_for('admin_logout') }}" class="btn btn-outline-warning btn-sm mx-1">خروج</a>
    </div>
  </div>
</nav>

<div class="container-fluid mt-3">

  {% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    {% for cat, msg in messages %}
      <div class="alert alert-{{cat}} py-1 my-1">{{ msg }}</div>
    {% endfor %}
  {% endif %}
  {% endwith %}

  <div class="row mb-3">
    <div class="col-md-3">
      <div class="card text-bg-warning mb-2">
        <div class="card-body py-2">
          <div class="d-flex justify-content-between">
            <span>Pending</span>
            <strong>{{ pending_count }}</strong>
          </div>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card text-bg-success mb-2">
        <div class="card-body py-2">
          <div class="d-flex justify-content-between">
            <span>Active</span>
            <strong>{{ active_count }}</strong>
          </div>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card text-bg-danger mb-2">
        <div class="card-body py-2">
          <div class="d-flex justify
          <div class="d-flex justify-content-between">
            <span>Banned</span>
            <strong>{{ banned_count }}</strong>
          </div>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card text-bg-secondary mb-2">
        <div class="card-body py-2">
          <div class="d-flex justify-content-between">
            <span>All Devices</span>
            <strong>{{ total_count }}</strong>
          </div>
        </div>
      </div>
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
              <td>{{ c.banned_reason }}</td>
              <td>
                <form class="d-inline" method="post" action="{{ url_for('admin_action') }}">
                  <input type="hidden" name="machine_id" value="{{ c.machine_id }}">
                  <input type="hidden" name="action" value="unban">
                  <button class="btn btn-success btn-sm">إلغاء الحظر</button>
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

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
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

    return render_template_string(
        DASHBOARD_TEMPLATE,
        pending=pending,
        active=active,
        banned=banned,
        pending_count=len(pending),
        active_count=len(active),
        banned_count=len(banned),
        total_count=len(clients)
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
#  6) إعدادات اللوحة
# ============================================================

SETTINGS_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>إعدادات اللوحة</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<nav class="navbar navbar-dark bg-dark">
  <div class="container-fluid">
    <span class="navbar-brand">إعدادات لوحة التفعيل</span>
    <a href="{{ url_for('admin_dashboard') }}" class="btn btn-outline-light btn-sm">رجوع للوحة</a>
  </div>
</nav>
<div class="container my-3">
  {% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    {% for cat, msg in messages %}
      <div class="alert alert-{{cat}} py-1 my-1">{{ msg }}</div>
    {% endfor %}
  {% endif %}
  {% endwith %}

  <form method="post" class="card p-3 shadow-sm">
    <div class="mb-3">
      <label class="form-label">اسم المستخدم للأدمن</label>
      <input type="text" name="admin_user" class="form-control" value="{{ settings.admin_user }}">
    </div>
    <div class="mb-3">
      <label class="form-label">كلمة المرور للأدمن</label>
      <input type="text" name="admin_pass" class="form-control" value="{{ settings.admin_pass }}">
      <div class="form-text text-danger">⚠ احفظ هذه القيم في مكان آمن، أي شخص يعرفها يستطيع الدخول للوحة.</div>
    </div>
    <div class="mb-3">
      <label class="form-label">SECRET_KEY المستخدم في التفعيل</label>
      <input type="text" name="secret_key" class="form-control" value="{{ settings.secret_key }}">
      <div class="form-text text-danger">
        ⚠ تغيير هذا المفتاح يعني أن الأكواد القديمة لن تعمل،
        ويجب تحديث البرنامج والكيجن على نفس المفتاح الجديد.
      </div>
    </div>
    <div class="mb-3">
      <label class="form-label">الخطة الافتراضية</label>
      <select name="default_plan" class="form-select">
        <option value="M" {% if settings.default_plan == 'M' %}selected{% endif %}>شهري (30 يوم)</option>
        <option value="Y" {% if settings.default_plan == 'Y' %}selected{% endif %}>سنوي (365 يوم)</option>
      </select>
    </div>
    <div class="mb-3">
      <label class="form-label">الحد الأقصى للأجهزة المسجلة (إحصائي فقط)</label>
      <input type="number" name="max_devices" class="form-control" value="{{ settings.max_devices }}">
    </div>
    <div class="mb-3">
      <label class="form-label">رقم الواتساب الافتراضي</label>
      <input type="text" name="admin_whatsapp" class="form-control" value="{{ settings.admin_whatsapp }}">
    </div>
    <button class="btn btn-primary">حفظ الإعدادات</button>
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
        try:
            settings["max_devices"] = int(request.form.get("max_devices", settings["max_devices"]))
        except:
            pass
        settings["admin_whatsapp"] = request.form.get("admin_whatsapp", settings["admin_whatsapp"])
        db["settings"] = settings
        save_db(db)
        flash("تم حفظ الإعدادات بنجاح", "success")
        return redirect(url_for("admin_settings"))

    return render_template_string(SETTINGS_TEMPLATE, settings=settings)


# ============================================================
#  7) إجراءات الأدمن (تفعيل، تجديد، حظر، إلغاء حظر، إلخ)
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

    # عدد الأيام حسب الخطة أو مخصص
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
        save_db(db)
        # إرسال إيميل تفعيل
        send_activation_email(client, settings, is_renew=False)
        flash("تم تفعيل الجهاز وتم إرسال إيميل للعميل (إن وُجد بريد).", "success")

    elif action == "renew":
        plan = client.get("plan") or settings.get("default_plan", "M")
        days = calc_days(plan)
        # التجديد من تاريخ الانتهاء الحالي إن وجد وإلا من اليوم
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
        save_db(db)
        # إرسال إيميل تجديد
        send_activation_email(client, settings, is_renew=True)
        flash("تم تجديد الاشتراك وتم إرسال إيميل للعميل (إن وُجد بريد).", "success")

    elif action == "pause":
        client["status"] = "paused"
        client["updated_at"] = now
        save_db(db)
        flash("تم إيقاف الجهاز مؤقتاً (Paused)", "warning")

    elif action == "unactivate":
        client["status"] = "expired"
        client["updated_at"] = now
        save_db(db)
        flash("تم إلغاء تفعيل الجهاز (تحويله إلى Expired)", "secondary")

    elif action == "reject":
        client["status"] = "rejected"
        client["updated_at"] = now
        save_db(db)
        flash("تم رفض طلب التفعيل", "secondary")

    elif action == "ban":
        client["status"] = "banned"
        client["banned_reason"] = reason or "Banned from Admin Panel"
        client["license_code"] = None
        client["expire_date"] = None
        client["updated_at"] = now
        save_db(db)
        flash("تم حظر الجهاز", "danger")

    elif action == "unban":
        client["status"] = "pending"
        client["banned_reason"] = None
        client["updated_at"] = now
        save_db(db)
        flash("تم إلغاء الحظر. حالة الجهاز الآن Pending", "success")

    else:
        flash("إجراء غير معروف", "danger")

    return redirect(url_for("admin_dashboard"))


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    # للتجربة محلياً:
    app.run(host="0.0.0.0", port=5050, debug=True)

