import json
import os
import sys
import datetime
from scraper import JobScraper
from notifier import JobNotifier

# Ensure UTF-8 output on Windows console
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import re

STATE_FILE = "sent_jobs.json"

def normalize_company_name(name):
    # Remove common corporate suffixes and prefixes
    indicators = ["(주)", "주식회사", "(유)", "유한회사", "㈜", " 유한회사", " 주식회사", "(사)", "사단법인", "(재)", "재단법인"]
    for ind in indicators:
        name = name.replace(ind, "")
    # Remove spaces and convert to lowercase
    return "".join(name.split()).lower()

def normalize_title(title):
    # Remove spaces, convert to lowercase, and strip special characters
    title = "".join(title.split()).lower()
    return re.sub(r'[^a-zA-Z0-9가-힣]', '', title)

def is_junior_or_mid_level(career_text, title):
    title_lower = title.lower()
    career_clean = career_text.replace(" ", "")
    
    # 1. Blacklist title keywords (junior, mid-level, staff, team members, up to GM/부장)
    blacklist_title = [
        "신입", "인턴", "사원", "주임", "대리", "과장", "차장", "부장",
        "팀원", "담당자", "실무자", "어소시에이트",
        "junior", "staff", "associate", "assistant", "intern", "member"
    ]
    for kw in blacklist_title:
        if kw in title_lower:
            # Exception: e.g., "임원/부장급 이상" or "부장급 이상" which explicitly mentions "이상" (above) or "임원" (executive)
            if kw == "부장" and ("이상" in title_lower or "임원" in title_lower):
                continue
            return True

    # 2. Check career requirement text
    # Filter out entry-level, no-experience-needed, or open to anyone
    if any(x in career_clean for x in ["신입", "무관", "초보"]):
        return True
        
    # Extract numbers (years of experience)
    # e.g., "경력5년↑" -> 5; "경력10년↑" -> 10; "경력 3~5년" -> [3, 5]
    numbers = [int(n) for n in re.findall(r'\d+', career_clean)]
    if numbers:
        max_years = max(numbers)
        # Filter out if the required experience is less than 10 years
        if max_years < 10:
            return True
            
    return False

def deduplicate_jobs(jobs):
    deduped = []
    for job in jobs:
        norm_corp = normalize_company_name(job["company"])
        norm_title = normalize_title(job["title"])
        
        found = False
        for existing in deduped:
            exist_corp = normalize_company_name(existing["company"])
            exist_title = normalize_title(existing["title"])
            
            # If companies are highly similar AND titles are highly similar
            if (norm_corp == exist_corp or norm_corp in exist_corp or exist_corp in norm_corp) and \
               (norm_title == exist_title or norm_title in exist_title or exist_title in norm_title):
                
                # Deduplicate by merging site names and links
                sites = [s.strip() for s in existing["site_name"].split(",")]
                if job["site_name"] not in sites:
                    existing["site_name"] += f", {job['site_name']}"
                    
                # Combine link references
                if "links" not in existing:
                    existing["links"] = {existing["site_name"].split(",")[0].strip(): existing["link"]}
                existing["links"][job["site_name"]] = job["link"]
                
                # Combine matched keywords
                existing_kws = [k.strip() for k in existing["keyword"].split(",")]
                new_kws = [k.strip() for k in job["keyword"].split(",")]
                combined_kws = list(set(existing_kws + new_kws))
                existing["keyword"] = ", ".join(combined_kws)
                
                found = True
                break
                
        if not found:
            # Initialize links dict for single links
            job["links"] = {job["site_name"]: job["link"]}
            deduped.append(job)
            
    return deduped

def load_active_jobs():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    # Migration: If it's a list of strings (old format), discard and return empty list
                    if data and isinstance(data[0], str):
                        print("Migrating old state file format (list of strings) to new list of dicts format.")
                        return []
                    return data
        except Exception as e:
            print(f"Warning: Could not parse state file {STATE_FILE}. Starting fresh. Error: {e}")
    return []

def save_active_jobs(jobs_list):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(jobs_list, f, ensure_ascii=False, indent=2)
        print(f"Updated state file: {STATE_FILE} saved with {len(jobs_list)} active job entries.")
    except Exception as e:
        print(f"Error saving state file {STATE_FILE}: {e}")

