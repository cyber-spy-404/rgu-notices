# 🏛️ Raiganj University Notice & SMTP Dispatcher

An automated, modern web application and SMTP dispatch system for **Raiganj University (রায়গঞ্জ বিশ্ববিদ্যালয়)** students.

The application automatically checks [raiganjuniversity.ac.in](https://raiganjuniversity.ac.in/) **everyday at 00:00 (midnight)** for new notices and announcements. If new notices are found, it dispatches an alert email to all enrolled student emails. If no new notices are found, it logs the check and automatically reschedules the next check for the next 00:00.

---

## ✨ Features

- **Automated Daily 00:00 Scheduler**:
  - Automatically triggers every night at `00:00:00 IST` via APScheduler.
  - Live countdown clock on the UI showing hours, minutes, and seconds until the next 00:00 run.
  - If new notices are found: generates responsive, branded HTML emails and dispatches them to students.
  - If no new notices are found: logs the event and reschedules for next 00:00.

- **Raiganj University Web Scraper**:
  - Live scraper targeting `https://raiganjuniversity.ac.in/Website/AllNotices` and the homepage.
  - Categorizes notices (Admissions, Examinations, Holidays, Tenders, Research & PhD, Academic Events).
  - Extracts notice titles, reference IDs, publication dates, and direct links to official documents and PDFs.
  - Differential change detection: only genuinely new notices trigger email alerts.
  - "Check Notices Now" button to execute manual scans anytime.

- **Student Email Management**:
  - Add individual students (Name, Email, Department, Roll No).
  - Bulk import via CSV or raw email list (paste format: `Name, email@domain.com, Department, RollNo` or simple emails).
  - Toggle student email subscription (Subscribed / Paused).
  - Instant live search & filtering.

- **Dual SMTP Architecture**:
  - **Built-in Local SMTP Server**: Runs on `127.0.0.1:1025` using `aiosmtpd`. Requires zero external configuration and captures all outgoing/incoming emails into an in-app viewer.
  - **In-App Local SMTP Inbox**: Review every dispatched email with an embedded HTML previewer.
  - **Custom / External SMTP Relay**: Switch to Gmail (App Password), Outlook, Amazon SES, Brevo, or custom university SMTP server with full TLS/SSL authentication.
  - **SMTP Diagnostic Tester**: Test connection handshake and send sample verification emails directly from the dashboard.

- **UI & Aesthetics**:
  - Glassmorphic dark university theme with glowing accents.
  - Real-time metrics dashboard, live execution logs console, and email mockup preview.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+ (Tested on Python 3.13)
- Required packages (already installed): `flask`, `requests`, `beautifulsoup4`, `apscheduler`, `aiosmtpd`

### 2. Run Application
Run via python:
```bash
python run.py
```
Or double-click:
```
start.bat
```

Open your browser to:
```
http://127.0.0.1:5000
```

---

## 📁 Project Structure

```
RGU SMTP/
├── app.py                  # Main Flask backend & REST API
├── run.py                  # Launcher script (browser auto-open & seed data)
├── start.bat               # Windows double-click startup batch script
├── scraper.py              # Notice scraper & differential change engine
├── scheduler_engine.py     # Background APScheduler (Daily 00:00:00 cron)
├── email_dispatcher.py     # Responsive HTML email builder & SMTP dispatch
├── local_smtp_server.py    # Built-in aiosmtpd local server & capture inbox
├── database.py             # SQLite data access layer
├── requirements.txt        # Dependencies
├── static/
│   ├── css/style.css       # Design system & dark glassmorphic styling
│   └── js/app.js           # Frontend logic & real-time polling
└── templates/
    └── index.html          # Web UI Dashboard
```
