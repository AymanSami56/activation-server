# ===============================================================
#  Ayman Activation Server + Admin Panel
#  - يستقبل طلبات التفعيل من البرنامج
#  - يعرضها في لوحة Admin
#  - يولّد كود تفعيل ويخزّنه
#  - يسمح للبرنامج أن يتحقق من حالة التفعيل أونلاين
# ===============================================================

from flask import Flask, request, jsonify, Response
import hashlib
import json
import os
from datetime import datetime, date, timedelta
import re

# ------------------ إعدادات عامة ------------------

SECRET_KEY = "AYMAN_SUPER_SECRET_2025"   # نفس المفتاح في البرنامج و KeyGen
ADMIN_TOKEN = "AYMAN_ADMIN_123"         # توكن بسيط للحماية (غيره لشيء سري)
DB_FILE = "clients_db.json"

app = Flask(__name__)

# ------------------ دوال مساعدة للـ DB ------------------

def load_db():
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_db(clients):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(clients, f, indent=4, ensure_ascii=False)

def normalize_machine_id(mid: str) -> str:
    mid = mid.strip().upper()
    mid = re.sub(r"[^0-9A-F]", "", mid)
    return mid[:16]

def generate_license_code(machine_id: str, plan: str) -> str:
    base = f"{machine_id}{plan}{SECRET_KEY}"
    d = hashlib.sha256(base.encode("utf-8")).hexdigest()
    num = int(d, 16) % (10**16)
    return f"{num:016d}"

def find_client_by_mid(clients, machine_id_norm):
    for c in clients:
        if c.get("machine_id") == machine_id_norm:
            return c
    return None

# ------------------ صفحة بسيطة في الجذر ------------------

@app.route("/")
def index():
    return "Ayman Activation Server ✔ Online"

# ==========================================================
# 1) API: طلب تفعيل من داخل البرنامج
# ==========================================================

@app.route("/api/request_activation", methods=["POST"])
def api_request_activation():
    """
    يستقبل طلب جديد من برنامج AutoClicker:
    JSON:
      {
        "name": "...",
        "email": "...",
        "phone": "...",
        "machine_id": "XXXX-XXXX-XXXX-XXXX",
        "plan": "M" or "Y",
        "version": "3.1.0"  (اختياري)
      }
    """
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    raw_mid = (data.get("machine_id") or "").strip()
    plan = (data.get("plan") or "M").strip().upper()
    version = (data.get("version") or "").strip()

    if not raw_mid:
        return jsonify({"status": "error", "message": "machine_id مفقود"}), 400

    if plan not in ("M", "Y"):
        plan = "M"

    mid_norm = normalize_machine_id(raw_mid)

    clients = load_db()
    client = find_client_by_mid(clients, mid_norm)

    now = datetime.utcnow().isoformat()

    if client is None:
        # عميل جديد
        client = {
            "id": len(clients) + 1,
            "name": name,
            "email": email,
            "phone": phone,
            "machine_id": mid_norm,
            "plan": plan,
            "license_code": None,
            "status": "pending",  # pending / active / expired
            "created_at": now,
            "updated_at": now,
            "expire_date": None,
            "notes": "",
            "version": version
        }
        clients.append(client)
    else:
        # تحديث بيانات عميل قديم (مثلاً أعاد تثبيت البرنامج)
        client["name"] = name or client["name"]
        client["email"] = email or client["email"]
        client["phone"] = phone or client["phone"]
        client["plan"] = plan
        client["updated_at"] = now
        # لا نغير status هنا

    save_db(clients)

    return jsonify({
        "status": "pending",
        "message": "تم استلام طلب التفعيل، تواصل مع المطوّر عبر الواتساب لإكمال الدفع.",
        "whatsapp": "07829004566"
    })


# ==========================================================
# 2) API: تحقق من حالة التفعيل (يستخدمه البرنامج)
# ==========================================================

