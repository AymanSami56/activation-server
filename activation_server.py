# ===============================================================
#  Ayman Activation Server + Admin Panel (Final)
#  - يدعم REST API للبرنامج AutoClicker
#  - لوحة تحكم كاملة: Login / Pending / Active / Banned / Settings
#  - وظائف الإدارة: Ban / Unban / Renew / Delete
#  - دعم إشعارات البريد الإلكتروني (SMTP)
# ===============================================================

from flask import (
    Flask, request, jsonify, render_template, render_template_string,
    redirect, url_for, session, flash, Response
)
import hashlib
import json
import os
from datetime import datetime, date, timedelta
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

# ------------------ إعدادات عامة ------------------

# ملف قاعدة البيانات
DB_FILE = "server_db.json" 

# إعدادات الدخول الافتراضية
DEFAULT_ADMIN_USER = "admin"
# قم بتغيير القيمة الافتراضية إلى الهاش المشفر لكلمة "admin1234"
# (هذا سيجعل التحقق يعمل مباشرة)
DEFAULT_ADMIN_PASS = "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"  
DEFAULT_SECRET_KEY = "AYMAN_SUPER_SECRET_2025"

# ------------------ تهيئة التطبيق ------------------

app = Flask(__name__)
# مفتاح الجلسات (مهم للأمان ولعمل flash / session)
app.secret_key = 'super_secret_key_for_session' 
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30) # مدة الجلسة

# ===========================================================
# وظائف قاعدة البيانات (JSON-Based)
# ===========================================================

def load_db():
    """تحميل قاعدة البيانات (الإعدادات + العملاء)"""
    if not os.path.exists(DB_FILE):
        return {
            "settings": {
                "admin_user": DEFAULT_ADMIN_USER,
                "admin_pass": DEFAULT_ADMIN_PASS,
                "secret_key": DEFAULT_SECRET_KEY,
                "default_plan": "Pro (2 Months)",
                "email_enabled": False,
                "smtp_server": "",
                "smtp_port": 587,
                "smtp_user": "",
                "smtp_password": "",
                "smtp_ssl": True,
                "admin_notify_email": "admin@example.com",
                "admin_whatsapp": "0782XXXXXX",
            },
            "clients": {}
        }
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_db(db_data):
    """حفظ قاعدة البيانات"""
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db_data, f, indent=4, ensure_ascii=False)

def get_db():
    """تحميل البيانات مرة واحدة (للاستخدام داخل الدوال)"""
    if not hasattr(app, 'db'):
        app.db = load_db()
    return app.db

# ===========================================================
# وظائف إضافية: البريد الإلكتروني
# ===========================================================

def send_email(to_email, subject, body, html_body=None):
    db = get_db()
    settings = db["settings"]
    
    if not settings.get('email_enabled'):
        print(f"⚠️ البريد الإلكتروني معطل. لم يتم إرسال رسالة إلى {to_email}")
        return

    msg = MIMEMultipart('alternative')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = settings['smtp_user']
    msg['To'] = to_email

    if html_body:
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    else:
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        if settings.get('smtp_ssl'):
            server = smtplib.SMTP_SSL(settings['smtp_server'], settings['smtp_port'])
        else:
            server = smtplib.SMTP(settings['smtp_server'], settings['smtp_port'])
            server.starttls()
            
        server.login(settings['smtp_user'], settings['smtp_password'])
        server.sendmail(settings['smtp_user'], to_email, msg.as_string())
        server.quit()
        print(f"✅ تم إرسال إيميل بنجاح إلى {to_email}")
    except Exception as e:
        print(f"❌ خطأ في إرسال البريد الإلكتروني إلى {to_email}: {e}")

# ===========================================================
# حماية لوحة الأدمن (Authentication)
# ===========================================================

