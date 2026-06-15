import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NnnrcBot:
    def __init__(self, phone, password, job_id, status_dict):
        self.phone = phone
        self.password = password
        self.job_id = job_id
        self.status_dict = status_dict
        self.token = None
        self.session = requests.Session()
        
        # Shared headers
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/148.0.0.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://nnnrc.com",
            "Referer": "https://nnnrc.com/",
            "Authority": "app.nnnrc.com"
        })

    def update_status(self, status_msg, completed=None, total=None):
        if self.job_id and self.status_dict is not None:
            if self.job_id not in self.status_dict:
                self.status_dict[self.job_id] = {}
            self.status_dict[self.job_id]["message"] = status_msg
            if completed is not None:
                self.status_dict[self.job_id]["completed"] = completed
            if total is not None:
                self.status_dict[self.job_id]["total"] = total

    def login(self):
        url = "https://app.nnnrc.com/api/user/login"
        payload = {
            "username": self.phone,
            "password": self.password,
            "lang": "en"
        }
        self.update_status("Logging in...")
        try:
            resp = self.session.post(url, data=payload)
            data = resp.json()
            if data.get("code") == 1 and "info" in data:
                self.token = data["info"].get("token")
                total_tasks = data["info"].get("number", 0)
                logging.info(f"Login successful. Token acquired. Total available tasks: {total_tasks}")
                self.update_status("Login successful", completed=0, total=total_tasks)
                return True
            else:
                logging.error(f"Login failed: {data}")
                self.update_status(f"Login failed: {data.get('code_dec', 'Unknown error')}")
                return False
        except Exception as e:
            logging.error(f"Login error: {e}")
            self.update_status(f"Login error: {str(e)}")
            return False

    def get_tasks(self, page=1):
        url = "https://app.nnnrc.com/api/task/taskOrderlist"
        payload = {
            "status": "1",
            "page_no": str(page),
            "is_u": "2",
            "lang": "en",
            "token": self.token
        }
        try:
            resp = self.session.post(url, data=payload)
            data = resp.json()
            if data.get("code") == 1:
                return data
            else:
                logging.error(f"Failed to get tasks page {page}: {data}")
                return None
        except Exception as e:
            logging.error(f"Get tasks error: {e}")
            return None

    def complete_task(self, task_id):
        url = "https://app.nnnrc.com/api/task/receiveTask"
        payload = {
            "id": str(task_id),
            "lang": "en",
            "token": self.token
        }
        try:
            resp = self.session.post(url, data=payload)
            data = resp.json()
            if data.get("code") == 1:
                logging.info(f"Task {task_id} completed successfully.")
                return True
            else:
                logging.warning(f"Task {task_id} failed: {data}")
                return False
        except Exception as e:
            logging.error(f"Complete task error: {e}")
            return False

    def run(self):
        if not self.login():
            return
        
        empty_tries = 0
        tasks_completed = 0
        total_tasks_target = self.status_dict[self.job_id].get("total", 0)

        while empty_tries < 5:
            self.update_status(f"Fetching tasks... (Completed: {tasks_completed})")
            
            # Fetch page 1 (we rely on page 1 always yielding tasks if any exist)
            task_data = self.get_tasks(page=1)
            
            if not task_data or not task_data.get("info"):
                empty_tries += 1
                logging.info(f"No tasks found. Try {empty_tries}/5. Waiting 30s...")
                self.update_status(f"No tasks available. Waiting 30s... (Retry {empty_tries}/5)")
                time.sleep(30)
                continue
                
            tasks = task_data.get("info", [])
            empty_tries = 0 # reset on finding tasks
            
            for task in tasks:
                task_id = task.get("id")
                if not task_id:
                    continue
                    
                self.update_status(f"Completing task {task_id}...")
                success = self.complete_task(task_id)
                if success:
                    tasks_completed += 1
                    self.update_status(f"Task {task_id} completed. Waiting 22s...", completed=tasks_completed)
                else:
                    self.update_status(f"Task {task_id} failed. Waiting 22s...", completed=tasks_completed)
                
                # Wait 22s between tasks
                time.sleep(22)
        
        self.update_status("Job finished. No more tasks after 5 retries.", completed=tasks_completed)
        logging.info("Bot execution finished.")

def run_job(phone, password, job_id, status_dict):
    bot = NnnrcBot(phone, password, job_id, status_dict)
    try:
        bot.run()
    except Exception as e:
        bot.update_status(f"Fatal error: {str(e)}")
        logging.error(f"Fatal job error: {e}", exc_info=True)