@app.route("/api/check_status", methods=["GET"])
def api_check_status():
    """
    GET /api/check_status?machine_id=XXXX-XXXX-XXXX-XXXX
    يرجع حالة الجهاز:
    - pending
    - active
    - expired
    """
    raw_mid = request.args.get("machine_id", "").strip()
    if not raw_mid:
        return jsonify({"status": "error", "message": "machine_id مفقود"}), 400

    mid_norm = normalize_machine_id(raw_mid)
    clients = load_db()
    client = find_client_by_mid(clients, mid_norm)

    if client is None:
        return jsonify({
            "status": "not_found",
            "message": "لا يوجد طلب تفعيل لهذا الجهاز."
        })

    status = client.get("status", "pending")
    expire_str = client.get("expire_date")
    expire_date = None
    if expire_str:
        try:
            expire_date = datetime.strptime(expire_str, "%Y-%m-%d").date()
        except:
            pass

    # تحقق من انتهاء الاشتراك
    if status == "active" and expire_date and date.today() > expire_date:
        status = "expired"
        client["status"] = "expired"
        save_db(clients)

    return jsonify({
        "status": status,
        "plan": client.get("plan"),
        "license_code": client.get("license_code"),
        "expire_date": client.get("expire_date"),
        "name": client.get("name"),
        "email": client.get("email"),
        "phone": client.get("phone")
    })


# ==========================================================
# 3) API Admin: عرض العملاء في لوحة التحكم
# ==========================================================

@app.route("/api/admin/clients", methods=["GET"])
def api_admin_clients():
    """
    GET /api/admin/clients?token=ADMIN_TOKEN
    يرجّع كل العملاء كـ JSON لاستخدامها في لوحة الإدارة
    """
    token = request.args.get("token", "")
    if token != ADMIN_TOKEN:
        return jsonify({"status": "error", "message": "توكن غير صالح"}), 403

    clients = load_db()
    return jsonify(clients)


# ==========================================================
# 4) API Admin: تفعيل عميل معيّن
# ==========================================================

@app.route("/api/admin/activate", methods=["POST"])
def api_admin_activate():
    """
    POST /api/admin/activate?token=ADMIN_TOKEN
    JSON:
      {
        "machine_id": "XXXX-XXXX-XXXX-XXXX",
        "plan": "M" or "Y",
        "days": 30 (اختياري، لو حاب تمدد شيء مخصص)
      }
    """
    token = request.args.get("token", "")
    if token != ADMIN_TOKEN:
        return jsonify({"status": "error", "message": "توكن غير صالح"}), 403

    data = request.get_json(silent=True) or {}
    raw_mid = (data.get("machine_id") or "").strip()
    plan = (data.get("plan") or "M").strip().upper()
    custom_days = data.get("days")

    if not raw_mid:
        return jsonify({"status": "error", "message": "machine_id مفقود"}), 400

    if plan not in ("M", "Y"):
        return jsonify({"status": "error", "message": "الخطة يجب أن تكون M أو Y"}), 400

    mid_norm = normalize_machine_id(raw_mid)
    clients = load_db()
    client = find_client_by_mid(clients, mid_norm)

    if client is None:
        return jsonify({"status": "error", "message": "عميل غير موجود"}), 404

    # عدد الأيام حسب الخطة أو مخصص
    if custom_days:
        try:
            days = int(custom_days)
        except:
            days = 30
    else:
        days = 30 if plan == "M" else 365

    today = date.today()
    expire_date = today + timedelta(days=days)

    # توليد كود التفعيل
    license_code = generate_license_code(mid_norm, plan)

    client["plan"] = plan
    client["license_code"] = license_code
    client["status"] = "active"
    client["expire_date"] = expire_date.isoformat()
    client["updated_at"] = datetime.utcnow().isoformat()

    save_db(clients)

    return jsonify({
        "status": "ok",
        "message": "تم تفعيل العميل بنجاح.",
        "license_code": license_code,
        "expire_date": expire_date.isoformat()
    })


# ==========================================================
# 5) لوحة Admin (صفحة ويب)
# ==========================================================

ADMIN_HTML = r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <title>Ayman Activation Admin</title>
  <style>
    body {
      font-family: Tahoma, Arial, sans-serif;
      background: #f4f4f4;
      margin: 0;
      padding: 0;
    }
    header {
      background: #2196F3;
      color: white;
      padding: 10px 15px;
    }
    header h1 {
      margin: 0;
      font-size: 20px;
    }
    .container {
      padding: 15px;
    }
    .token-box {
      margin-bottom: 10px;
    }
    .token-box input {
      width: 220px;
      padding: 5px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: white;
    }
    th, td {
      border: 1px solid #ddd;
      padding: 6px;
      font-size: 13px;
      text-align: center;
    }
    th {
      background: #eee;
    }
    tr.pending {
      background: #fffde7;
    }
    tr.active {
      background: #e8f5e9;
    }
    tr.expired {
      background: #ffebee;
    }
    button {
      padding: 4px 8px;
      font-size: 12px;
      cursor: pointer;
    }
    .small-input {
      width: 60px;
    }
  </style>
