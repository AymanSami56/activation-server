from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import hashlib
import json
import os

app = Flask(__name__)

SECRET_KEY = "AYMAN_SUPER_SECRET_2025"
DB_FILE = "clients.json"


def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            json.dump({}, f)
    with open(DB_FILE, "r") as f:
        return json.load(f)


def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)


def generate_expected_code(machine_id, plan):
    base = f"{machine_id}{plan}{SECRET_KEY}"
    d = hashlib.sha256(base.encode()).hexdigest()
    num = int(d, 16) % (10**16)
    return f"{num:016d}"


@app.route("/verify", methods=["POST"])
def verify():
    data = request.json

    if not data:
        return jsonify({"status": "error", "msg": "No JSON received"}), 400

    machine_id = data.get("machine_id")
    plan = data.get("plan")
    code_input = data.get("code")

    if not machine_id or not plan or not code_input:
        return jsonify({"status": "error", "msg": "Missing fields"}), 400

    # Normalize
    code_input_clean = "".join([c for c in code_input if c.isdigit()])
    expected = generate_expected_code(machine_id, plan)

    if code_input_clean != expected:
        return jsonify({
            "status": "invalid",
            "msg": "Activation code incorrect"
        })

    # Valid code → Check or create subscription
    db = load_db()

    if machine_id not in db:
        # New client
        if plan == "M":
            exp = datetime.now() + timedelta(days=30)
        else:
            exp = datetime.now() + timedelta(days=365)

        db[machine_id] = {
            "plan": plan,
            "expire": exp.strftime("%Y-%m-%d")
        }
        save_db(db)

        return jsonify({
            "status": "ok",
            "msg": "Activated successfully",
            "expire": exp.strftime("%Y-%m-%d")
        })

    else:
        # Existing client → Check expiry
        exp_str = db[machine_id]["expire"]
        exp = datetime.strptime(exp_str, "%Y-%m-%d")

        if datetime.now() > exp:
            return jsonify({
                "status": "expired",
                "msg": "Subscription expired",
                "expire": exp_str
            })

        return jsonify({
            "status": "ok",
            "msg": "Subscription valid",
            "expire": exp_str
        })


@app.route("/", methods=["GET"])
def home():
    return "Ayman Activation Server ✔ Online"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
