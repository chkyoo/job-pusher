import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv

# Load local .env file if it exists
load_dotenv()

class JobNotifier:
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        try:
            self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        except ValueError:
            self.smtp_port = 587
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.recipient_email = os.getenv("RECIPIENT_EMAIL")

    def is_configured(self):
        return bool(self.smtp_user and self.smtp_password and self.recipient_email)

    def build_html_content(self, jobs):
        date_str = datetime.now().strftime("%Y년 %m월 %d일")
        
        # Build job cards HTML
        cards_html = ""
        for job in jobs:
            # Create pill tags for keywords
            keywords = [kw.strip() for kw in job["keyword"].split(",") if kw.strip()]
            keywords_html = "".join([
                f'<span style="display: inline-block; background-color: #f0f4ff; color: #3b82f6; font-size: 11px; font-weight: 600; padding: 3px 8px; margin-right: 5px; margin-bottom: 5px; border-radius: 9999px; border: 1px solid #dbeafe;">#{kw}</span>'
                for kw in keywords
            ])

            # Build site badges dynamically (in case of merged jobs)
            site_badges = []
            for s in job["site_name"].split(","):
                s = s.strip()
                site_tag_color = "#e0f2fe" if "사람인" in s else "#fef3c7"
                site_text_color = "#0369a1" if "사람인" in s else "#b45309"
                site_badges.append(f'<span style="font-size: 11px; font-weight: 500; background-color: {site_tag_color}; color: {site_text_color}; padding: 2px 8px; border-radius: 6px; margin-left: 4px;">{s}</span>')
            sites_html = "".join(site_badges)

            # Build action buttons (multiple buttons if job was found on multiple sites)
            buttons_html = ""
            if "links" in job and len(job["links"]) > 1:
                for site_name, link in job["links"].items():
                    buttons_html += f'<a href="{link}" target="_blank" style="display: inline-block; background-color: #4f46e5; color: #ffffff; text-decoration: none; font-size: 11px; font-weight: 600; padding: 6px 12px; border-radius: 6px; margin-left: 6px; box-shadow: 0 1px 2px rgba(79, 70, 229, 0.15);">{site_name}</a>'
            else:
                buttons_html = f'<a href="{job["link"]}" target="_blank" style="display: inline-block; background-color: #4f46e5; color: #ffffff; text-decoration: none; font-size: 12px; font-weight: 600; padding: 6px 14px; border-radius: 6px; box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2);">공고 상세보기</a>'

            cards_html += f"""
            <div style="background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02); transition: transform 0.2s ease;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div style="display: flex; align-items: center;">
                        <span style="font-size: 13px; font-weight: bold; color: #4b5563;">{job['company']}</span>
                        <span style="font-size: 11px; font-weight: 600; background-color: #f3f4f6; color: #4b5563; padding: 2px 6px; border-radius: 4px; margin-left: 8px;">{job['career']}</span>
                    </div>
                    <div>{sites_html}</div>
                </div>
                <h3 style="font-size: 16px; font-weight: 700; color: #1f2937; margin: 0 0 10px 0; line-height: 1.4;">{job['title']}</h3>
                <div style="margin-bottom: 12px;">{keywords_html}</div>
                <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #f3f4f6; padding-top: 12px; margin-top: 12px;">
                    <span style="font-size: 12px; color: #9ca3af;">등록일: {job['date']}</span>
                    <div style="display: flex; align-items: center;">
                        {buttons_html}
                    </div>
                </div>
            </div>
            """

        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>일자리 정보 푸시 알림</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f9fafb; margin: 0; padding: 0;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); border-radius: 16px 16px 0 0; padding: 35px 25px; text-align: center; color: #ffffff; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
                    <h1 style="font-size: 24px; font-weight: 800; margin: 0 0 8px 0; letter-spacing: -0.5px;">📋 맞춤형 신규 채용 정보</h1>
                    <p style="font-size: 14px; margin: 0; opacity: 0.9; font-weight: 500;">{date_str} 기준 새롭게 등록된 공고 ({len(jobs)}건)</p>
                </div>
                
                <!-- Content Area -->
                <div style="background-color: #ffffff; border-radius: 0 0 16px 16px; padding: 25px 20px; border: 1px solid #e5e7eb; border-top: none;">
                    {cards_html}
                    
                    <!-- Footer Info -->
                    <div style="text-align: center; margin-top: 25px; padding-top: 15px; border-top: 1px solid #f3f4f6; color: #9ca3af; font-size: 11px; line-height: 1.6;">
                        본 메일은 설정된 키워드(OLED, 디스플레이 등)를 기반으로 자동 발송된 채용 정보 알림입니다.<br>
                        GitHub Actions 스케줄러에 의해 매일 1회 실행됩니다.
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return html_template

    def send_notification(self, jobs):
        if not jobs:
            print("No new jobs to notify.")
            return False

        if not self.is_configured():
            print("SMTP configuration is incomplete. Skip sending email.")
            print("Please set SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, and RECIPIENT_EMAIL environment variables.")
            return False

        date_str = datetime.now().strftime("%Y-%m-%d")
        subject = f"[일자리 정보] {date_str} 신규 채용 공고 안내 ({len(jobs)}건)"
        html_content = self.build_html_content(jobs)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.smtp_user
        msg["To"] = self.recipient_email
        msg.attach(MIMEText(html_content, "html"))

        try:
            print(f"Connecting to SMTP server {self.smtp_server}:{self.smtp_port}...")
            # Use SSL or TLS based on Port
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
                server.starttls()
            
            server.login(self.smtp_user, self.smtp_password)
            print("SMTP login successful. Sending email...")
            server.sendmail(self.smtp_user, self.recipient_email, msg.as_string())
            server.quit()
            print("Email sent successfully!")
            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False

if __name__ == "__main__":
    # Test layout without sending
    notifier = JobNotifier()
    sample_jobs = [
        {
            "company": "LG디스플레이",
            "title": "OLED 패널 공정 및 소자 개발 엔지니어 채용",
            "link": "https://www.saramin.co.kr/zf_user/search/recruit?searchword=OLED",
            "date": "오늘 등록",
            "site_name": "사람인 (Saramin)",
            "keyword": "OLED, 디스플레이"
        },
        {
            "company": "삼성디스플레이",
            "title": "마이크로 디스플레이(Micro-OLED) 개발 인력 특별 채용",
            "link": "https://www.jobkorea.co.kr/Search/?stext=OLED",
            "date": "어제 등록",
            "site_name": "잡코리아 (JobKorea)",
            "keyword": "micro oled, 디스플레이, OLED"
        }
    ]
    html = notifier.build_html_content(sample_jobs)
    print("HTML build test successful. Length:", len(html))