</head>
<body>
  <header>
    <h1>لوحة تفعيل برنامج Auto Clicker Ayman</h1>
  </header>
  <div class="container">
    <div class="token-box">
      <label>Admin Token: </label>
      <input type="password" id="tokenInput" placeholder="أدخل التوكن ثم اضغط تحميل" />
      <button onclick="loadClients()">📥 تحميل العملاء</button>
      <span id="statusText"></span>
    </div>

    <table id="clientsTable">
      <thead>
        <tr>
          <th>#</th>
          <th>الاسم</th>
          <th>البريد</th>
          <th>الهاتف</th>
          <th>Machine ID</th>
          <th>الحالة</th>
          <th>الخطة</th>
          <th>الكود</th>
          <th>تاريخ الانتهاء</th>
          <th>أيام</th>
          <th>تفعيل</th>
        </tr>
      </thead>
      <tbody>
      </tbody>
    </table>
  </div>

  <script>
    let clientsCache = [];

    async function loadClients() {
      const token = document.getElementById('tokenInput').value.trim();
      if (!token) {
        alert('أدخل التوكن أولاً');
        return;
      }
      document.getElementById('statusText').innerText = '...جاري التحميل';
      try {
        const res = await fetch('/api/admin/clients?token=' + encodeURIComponent(token));
        if (!res.ok) {
          const txt = await res.text();
          document.getElementById('statusText').innerText = 'خطأ: ' + txt;
          return;
        }
        const data = await res.json();
        clientsCache = data;
        renderTable(data);
        document.getElementById('statusText').innerText = 'تم التحديث';
      } catch (e) {
        document.getElementById('statusText').innerText = 'مشكلة في الاتصال';
        console.error(e);
      }
    }

    function renderTable(clients) {
      const tbody = document.querySelector('#clientsTable tbody');
      tbody.innerHTML = '';
      clients.forEach((c, idx) => {
        const tr = document.createElement('tr');
        tr.className = c.status || '';
        tr.innerHTML = `
          <td>${idx + 1}</td>
          <td>${c.name || ''}</td>
          <td>${c.email || ''}</td>
          <td>${c.phone || ''}</td>
          <td>${c.machine_id || ''}</td>
          <td>${c.status || ''}</td>
          <td>${c.plan || ''}</td>
          <td>${c.license_code || ''}</td>
          <td>${c.expire_date || ''}</td>
          <td><input class="small-input" type="number" id="days_${idx}" placeholder="30/365" /></td>
          <td><button onclick="activateClient(${idx})">تفعيل</button></td>
        `;
        tbody.appendChild(tr);
      });
    }

    async function activateClient(index) {
      const token = document.getElementById('tokenInput').value.trim();
      if (!token) {
        alert('أدخل التوكن أولاً');
        return;
      }
      const c = clientsCache[index];
      if (!c) return;
      const daysInput = document.getElementById('days_' + index).value.trim();
      let body = {
        machine_id: c.machine_id,
        plan: c.plan || 'M'
      };
      if (daysInput) {
        body.days = parseInt(daysInput);
      }
      try {
        const res = await fetch('/api/admin/activate?token=' + encodeURIComponent(token), {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(body)
        });
        const data = await res.json();
        if (res.ok && data.status === 'ok') {
          alert('تم التفعيل.\nالكود: ' + data.license_code + '\nينتهي في: ' + data.expire_date);
          // إعادة التحميل بعد التفعيل
          loadClients();
        } else {
          alert('خطأ في التفعيل: ' + JSON.stringify(data));
        }
      } catch (e) {
        alert('مشكلة في الاتصال بالسيرفر');
        console.error(e);
      }
    }

    // تحديث تلقائي كل 10 ثواني بعد إدخال التوكن مرة واحدة
    setInterval(() => {
      const token = document.getElementById('tokenInput').value.trim();
      if (token) {
        loadClients();
      }
    }, 10000);
  </script>
</body>
</html>
"""

@app.route("/admin")
def admin_page():
    return Response(ADMIN_HTML, mimetype="text/html")

# ==========================================================
# 6) تشغيل السيرفر (للتشغيل المحلي أو عبر waitress على Render)
# ==========================================================

if __name__ == "__main__":
    # تشغيل مباشر (للتجربة على localhost)
    app.run(host="0.0.0.0", port=5050)