def parse_deadline_date(date_text, current_year=2026):
    text = date_text.strip()
    
    # Check for keywords indicating no specific date
    if any(x in text for x in ["상시", "채용시", "상세", "미상", "종료", "마감", "접수"]):
        return None
        
    # Match YYYY-MM-DD
    match_long = re.search(r'(\d{4})[-./](\d{1,2})[-./](\d{1,2})', text)
    if match_long:
        try:
            year, month, day = map(int, match_long.groups())
            return datetime.date(year, month, day)
        except ValueError:
            return None
            
    # Match MM/DD or MM.DD
    match_short = re.search(r'(\d{1,2})[-./](\d{1,2})', text)
    if match_short:
        try:
            month, day = map(int, match_short.groups())
            d = datetime.date(current_year, month, day)
            now = datetime.date.today()
            if now.month in [11, 12] and month in [1, 2]:
                d = datetime.date(current_year + 1, month, day)
            return d
        except ValueError:
            return None
            
    return None

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
    print(f"Total raw jobs crawled: {len(all_jobs)}")
    
    # 3. Deduplicate listings across multiple search queries and sites
    deduped_jobs = deduplicate_jobs(all_jobs)
    print(f"Deduplicated jobs: {len(deduped_jobs)}")
    
    # 4. Filter out junior/mid-level jobs (keep only senior/executive levels)
    new_senior_jobs = []
    for job in deduped_jobs:
        if not is_junior_or_mid_level(job["career"], job["title"]):
            new_senior_jobs.append(job)
        else:
            print(f"  [Filtered Out] {job['company']} - {job['title']} (Career: {job['career']})")
    print(f"Filtered (Senior/Executive only) jobs: {len(new_senior_jobs)}")
    
    # 5. Load existing active jobs
    existing_active_jobs = load_active_jobs()
    print(f"Loaded {len(existing_active_jobs)} existing active jobs from state.")
    
    # 6. Merge newly crawled senior jobs with existing active jobs
    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    current_year = today.year
    
    active_jobs_dict = {job["id"]: job for job in existing_active_jobs}
    
    # Clear "is_new" flag on existing jobs
    for job in active_jobs_dict.values():
        job["is_new"] = False
        # Initialize scraped_this_run as False, we will mark True if seen in this crawl
        job["scraped_this_run"] = False
        
    for job in new_senior_jobs:
        job_id = job["id"]
        if job_id in active_jobs_dict:
            # Update info but keep first_seen and update keywords, links, etc.
            existing_job = active_jobs_dict[job_id]
            existing_job.update({
                "title": job["title"],
                "company": job["company"],
                "link": job["link"],
                "links": job.get("links", {job["site_name"]: job["link"]}),
                "date": job["date"],
                "career": job["career"],
                "site_name": job["site_name"],
                "keyword": job["keyword"]
            })
            existing_job["scraped_this_run"] = True
        else:
            # Brand new senior job
            job["first_seen"] = today_str
            job["is_new"] = True
            job["scraped_this_run"] = True
            active_jobs_dict[job_id] = job
            print(f"  [New Senior Job Added] {job['company']} - {job['title']} (Career: {job['career']})")

    # 7. Expiry check and D-Day calculation
    filtered_active_jobs = []
    for job_id, job in active_jobs_dict.items():
        deadline = parse_deadline_date(job["date"], current_year)
        
        expired = False
        if deadline is not None:
            expired = today > deadline
        else:
            # Indefinite deadline (e.g. 상시채용)
            scraped_this_run = job.get("scraped_this_run", False)
            if scraped_this_run:
                expired = False
            else:
                try:
                    first_seen_date = datetime.datetime.strptime(job["first_seen"], "%Y-%m-%d").date()
                except (ValueError, KeyError):
                    first_seen_date = today
                    job["first_seen"] = today_str
                # Expire after 30 days if it fell off the first page and is indefinite
                expired = today > first_seen_date + datetime.timedelta(days=30)
                
        if expired:
            print(f"  [Expired/Removed] {job['company']} - {job['title']} (Deadline: {job['date']}, First Seen: {job.get('first_seen', today_str)})")
        else:
            # Calculate days left
            if deadline is not None:
                days_left = (deadline - today).days
                job["days_left"] = days_left
            else:
                job["days_left"] = None
                
            # Clean temporary keys
            job.pop("scraped_this_run", None)
            filtered_active_jobs.append(job)
            
    # Sort: New jobs first, then by days_left (ascending, putting None at the end)
    def sort_key(j):
        is_new_val = 0 if j.get("is_new") else 1
        dl = j.get("days_left")
        dl_val = dl if dl is not None else 999999
        return (is_new_val, dl_val, j["company"])
        
    filtered_active_jobs.sort(key=sort_key)
    
    # Save active jobs back to file
    save_active_jobs(filtered_active_jobs)
    print(f"Total active senior jobs remaining: {len(filtered_active_jobs)}")
    
    # 8. Notify
    notifier = JobNotifier()
    if notifier.is_configured():
        # Always send the email if there are active jobs
        # If no active jobs, send the status report that there are no matching jobs
        print(f"\nSending notification for {len(filtered_active_jobs)} active jobs...")
        success = notifier.send_notification(filtered_active_jobs)
        if success:
            print("Notification sent successfully.")
        else:
            print("Notification failed.")
    else:
        if filtered_active_jobs:
            print("\nSMTP is not configured. Print active job listings to console instead:")
            for idx, job in enumerate(filtered_active_jobs, 1):
                new_str = "[NEW] " if job.get("is_new") else ""
                print(f"[{idx}] {new_str}{job['company']} - {job['title']}")
                if "links" in job and len(job["links"]) > 1:
                    print("    Links:")
                    for site, link in job["links"].items():
                        print(f"      - {site}: {link}")
                else:
                    print(f"    Link: {job['link']}")
                print(f"    Date: {job['date']} | Career: {job['career']} | Site: {job['site_name']} | Keywords: {job['keyword']}")
        else:
            print("\nNo active job listings found and SMTP is not configured. Notification skipped.")
        
    print("\n=== Process Completed ===")

if __name__ == "__main__":
    main()
