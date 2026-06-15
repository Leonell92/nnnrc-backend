import requests
import time
import logging
import hashlib

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class NnnrcBot:
    def __init__(self, phone, password, job_id, status_dict):
        self.phone       = phone
        self.password    = password
        self.job_id      = job_id
        self.status_dict = status_dict
        self.token       = None
        self.session     = requests.Session()
        self.session.headers.update({
            "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/148.0.0.0",
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type":    "application/x-www-form-urlencoded",
            "Origin":          "https://nnnrc.com",
            "Referer":         "https://nnnrc.com/",
        })

    # ── helpers ──────────────────────────────────────────────
    def _set(self, message=None, completed=None, total=None, status=None):
        """Single helper to update every field of this job's status dict."""
        entry = self.status_dict.setdefault(self.job_id, {})
        if message   is not None:
            entry["message"] = message
            entry.setdefault("log", []).append(message)
            logging.info(message)
        if completed is not None:
            entry["completed"] = completed
        if total     is not None:
            entry["total"] = total
        if status    is not None:
            entry["status"] = status

    # ── login ─────────────────────────────────────────────────
    def login(self):
        raw = self.phone.strip().lstrip("+")
        if raw.startswith("234"):
            raw = raw[3:]
        if raw.startswith("0"):
            raw = raw[1:]

        # MD5-hash the password (site hashes it in JS before submitting)
        hashed_pwd = hashlib.md5(self.password.encode()).hexdigest()

        # Try both phone formats
        for username in [raw, "0" + raw]:
            self._set(message=f"Trying login with: {username}")
            try:
                resp = self.session.post(
                    "https://app.nnnrc.com/api/user/login",
                    data={"username": username, "password": hashed_pwd, "lang": "en"},
                    timeout=15
                )
                self._set(message=f"Login response: {resp.text[:300]}")
                data = resp.json()
                if data.get("code") == 1:
                    self.token = data["info"]["token"]
                    total      = data["info"].get("number", 0)
                    self._set(
                        message=f"✅ Login SUCCESS ({username}). Tasks available: {total}",
                        completed=0, total=total, status="running"
                    )
                    return True
                else:
                    self._set(message=f"❌ Login failed ({username}): {data.get('code_dec','')}")
            except Exception as e:
                self._set(message=f"Login exception ({username}): {e}")

        return False

    # ── fetch task list ────────────────────────────────────────
    def get_tasks(self, page=1):
        try:
            resp = self.session.post(
                "https://app.nnnrc.com/api/task/taskOrderlist",
                data={"status": "1", "page_no": str(page),
                      "is_u": "2", "lang": "en", "token": self.token},
                timeout=15
            )
            self._set(message=f"taskOrderlist p{page}: {resp.text[:400]}")
            return resp.json()
        except Exception as e:
            self._set(message=f"get_tasks error: {e}")
            return None

    # ── complete one task ─────────────────────────────────────
    def complete_task(self, task_id):
        try:
            resp = self.session.post(
                "https://app.nnnrc.com/api/task/receiveTask",
                data={"id": str(task_id), "lang": "en", "token": self.token},
                timeout=15
            )
            self._set(message=f"receiveTask {task_id}: {resp.text[:200]}")
            return resp.json().get("code") == 1
        except Exception as e:
            self._set(message=f"complete_task error: {e}")
            return False

    # ── main loop ─────────────────────────────────────────────
    def run(self):
        self._set(message="🤖 Bot starting...", status="running")

        if not self.login():
            self._set(message="Login failed — stopping.", status="error")
            return

        tasks_completed = 0
        empty_tries     = 0
        done_ids        = set()   # track IDs we've already processed

        while empty_tries < 5:
            found_new_task = False

            # Loop all pages (up to 3 as confirmed by the API)
            total_pages = 3
            for page in range(1, total_pages + 1):
                self._set(message=f"📋 Fetching page {page}/{total_pages}... (Done: {tasks_completed})")
                task_data = self.get_tasks(page=page)

                if not task_data:
                    self._set(message=f"No response on page {page}, skipping...")
                    continue

                api_code  = task_data.get("code")
                api_msg   = task_data.get("code_dec", task_data.get("msg", ""))
                task_list = task_data.get("info", [])

                if not isinstance(task_list, list):
                    task_list = []

                if api_code != 1 or not task_list:
                    self._set(message=f"Page {page}: code={api_code} '{api_msg}'")
                    continue

                self._set(message=f"✅ Page {page}: {len(task_list)} tasks found")

                for task in task_list:
                    task_id = (task.get("task_id") or task.get("id")
                               or task.get("order_id") or task.get("taskId"))

                    if not task_id:
                        self._set(message=f"⚠️ Unknown task structure: {task}")
                        continue

                    # Skip tasks we already completed this session
                    if task_id in done_ids:
                        self._set(message=f"⏭️ Skipping {task_id} (already done)")
                        continue

                    found_new_task = True
                    self._set(message=f"⏳ Completing task {task_id}...")
                    success = self.complete_task(task_id)
                    done_ids.add(task_id)

                    if success:
                        tasks_completed += 1
                        self._set(message=f"✅ Task {task_id} done! ({tasks_completed} total)",
                                  completed=tasks_completed)
                    else:
                        self._set(message=f"❌ Task {task_id} failed.")

                    time.sleep(22)

            if found_new_task:
                empty_tries = 0   # reset retry counter when we found work
            else:
                empty_tries += 1
                self._set(message=f"No new tasks across all pages. Retry {empty_tries}/5 — waiting 30s...")
                time.sleep(30)

        self._set(message=f"🏁 Finished! Total tasks completed: {tasks_completed}",
                  completed=tasks_completed, status="finished")


# ── entry point called by app.py ─────────────────────────────
def run_job(phone, password, job_id, status_dict):
    bot = NnnrcBot(phone, password, job_id, status_dict)
    try:
        bot.run()
    except Exception as e:
        status_dict.setdefault(job_id, {})["message"] = f"Fatal: {e}"
        status_dict[job_id]["status"] = "error"
        logging.error(f"Fatal job error: {e}", exc_info=True)