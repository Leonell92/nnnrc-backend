import threading
import uuid
import logging
from fastapi import FastAPI, Request
from bot import run_job
import flet as ft
import flet.fastapi as flet_fastapi

# Add NRC APK directory to path so we can import the UI main function
import sys
import os
apk_path = os.path.join(os.path.dirname(__file__), "NRC APK")
sys.path.append(apk_path)
from main import main as flet_main

app = FastAPI()
jobs = {}

@app.post("/start")
async def start_job(request: Request):
    try:
        data = await request.json()
    except:
        data = await request.form()
    
    phone    = data.get("phone", "").strip()
    password = data.get("password", "").strip()

    if not phone or not password:
        return {"error": "Missing phone or password"}

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

    return {"job_id": job_id}

@app.get("/status/{job_id}")
def get_status(job_id: str):
    if job_id not in jobs:
        return {"error": "Job not found"}
    return jobs[job_id]

@app.get("/debug/{job_id}")
def get_debug(job_id: str):
    if job_id not in jobs:
        return {"error": "Job not found"}
    return {
        "status":  jobs[job_id].get("status"),
        "message": jobs[job_id].get("message"),
        "completed": jobs[job_id].get("completed"),
        "total":   jobs[job_id].get("total"),
        "full_log": jobs[job_id].get("log", [])
    }

@app.get("/api-status")
def index():
    return {"message": "NNNRC Bot API is running."}

# Mount the Flet app at the root. Anyone visiting the URL will see the Flet UI.
app.mount("/", flet_fastapi.app(flet_main))
