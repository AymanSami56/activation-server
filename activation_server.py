from flask import Flask, request, jsonify
import hashlib

app = Flask(__name__)

SECRET_KEY = "AYMAN_SUPER_SECRET_2025"

def generate_code(machine_id, plan):
    mid = machine_id.replace("-", "").upper()
    base = f"{mid}{plan}{SECRET_KEY}"
    d = hashlib.sha256(base.encode()).hexdigest()
    n = int(d, 16) % (10**16)
    return f"{n:016d}"

@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "server": "Ayman Activation Server",
        "version": "1.0"
    })

@app.route("/test")
def test():
    return jsonify({"status": "ok", "message": "Server Working"})

@app.route("/activate")
def activate():
    machine_id = request.args.get("machine_id")
    plan = request.args.get("plan")
    code = request.args.get("code")

    if not machine_id or not plan or not code:
        return jsonify({"valid": False, "error": "Missing parameters"})

    expected = generate_code(machine_id, plan)
    clean = "".join(ch for ch in code if ch.isdigit())

    return jsonify({
        "valid": clean == expected,
        "expected": expected
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
