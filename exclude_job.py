import sys
import json
import os

EXCLUDED_IDS_FILE = "excluded_ids.json"

def load_excluded_ids():
    """Load permanently excluded job IDs from separate file."""
    if os.path.exists(EXCLUDED_IDS_FILE):
        try:
            with open(EXCLUDED_IDS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()

def save_excluded_ids(ids_set):
    """Save permanently excluded job IDs to separate file."""
    try:
        with open(EXCLUDED_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(ids_set)), f, ensure_ascii=False, indent=2)
        print(f"Updated {EXCLUDED_IDS_FILE} with {len(ids_set)} excluded IDs.")
    except Exception as e:
        print(f"Error saving {EXCLUDED_IDS_FILE}: {e}")

def main():
    issue_title = os.environ.get("ISSUE_TITLE")
    if not issue_title:
        if len(sys.argv) < 2:
            print("No issue title provided.")
            return
        issue_title = sys.argv[1]

    # Expecting title like "exclude:https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=54166764"
    if not issue_title.startswith("exclude:"):
        print("Invalid issue title format.")
        return

    job_id = issue_title.replace("exclude:", "").strip()
    print(f"Target job ID to exclude: {job_id}")

    STATE_FILE = "sent_jobs.json"
    if not os.path.exists(STATE_FILE):
        print("State file does not exist.")
        return

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except Exception as e:
        print(f"Error reading state file: {e}")
        return

    updated_jobs = []
    found = False
    for job in jobs:
        # Check by id or link
        if job.get("id") == job_id or job.get("link") == job_id:
            job["excluded"] = True
            found = True
            print(f"Marked job {job_id} as excluded.")
        updated_jobs.append(job)

    if not found:
        # If not found in active jobs, add a stub to prevent future addition in main scraper runs
        import datetime
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        stub = {
            "id": job_id,
            "title": "Excluded Job Stub",
            "company": "N/A",
            "link": job_id,
            "date": "상시채용",
            "career": "N/A",
            "site_name": "N/A",
            "keyword": "N/A",
            "first_seen": today_str,
            "excluded": True
        }
        updated_jobs.append(stub)
        print(f"Job ID not found in active list. Added stub to prevent future addition.")

    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_jobs, f, ensure_ascii=False, indent=2)
        print("Saved updated sent_jobs.json.")
    except Exception as e:
        print(f"Error saving state file: {e}")

    # Also save to permanent excluded IDs file
    excluded_ids = load_excluded_ids()
    excluded_ids.add(job_id)
    save_excluded_ids(excluded_ids)

if __name__ == "__main__":
    main()
