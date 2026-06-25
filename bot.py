import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# How long to pause between task completions (seconds).
# The site seems to need ~20-25s between calls to avoid rate-limiting.
TASK_DELAY     = 22
# Seconds to wait when the API returns no tasks before trying again
EMPTY_WAIT     = 30
# Max consecutive empty sweeps before we declare "all done"
MAX_EMPTY_TRIES = 1
# Max individual network retries per API call
MAX_RETRIES    = 3
RETRY_BACKOFF  = [5, 15, 30]   # seconds between retries


class NnnrcBot:
    def __init__(self, phone, password, job_id, status_dict, api_base="https://app.nnnrc.com"):
        self.phone       = phone
        self.password    = password
        self.job_id      = job_id
        self.status_dict = status_dict
        self.api_base    = api_base
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

    def _post_with_retry(self, url, data, label="request"):
        """POST with automatic retry + backoff. Returns parsed JSON or None."""
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.post(url, data=data, timeout=20)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.Timeout:
                wait = RETRY_BACKOFF[attempt]
                self._set(message=f"⏱️ {label} timeout (attempt {attempt+1}/{MAX_RETRIES}), retrying in {wait}s...")
                time.sleep(wait)
            except requests.exceptions.ConnectionError:
                wait = RETRY_BACKOFF[attempt]
                self._set(message=f"🔌 {label} connection error (attempt {attempt+1}/{MAX_RETRIES}), retrying in {wait}s...")
                time.sleep(wait)
            except Exception as e:
                self._set(message=f"❌ {label} error: {e}")
                return None
        self._set(message=f"❌ {label} failed after {MAX_RETRIES} attempts.")
        return None

    # ── login ─────────────────────────────────────────────────
    def login(self):
        raw = self.phone.strip().lstrip("+")
        if raw.startswith("234"):
            raw = raw[3:]
        if raw.startswith("0"):
            raw = raw[1:]

        for username in [raw, "0" + raw]:
            self._set(message=f"🔑 Trying login: {username}")
            data = self._post_with_retry(
                f"{self.api_base}/api/user/login",
                {"username": username, "password": self.password, "lang": "en"},
                label=f"login({username})"
            )
            if not data:
                continue

            if data.get("code") == 1:
                self.token = data["info"]["token"]
                total      = data["info"].get("number", 0)
                self._set(
                    message=f"✅ Login SUCCESS ({username}). Tasks available: {total}",
                    completed=0, total=total, status="running"
                )
                return True
            else:
                self._set(message=f"❌ Login failed ({username}): {data.get('code_dec', data.get('msg', 'unknown'))}")

        return False

    def _relogin(self):
        """Re-authenticate when token expires mid-run."""
        self._set(message="🔄 Token expired — re-logging in...")
        return self.login()

    # ── fetch task list ────────────────────────────────────────
    def get_tasks(self, page=1):
        data = self._post_with_retry(
            f"{self.api_base}/api/task/taskOrderlist",
            {"status": "1", "page_no": str(page),
             "is_u": "2", "lang": "en", "token": self.token},
            label=f"get_tasks(p{page})"
        )
        if data:
            # Log a trimmed summary (not the full blob)
            code = data.get("code")
            msg  = data.get("code_dec", data.get("msg", ""))
            count = len(data.get("info", [])) if isinstance(data.get("info"), list) else "-"
            self._set(message=f"📄 Page {page} API → code={code} msg='{msg}' tasks={count}")
        return data

    # ── complete one task ─────────────────────────────────────
    def complete_task(self, task_id):
        data = self._post_with_retry(
            f"{self.api_base}/api/task/receiveTask",
            {"id": str(task_id), "lang": "en", "token": self.token},
            label=f"receiveTask({task_id})"
        )
        if not data:
            return False

        code = data.get("code")
        msg  = data.get("code_dec", data.get("msg", ""))

        # Token expired mid-run — re-login and retry once
        if code in (401, -1) or "token" in str(msg).lower() or "login" in str(msg).lower():
            if self._relogin():
                data = self._post_with_retry(
                    f"{self.api_base}/api/task/receiveTask",
                    {"id": str(task_id), "lang": "en", "token": self.token},
                    label=f"receiveTask({task_id}) retry"
                )
                if data:
                    code = data.get("code")
                    msg  = data.get("code_dec", data.get("msg", ""))

        return code == 1

    # ── main loop ─────────────────────────────────────────────
    def run(self):
        self._set(message="🤖 Bot starting...", status="running")

        if not self.login():
            self._set(message="❌ Login failed — stopping.", status="error")
            return

        tasks_completed = 0
        empty_tries     = 0
        done_ids        = set()   # track IDs we've already processed this session
        total_pages     = 3       # confirmed 3 pages of tasks

        while empty_tries < MAX_EMPTY_TRIES:
            found_new_task = False

            for page in range(1, total_pages + 1):
                self._set(message=f"📋 Sweeping page {page}/{total_pages}... (Completed so far: {tasks_completed})")
                task_data = self.get_tasks(page=page)

                if not task_data:
                    self._set(message=f"⚠️ No response on page {page}, skipping...")
                    continue

                api_code  = task_data.get("code")
                api_msg   = task_data.get("code_dec", task_data.get("msg", ""))
                task_list = task_data.get("info", [])

                if not isinstance(task_list, list):
                    task_list = []

                # Token expired — relogin and re-fetch this page
                if api_code in (401, -1) or "token" in str(api_msg).lower():
                    self._set(message=f"🔄 Session expired on page {page}, re-logging in...")
                    if not self._relogin():
                        self._set(message="❌ Re-login failed — stopping.", status="error")
                        return
                    task_data = self.get_tasks(page=page)
                    if task_data:
                        api_code  = task_data.get("code")
                        task_list = task_data.get("info", [])
                        if not isinstance(task_list, list):
                            task_list = []

                if api_code != 1 or not task_list:
                    self._set(message=f"ℹ️ Page {page}: no tasks (code={api_code})")
                    continue

                self._set(message=f"✅ Page {page}: {len(task_list)} tasks available")

                for task in task_list:
                    task_id = (task.get("task_id") or task.get("id")
                               or task.get("order_id") or task.get("taskId"))

                    if not task_id:
                        self._set(message=f"⚠️ Unknown task structure: {list(task.keys())}")
                        continue

                    if task_id in done_ids:
                        self._set(message=f"⏭️ Skipping {task_id} (already done this session)")
                        continue

                    found_new_task = True
                    self._set(message=f"⏳ Submitting task {task_id}...")
                    success = self.complete_task(task_id)
                    done_ids.add(task_id)

                    if success:
                        tasks_completed += 1
                        self._set(
                            message=f"✅ Task {task_id} done! ({tasks_completed} completed)",
                            completed=tasks_completed
                        )
                    else:
                        self._set(message=f"❌ Task {task_id} failed — continuing to next.")

                    # Pause between tasks to avoid rate limiting
                    time.sleep(TASK_DELAY)

            if found_new_task:
                empty_tries = 0
            else:
                empty_tries += 1
                self._set(
                    message=f"⏸️ No new tasks found across all pages. "
                            f"({empty_tries}/{MAX_EMPTY_TRIES}) — waiting {EMPTY_WAIT}s..."
                )
                time.sleep(EMPTY_WAIT)

        self._set(
            message=f"🏁 All done! Total tasks completed this session: {tasks_completed}",
            completed=tasks_completed,
            status="finished"
        )


# ── entry point called by app.py ─────────────────────────────
def run_job(phone, password, job_id, status_dict, api_base="https://app.nnnrc.com"):
    bot = NnnrcBot(phone, password, job_id, status_dict, api_base=api_base)
    try:
        bot.run()
    except Exception as e:
        status_dict.setdefault(job_id, {})["message"] = f"Fatal: {e}"
        status_dict[job_id]["status"] = "error"
        logging.error(f"Fatal job error: {e}", exc_info=True)