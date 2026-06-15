from flask import Flask, request, jsonify
import threading
import uuid
from bot import run_job

app = Flask(__name__)
jobs = {}

@app.route("/start", methods=["POST"])
def start_job():
    data = request.get_json(force=True, silent=True) or request.form
    phone    = data.get("phone", "").strip()
    password = data.get("password", "").strip()

    if not phone or not password:
        return jsonify({"error": "Missing phone or password"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status":    "starting",
        "message":   "Initializing...",
        "completed": 0,
        "total":     0,
        "log":       []
    }

    t = threading.Thread(target=run_job, args=(phone, password, job_id, jobs))
    t.daemon = True
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>", methods=["GET"])
def get_status(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(jobs[job_id])


@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "NNNRC Bot API is running."})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)