import json
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup

class JobScraper:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = self.load_config()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

    def load_config(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config file {self.config_path}: {e}")
            raise

    def get_clean_id(self, link, site_name):
        import urllib.parse as urlparse
        try:
            parsed = urlparse.urlparse(link)
            base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            params = urlparse.parse_qs(parsed.query)
            
            if "사람인" in site_name or "Saramin" in site_name:
                rec_idx = params.get("rec_idx", [""])[0]
                if rec_idx:
                    return f"{base_url}?rec_idx={rec_idx}"
            elif "인크루트" in site_name or "Incruit" in site_name:
                job = params.get("job", [""])[0]
                if job:
                    return f"{base_url}?job={job}"
            return base_url
        except Exception as e:
            print(f"Error parsing clean ID for {link}: {e}")
            return link.split("?")[0]

    def scrape_site_keyword(self, site, keyword):
        jobs = []
        encoded_keyword = urllib.parse.quote(keyword)
        url = site["search_url"].format(keyword=encoded_keyword)
        print(f"[{site['name']}] Scraping keyword '{keyword}'... URL: {url}")

        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            if response.status_code != 200:
                print(f"[{site['name']}] Error: HTTP status code {response.status_code}")
                return jobs

            if "인크루트" in site["name"] or "Incruit" in site["name"]:
                response.encoding = 'euc-kr'
            else:
                response.encoding = 'utf-8'  # Force UTF-8 encoding for Korean sites
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select(site["item_selector"])
            print(f"[{site['name']}] Found {len(items)} items matching selector '{site['item_selector']}'")

            for item in items:
                # 1. Parse Title & Link
                title_el = None
                for sel in site["title_selector"].split(","):
                    title_el = item.select_one(sel.strip())
                    if title_el:
                        break
                
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                link = title_el.get("href", "")
                if not link:
                    continue

                # Ensure absolute URL
                if link.startswith("/"):
                    link = site["base_url"] + link
                elif not link.startswith("http"):
                    link = site["base_url"] + "/" + link

                # 2. Parse Company
                company_el = None
                for sel in site["company_selector"].split(","):
                    company_el = item.select_one(sel.strip())
                    if company_el:
                        break
                
                company = company_el.get_text(strip=True) if company_el else "회사명 미상"

                # 3. Parse Date
                date_el = None
                for sel in site["date_selector"].split(","):
                    date_el = item.select_one(sel.strip())
                    if date_el:
                        break
                
                date = date_el.get_text(strip=True) if date_el else "상세 정보 참조"
                date = " ".join(date.split())  # Clean whitespaces
                if not date or date.lower() == "n/a":
                    date = "상세 정보 참조"

                # 4. Parse Career/Experience Info
                career = "경력 정보 미상"
                if "사람인" in site["name"] or "Saramin" in site["name"]:
                    cond_el = item.select_one("div.job_condition")
                    if cond_el:
                        for sub_el in cond_el.find_all(True):
                            text = sub_el.get_text(strip=True)
                            if "경력" in text or "신입" in text:
                                career = text
                                break
                        if career == "경력 정보 미상":
                            career = cond_el.get_text(separator=" | ", strip=True)
                elif "잡코리아" in site["name"] or "JobKorea" in site["name"]:
                    for span in item.find_all("span"):
                        text = span.get_text(strip=True)
                        if "경력" in text or "신입" in text:
                            if not any(x in text for x in ["스크랩", "관심기업", "My"]):
                                career = text
                                break
                elif "인크루트" in site["name"] or "Incruit" in site["name"]:
                    for span in item.select("div.cell_mid div.cl_md span"):
                        text = span.get_text(strip=True)
                        if "경력" in text or "신입" in text:
                            career = text
                            break

                # Filter out jobs that don't match any keyword in the title or company to ensure relevancy
                title_lower = title.lower()
                company_lower = company.lower()
                matched_keywords = [
                    kw for kw in self.config["keywords"]
                    if kw.lower() in title_lower or kw.lower() in company_lower
                ]

                # We will keep all results but flag the matched keywords
                kw_match_str = ", ".join(matched_keywords) if matched_keywords else keyword

                jobs.append({
                    "id": self.get_clean_id(link, site["name"]),
                    "title": title,
                    "company": company,
                    "link": link,
                    "date": date,
                    "career": career,
                    "site_name": site["name"],
                    "keyword": kw_match_str
                })
        except Exception as e:
            print(f"[{site['name']}] Exception occurred while scraping '{keyword}': {e}")
        
        return jobs

    def scrape_all(self):
        all_jobs = {}
        for site in self.config["sites"]:
            for keyword in self.config["keywords"]:
                jobs = self.scrape_site_keyword(site, keyword)
                for job in jobs:
                    job_id = job["id"]
                    if job_id not in all_jobs:
                        all_jobs[job_id] = job
                    else:
                        # Append keyword if found under multiple searches
                        existing = all_jobs[job_id]
                        existing_kws = [k.strip() for k in existing["keyword"].split(",")]
                        new_kws = [k.strip() for k in job["keyword"].split(",")]
                        combined_kws = list(set(existing_kws + new_kws))
                        existing["keyword"] = ", ".join(combined_kws)
                
                time.sleep(2.0)  # Polite delay
        
        return list(all_jobs.values())

if __name__ == "__main__":
    scraper = JobScraper()
    # Simple test for the first keyword on the first site
    if scraper.config["sites"] and scraper.config["keywords"]:
        test_site = scraper.config["sites"][0]
        test_keyword = scraper.config["keywords"][0]
        results = scraper.scrape_site_keyword(test_site, test_keyword)
        print(f"\nTest scraped {len(results)} jobs.")
        for r in results[:3]:
            print(f"- {r['company']} | {r['title']} | {r['date']} | {r['link']}")
