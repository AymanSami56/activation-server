from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session
from datetime import datetime, timedelta
import hashlib
import json
import os

# ============================================
#  إعدادات أساسية
# ============================================

app = Flask(__name__)

# مفتاح جلسات Flask (لـ login admin) - غيّره لقيمة قوية
app.config["SECRET_KEY"] = "FLASK_SESSION_KEY_AYMAN_2025"

# مفتاح توليد الأكواد (نفسه في البرنامج و KeyGen)
SECRET_KEY = "AYMAN_SUPER_SECRET_2025"

# كلمة مرور لوحة التحكم
ADMIN_PASSWORD = "ayman_admin_2025"  # غيّرها بنفسك

DB_FILE = "clients.json"


# ============================================
#  دوال مساعدة لقراءة/حفظ قاعدة البيانات
# ============================================

def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_db(data: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def generate_expected_code(machine_id: str, plan: str) -> str:
    """
    نفس الدالة المستخدمة في البرنامج / KeyGen:
    machine_id (بدون -) + الخطة + SECRET_KEY → 16 رقم
    """
    mid = machine_id.replace("-", "").upper()
    base = f"{mid}{plan}{SECRET_KEY}"
    d = hashlib.sha256(base.encode("utf-8")).hexdigest()
    num = int(d, 16) % (10**16)
    return f"{num:016d}"


# ============================================
#  مسارات الـ API (Online Activation)
# ============================================

@app.route("/", methods=["GET"])
def home():
    return "Ayman Activation Server ✔ Online"


@app.route("/verify", methods=["POST"])
def verify():
    """
    يستقبل من البرنامج:
    {
      "machine_id": "...",
      "plan": "M" أو "Y",
      "code": "XXXX-XXXX-XXXX-XXXX"
    }

    ويرجع JSON فيه حالة الاشتراك:
      - status: ok / invalid / expired / error
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "msg": "no_json"}), 400

    machine_id = data.get("machine_id")
    plan = data.get("plan")
    code_input = data.get("code")

    if not machine_id or not plan or not code_input:
        return jsonify({"status": "error", "msg": "missing_fields"}), 400

    # تنظيف الكود من الشرطات وخلافه
    code_clean = "".join(ch for ch in code_input if ch.isdigit())
    expected = generate_expected_code(machine_id, plan)

    if code_clean != expected:
        return jsonify({"status": "invalid", "msg": "activation_code_incorrect"})

    # الكود صحيح → نتحقق/ننشيء اشتراك في DB
    db = load_db()
    mid_key = machine_id.replace("-", "").upper()

    today = datetime.utcnow().date()

    if mid_key not in db:
        # أوّل مرة هذا الجهاز يفعّل
        days = 30 if plan == "M" else 365
        expire = today + timedelta(days=days)
        db[mid_key] = {
            "plan": plan,
            "expire": expire.strftime("%Y-%m-%d")
        }
        save_db(db)
        return jsonify({
            "status": "ok",
            "msg": "activated_new",
            "plan": plan,
            "expire": expire.strftime("%Y-%m-%d")
        })

    # جهاز موجود من قبل → نتحقق من انتهاء الاشتراك
    entry = db[mid_key]
    expire_str = entry.get("expire")
    try:
        expire_date = datetime.strptime(expire_str, "%Y-%m-%d").date()
    except:
        return jsonify({"status": "error", "msg": "invalid_expire_in_db"})

    if today > expire_date:
        return jsonify({
            "status": "expired",
            "msg": "subscription_expired",
            "plan": entry.get("plan"),
            "expire": expire_str
        })

    return jsonify({
        "status": "ok",
        "msg": "subscription_valid",
        "plan": entry.get("plan"),
        "expire": expire_str
    })


# ============================================
#  نظام لوحة التحكم Admin (Bootstrap UI)
# ============================================

ADMIN_TEMPLATE = r"""
<!doctype html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="utf-8">
    <title>Ayman Activation Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
  <div class="container-fluid">
    <span class="navbar-brand">لوحة تفعيل Ayman</span>
    <div class="d-flex">
      <a href="{{ url_for('admin_logout') }}" class="btn btn-outline-light btn-sm">تسجيل خروج</a>
    </div>
  </div>
</nav>

<div class="container mb-5">

  <div class="row mb-4">
    <div class="col-md-4">
      <div class="card border-success">
        <div class="card-body">
          <h5 class="card-title">إجمالي الأجهزة</h5>
          <p class="display-6">{{ total }}</p>
        </div>
      </div>
    </div>
    <div class="col-md-4 mt-3 mt-md-0">
      <div class="card border-primary">
        <div class="card-body">
          <h5 class="card-title">فعّالة</h5>
          <p class="display-6 text-primary">{{ active }}</p>
        </div>
      </div>
    </div>
    <div class="col-md-4 mt-3 mt-md-0">
      <div class="card border-danger">
        <div class="card-body">
          <h5 class="card-title">منتهية</h5>
          <p class="display-6 text-danger">{{ expired }}</p>
        </div>
      </div>
    </div>
  </div>

  <div class="d-flex justify-content-between align-items-center mb-3">
    <h4>قائمة الأجهزة</h4>
    <a href="{{ url_for('admin_add') }}" class="btn btn-success">➕ إضافة / تعديل جهاز</a>
  </div>

  <div class="table-responsive">
    <table class="table table-striped table-hover align-middle">
      <thead class="table-light">
        <tr>
          <th>Machine ID</th>
          <th>الخطة</th>
          <th>تاريخ الانتهاء</th>
          <th>الحالة</th>
        </tr>
      </thead>
      <tbody>
        {% for mid, info in items %}
        <tr>
          <td><code>{{ mid }}</code></td>
          <td>{{ "شهري" if info.plan == "M" else "سنوي" }}</td>
          <td>{{ info.expire }}</td>
          <td>
            {% if info.is_expired %}
              <span class="badge bg-danger">منتهي</span>
            {% else %}
              <span class="badge bg-success">ساري</span>
            {% endif %}
          </td>
        </tr>
        {% else %}
        <tr>
          <td colspan="4" class="text-center text-muted">لا يوجد أجهزة بعد.</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

</div>
</body>
</html>
"""

LOGIN_TEMPLATE = r"""
<!doctype html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="utf-8">
    <title>تسجيل دخول - Ayman Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
</head>
<body class="bg-light d-flex align-items-center" style="min-height:100vh;">
  <div class="container">
    <div class="row justify-content-center">
      <div class="col-md-4">
        <div class="card shadow-sm">
          <div class="card-body">
            <h4 class="card-title mb-3 text-center">لوحة تفعيل Ayman</h4>
            {% if error %}
              <div class="alert alert-danger py-2">{{ error }}</div>
            {% endif %}
            <form method="post">
              <div class="mb-3">
                <label class="form-label">كلمة المرور</label>
                <input type="password" name="password" class="form-control" required>
              </div>
              <button class="btn btn-primary w-100">دخول</button>
            </form>
          </div>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""

ADD_TEMPLATE = r"""
<!doctype html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="utf-8">
    <title>إضافة / تعديل جهاز - Ayman Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
  <div class="container-fluid">
    <span class="navbar-brand">لوحة تفعيل Ayman</span>
    <div class="d-flex">
      <a href="{{ url_for('admin_dashboard') }}" class="btn btn-outline-light btn-sm">⬅ رجوع</a>
    </div>
  </div>
</nav>

<div class="container">
  <div class="row justify-content-center">
    <div class="col-md-6">
      <div class="card shadow-sm">
        <div class="card-body">
          <h4 class="card-title mb-3 text-center">إضافة / تعديل جهاز</h4>
          <form method="post">
            <div class="mb-3">
              <label class="form-label">Machine ID (بدون أو مع شرطات)</label>
              <input type="text" name="machine_id" class="form-control" required value="{{ machine_id or '' }}">
            </div>
            <div class="mb-3">
              <label class="form-label">الخطة</label>
              <select name="plan" class="form-select">
                <option value="M" {% if plan == 'M' %}selected{% endif %}>شهري (30 يوم)</option>
                <option value="Y" {% if plan == 'Y' %}selected{% endif %}>سنوي (365 يوم)</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">عدد الأيام (اختياري، يكتب بدل الخطة)</label>
              <input type="number" name="days" class="form-control" min="1" placeholder="مثال: 60">
            </div>
            <button class="btn btn-success w-100">حفظ</button>
          </form>
        </div>
      </div>
    </div>
  </div>
</div>
</body>
</html>
"""


def admin_login_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged"):
            return redirect(url_for("admin_login"))
        return func(*args, **kwargs)
    return wrapper


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        pwd = request.form.get("password")
        if pwd == ADMIN_PASSWORD:
            session["admin_logged"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            error = "كلمة المرور غير صحيحة."
    return render_template_string(LOGIN_TEMPLATE, error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged", None)
    return redirect(url_for("admin_login"))


@app.route("/admin", methods=["GET"])
@admin_login_required
def admin_dashboard():
    db = load_db()
    today = datetime.utcnow().date()
    total = len(db)
    active = 0
    expired = 0

    items = []
    for mid, info in db.items():
        exp_str = info.get("expire", "0000-00-00")
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
        except:
            exp_date = today
        is_expired = today > exp_date
        if is_expired:
            expired += 1
        else:
            active += 1
        items.append(type("Obj", (), {
            "mid": mid,
            "plan": info.get("plan", "?"),
            "expire": exp_str,
            "is_expired": is_expired
        }))

    return render_template_string(
        ADMIN_TEMPLATE,
        total=total,
        active=active,
        expired=expired,
        items=[(o.mid, o) for o in items]
    )


@app.route("/admin/add", methods=["GET", "POST"])
@admin_login_required
def admin_add():
    if request.method == "POST":
        machine_id = request.form.get("machine_id", "").strip()
        plan = request.form.get("plan", "M")
        days_str = request.form.get("days", "").strip()

        if not machine_id:
            return "Machine ID مطلوب", 400

        mid_key = machine_id.replace("-", "").upper()
        today = datetime.utcnow().date()

        if days_str:
            try:
                days = int(days_str)
            except:
                days = 30
        else:
            days = 30 if plan == "M" else 365

        expire = today + timedelta(days=days)

        db = load_db()
        db[mid_key] = {
            "plan": plan,
            "expire": expire.strftime("%Y-%m-%d")
        }
        save_db(db)

        return redirect(url_for("admin_dashboard"))

    # GET
    return render_template_string(ADD_TEMPLATE, machine_id="", plan="M")


# ============================================
#  تشغيل محلي (Render سيهمل هذا الـ block)
# ============================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
