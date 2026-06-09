import json
import os
import sys
from scraper import JobScraper
from notifier import JobNotifier

# Ensure UTF-8 output on Windows console
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

STATE_FILE = "sent_jobs.json"

def load_sent_jobs():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
        except Exception as e:
            print(f"Warning: Could not parse state file {STATE_FILE}. Starting fresh. Error: {e}")
    return set()

def save_sent_jobs(sent_jobs_set):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(sent_jobs_set), f, ensure_ascii=False, indent=2)
        print(f"Updated state file: {STATE_FILE} saved with {len(sent_jobs_set)} job entries.")
    except Exception as e:
        print(f"Error saving state file {STATE_FILE}: {e}")

def main():
    print("=== Job Information Scraping & Notification Tool ===")
    
    # Debug environment variables configuration safely
    print("\n[Debug] Checking Environment Variables:")
    required_vars = ["SMTP_SERVER", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "RECIPIENT_EMAIL"]
    for var in required_vars:
        val = os.getenv(var)
        if val:
            masked = val[:2] + "*" * (len(val) - 2) if len(val) > 2 else "**"
            print(f"  - {var}: 설정됨 (길이: {len(val)}, 마스킹: '{masked}')")
        else:
            print(f"  - {var}: 미설정 (비어있음 ❌)")
            
    # 1. Initialize scraper
    scraper = JobScraper()
    
    # 2. Scrape all listings
    print("\nStarting scraping process...")
    all_jobs = scraper.scrape_all()
    print(f"Total jobs crawled from search pages: {len(all_jobs)}")
    
    # 3. Load previously sent jobs
    sent_jobs = load_sent_jobs()
    print(f"Loaded {len(sent_jobs)} historical job links from state.")
    
    # 4. Filter out already sent jobs
    new_jobs = []
    for job in all_jobs:
        if job["id"] not in sent_jobs:
            new_jobs.append(job)
            
    print(f"Filtered down to {len(new_jobs)} NEW jobs.")
    
    # 5. Notify if there are new jobs
    if new_jobs:
        notifier = JobNotifier()
        if notifier.is_configured():
            print(f"\nSending notification for {len(new_jobs)} new jobs...")
            success = notifier.send_notification(new_jobs)
            if success:
                # Add to history and save
                for job in new_jobs:
                    sent_jobs.add(job["id"])
                save_sent_jobs(sent_jobs)
            else:
                print("Notification failed. State has NOT been updated.")
        else:
            print("\nSMTP is not configured. Print new job listings to console instead:")
            for idx, job in enumerate(new_jobs, 1):
                print(f"[{idx}] {job['company']} - {job['title']}")
                print(f"    Link: {job['link']}")
                print(f"    Date: {job['date']} | Site: {job['site_name']} | Keywords: {job['keyword']}")
    else:
        print("\nNo new job listings found. Notification skipped.")
        
    print("\n=== Process Completed ===")

if __name__ == "__main__":
    main()
