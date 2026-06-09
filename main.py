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
    print(f"Total raw jobs crawled: {len(all_jobs)}")
    
    # 3. Deduplicate listings across multiple search queries and sites
    deduped_jobs = deduplicate_jobs(all_jobs)
    print(f"Deduplicated jobs: {len(deduped_jobs)}")
    
    # 4. Filter out junior/mid-level jobs (keep only senior/executive levels)
    senior_jobs = []
    for job in deduped_jobs:
        if not is_junior_or_mid_level(job["career"], job["title"]):
            senior_jobs.append(job)
        else:
            print(f"  [Filtered Out] {job['company']} - {job['title']} (Career: {job['career']})")
    print(f"Filtered (Senior/Executive only) jobs: {len(senior_jobs)}")
    
    # 5. Load previously sent jobs
    sent_jobs = load_sent_jobs()
    print(f"Loaded {len(sent_jobs)} historical job links from state.")
    
    # 6. Filter out already sent jobs
    new_jobs = []
    for job in senior_jobs:
        # Check if any of the links associated with this job was already sent
        already_sent = False
        if "links" in job:
            for link in job["links"].values():
                link_id = link.split("?")[0]
                if link_id in sent_jobs:
                    already_sent = True
                    break
        else:
            if job["id"] in sent_jobs:
                already_sent = True
                
        if not already_sent:
            new_jobs.append(job)
            
    print(f"Filtered down to {len(new_jobs)} NEW jobs.")
    
    # 7. Notify (now always sending email if SMTP is configured)
    notifier = JobNotifier()
    if notifier.is_configured():
        if new_jobs:
            print(f"\nSending notification for {len(new_jobs)} new jobs...")
            success = notifier.send_notification(new_jobs)
            if success:
                # Add all associated links to history and save
                for job in new_jobs:
                    if "links" in job:
                        for link in job["links"].values():
                            sent_jobs.add(link.split("?")[0])
                    else:
                        sent_jobs.add(job["id"])
                save_sent_jobs(sent_jobs)
            else:
                print("Notification failed. State has NOT been updated.")
        else:
            print("\nNo new job listings found. Sending 'no new jobs' status notification...")
            success = notifier.send_notification([])
            if success:
                print("'No new jobs' notification sent successfully.")
            else:
                print("Failed to send 'no new jobs' notification.")
    else:
        if new_jobs:
            print("\nSMTP is not configured. Print new job listings to console instead:")
            for idx, job in enumerate(new_jobs, 1):
                print(f"[{idx}] {job['company']} - {job['title']}")
                if "links" in job and len(job["links"]) > 1:
                    print("    Links:")
                    for site, link in job["links"].items():
                        print(f"      - {site}: {link}")
                else:
                    print(f"    Link: {job['link']}")
                print(f"    Date: {job['date']} | Career: {job['career']} | Site: {job['site_name']} | Keywords: {job['keyword']}")
        else:
            print("\nNo new job listings found and SMTP is not configured. Notification skipped.")
        
    print("\n=== Process Completed ===")

if __name__ == "__main__":
    main()