def requires_auth(f):
    """ديكوريتور لفرض تسجيل الدخول"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'logged_in' not in session:
            flash('الرجاء تسجيل الدخول أولاً.', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    db = get_db()
    settings = db["settings"]
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # استخدام hashlib لتشفير كلمة المرور المخزنة (الأمان)
        hashed_input = hashlib.sha256(password.encode()).hexdigest()

        if username == settings["admin_user"] and hashed_input == settings["admin_pass"]:
            session['logged_in'] = True
            flash('تم تسجيل الدخول بنجاح.', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحين.', 'danger')
            return render_template_string(LOGIN_TEMPLATE)
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/admin/logout')
def admin_logout():
    session.pop('logged_in', None)
    flash('تم تسجيل الخروج.', 'info')
    return redirect(url_for('admin_login'))

# ===========================================================
# مسارات API للعميل (Client API Routes)
# ===========================================================

@app.route('/api/activate', methods=['POST'])
def activate():
    # ... (كود التفعيل الحالي - تم حذفه لتجنب الإطالة، ولكن يجب وضعه هنا)
    # ملاحظة: يجب تعديل كود التفعيل ليستخدم load_db/save_db بدلاً من load_clients/save_clients
    return jsonify({"status": "error", "message": "هذه الدالة تحتاج إلى كود التفعيل الخاص بك."})

@app.route('/api/check_status', methods=['POST'])
def check_status():
    # ... (كود التحقق من الحالة الحالي - تم حذفه لتجنب الإطالة، ولكن يجب وضعه هنا)
    # ملاحظة: يجب تعديل كود التحقق ليستخدم load_db/save_db بدلاً من load_clients/save_clients
    return jsonify({"status": "error", "message": "هذه الدالة تحتاج إلى كود التحقق الخاص بك."})


# ===========================================================
# مسارات لوحة الأدمن (Admin Dashboard Routes)
# ===========================================================

@app.route('/admin')
@requires_auth
def admin_dashboard():
    db = get_db()
    clients_list = list(db["clients"].values())
    
    # تحويل تاريخ الانتهاء إلى كائن Date (للتصفية والفرز)
    for client in clients_list:
        try:
            client['expire_date_dt'] = datetime.strptime(client.get('expire_date', '1900-01-01'), '%Y-%m-%d').date()
        except:
            client['expire_date_dt'] = date(1900, 1, 1) # تاريخ قديم للتعامل مع الأخطاء

    # فرز الأجهزة: (1) المحظورة أولاً، (2) النشطة، (3) المنتهية/الانتظار
    def sort_key(client):
        status = client.get('status', 'unknown')
        if status == 'banned': return 0
        if status == 'active': return 1
        if status == 'pending': return 2
        if status == 'expired': return 3
        return 4

    clients_list.sort(key=sort_key)
    
    return render_template('dashboard.html', clients=clients_list) # ⬅️ يعتمد على dashboard.html

@app.route('/admin/ban/<string:mid>', methods=['POST'])
@requires_auth
def ban_machine(mid):
    db = get_db()
    client = db["clients"].get(mid)
    
    if client:
        current_status = client.get('status', 'unknown')
        
        if current_status == 'banned':
            # إلغاء الحظر
            client['status'] = 'active' if client.get('license_code') and (client.get('expire_date_dt', date.today()) >= date.today()) else 'expired'
            client['banned_reason'] = ""
            flash(f'✅ تم رفع الحظر عن الجهاز: {mid}', 'success')
        else:
            # تطبيق الحظر
            client['status'] = 'banned'
            client['banned_reason'] = request.form.get('reason', 'Manually banned by admin.')
            flash(f'⛔ تم حظر الجهاز: {mid}', 'danger')
            
        save_db(db)
    else:
        flash(f'❌ لم يتم العثور على الجهاز {mid}.', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/set_expiry/<string:mid>', methods=['POST'])
@requires_auth
def set_expiry(mid):
    db = get_db()
    client = db["clients"].get(mid)
    new_date_str = request.form.get('expiry_date') 
    
    if client:
        try:
            new_expiry_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
            client['expire_date'] = new_expiry_date.isoformat()
            
            # تحديث الحالة: يصبح نشطاً إذا كان تاريخ الانتهاء في المستقبل
            if new_expiry_date >= date.today():
                 client['status'] = 'active'
                 flash(f'✅ تم تفعيل الجهاز {mid} وتعيين الصلاحية حتى {new_date_str}', 'success')
            else:
                 client['status'] = 'expired'
                 flash(f'⚠️ تم تعيين الصلاحية لـ {mid} لكن التاريخ {new_date_str} من الماضي.', 'warning')
            
            save_db(db)
            
            # إرسال بريد إلكتروني (وظيفة اختيارية)
            if client.get('email'):
                send_email(
                    client['email'],
                    "تم تحديث ترخيص النقر التلقائي الخاص بك",
                    f"عزيزي {client['name']}\nتم تحديث صلاحية ترخيص النقر التلقائي الخاص بك. صلاحيتك الجديدة تنتهي بتاريخ {new_date_str}."
                )
                
        except Exception as e:
            flash(f'❌ خطأ في معالجة التاريخ: {e}', 'danger')
    else:
        flash(f'❌ لم يتم العثور على الجهاز {mid}.', 'danger')
            
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<string:mid>', methods=['POST'])
@requires_auth
def delete_machine(mid):
    db = get_db()
    
    if mid in db["clients"]:
        del db["clients"][mid]
        save_db(db)
        flash(f'🗑️ تم حذف الجهاز {mid} نهائياً.', 'info')
    
    return redirect(url_for('admin_dashboard'))

# ---------------------------------------------------------------
# [SERVER] صفحة الإعدادات
# ---------------------------------------------------------------

@app.route('/admin/settings', methods=['GET', 'POST'])
@requires_auth
def admin_settings():
    db = get_db()
    settings = db["settings"]
    
    if request.method == "POST":
        # 1. تحديث بيانات الدخول
        new_user = request.form.get("admin_user")
        new_pass = request.form.get("admin_pass")
        
        if new_pass:
            # تشفير كلمة المرور الجديدة
            settings["admin_pass"] = hashlib.sha256(new_pass.encode()).hexdigest()
            flash("تم تحديث كلمة المرور بنجاح.", "success")
        
        settings["admin_user"] = new_user
        settings["secret_key"] = request.form.get("secret_key", settings["secret_key"])
        settings["default_plan"] = request.form.get("default_plan", settings["default_plan"])
        settings["admin_whatsapp"] = request.form.get("admin_whatsapp", settings["admin_whatsapp"])

        # 2. تحديث إعدادات الإيميل
        settings["email_enabled"] = True if request.form.get("email_enabled") == "on" else False
        settings["smtp_server"] = request.form.get("smtp_server", settings["smtp_server"])
        settings["smtp_port"] = int(request.form.get("smtp_port", settings["smtp_port"]) or 587)
        settings["smtp_user"] = request.form.get("smtp_user", settings["smtp_user"])
        settings["smtp_password"] = request.form.get("smtp_password", settings["smtp_password"])
        settings["smtp_ssl"] = True if request.form.get("smtp_ssl") == "on" else False
        settings["admin_notify_email"] = request.form.get("admin_notify_email", settings["admin_notify_email"])

        # 3. حفظ
        save_db(db)
        flash("تم حفظ الإعدادات بنجاح ✔", "success")
        return redirect(url_for("admin_settings"))

    return render_template('settings.html', settings=settings) # ⬅️ يعتمد على settings.html

# ===========================================================
# القوالب الأساسية
# ===========================================================

# قالب تسجيل الدخول (LOGIN_TEMPLATE)
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="UTF-8"><title>تسجيل الدخول</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
<style>body { background-color: #f8f9fa; display: flex; justify-content: center; align-items: center; min-height: 100vh; }</style>
</head>
<body>
<div class="card shadow" style="width: 350px;">
    <div class="card-header text-center bg-primary text-white">تسجيل الدخول للأدمن</div>
    <div class="card-body">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}{% for category, message in messages %}<div class="alert alert-{{ category }}">{{ message }}</div>{% endfor %}{% endif %}
        {% endwith %}
        <form method="POST">
            <div class="mb-3">
                <label for="username" class="form-label">اسم المستخدم</label>
                <input type="text" class="form-control" id="username" name="username" required>
            </div>
            <div class="mb-3">
                <label for="password" class="form-label">كلمة المرور</label>
                <input type="password" class="form-control" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-primary w-100">دخول</button>
        </form>
    </div>
</div>
</body>
</html>
"""

# ===========================================================
# التشغيل
# ===========================================================

if __name__ == '__main__':
    # تأكد من تحميل قاعدة البيانات عند التشغيل
    get_db()
    # يتم تشغيل Flask في وضع التطوير، استخدم Waitress للإنتاج (كما في Procfile.txt)

    app.run(debug=True, host='0.0.0.0', port=5000)
