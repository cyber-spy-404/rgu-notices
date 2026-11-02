# Contributing to Raiganj University Notice & SMTP Dispatcher

Thank you for your interest in contributing to the **Raiganj University (রায়গঞ্জ বিশ্ববিদ্যালয়) Notice & SMTP Dispatcher**! 

This open-source project helps ensure thousands of university students never miss important examination schedules, admission updates, holiday notices, and administrative announcements by automatically scraping, summarizing, and broadcasting them.

We welcome contributions from developers, students, and community members of all skill levels.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can You Contribute?](#how-can-you-contribute)
- [Local Development Setup](#local-development-setup)
- [Project Architecture & Directory Structure](#project-architecture--directory-structure)
- [Testing Guidelines](#testing-guidelines)
- [Git & Commit Conventions](#git--commit-conventions)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Security & Sensitive Data](#security--sensitive-data)
- [License](#license)

---

## Code of Conduct

We are committed to providing a friendly, safe, and welcoming environment for everyone. Please be respectful, constructive, and collaborative in all communications, issues, and pull requests.

---

## How Can You Contribute?

Here are several areas where you can help:

1. **Scraper Enhancements**: Improve resilience of `scraper.py` against university portal markup shifts, new file formats, or anti-scraping geoblocking.
2. **AI & Extraction Engine**: Enhance `notice_extractor.py` and `gemini_polisher.py` to extract event dates, application deadlines, and target audiences with higher accuracy.
3. **Frontend & UI**: Improve dashboard responsiveness, accessibility, dark mode aesthetics, and real-time metric indicators.
4. **Multi-Channel Dispatchers**: Add notification adapters (e.g. Telegram channel bot, WhatsApp Community alerts, Discord webhooks).
5. **Localization & Language**: Improve bilingual rendering (Bengali & English) for university announcements.
6. **Bug Fixes & Docs**: Fix reported issues, add unit tests, or clarify documentation.

---

## Local Development Setup

### 1. Prerequisites
- **Python**: 3.10+ (Tested on Python 3.11, 3.12, 3.13)
- **Git**: Installed and configured
- **Tesseract OCR** *(Optional for local image notice OCR)*:
  - Ubuntu/Debian: `sudo apt-get install tesseract-ocr`
  - Windows: Install from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki)

### 2. Fork and Clone
```bash
git clone https://github.com/<your-username>/rgu-notices.git
cd rgu-notices
```

### 3. Create a Virtual Environment
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env     # Linux / macOS
copy .env.example .env   # Windows CMD / PowerShell
```

Edit `.env` with your development settings:
- **Database**: Leave `DATABASE_URL` empty to use local SQLite (`data/rgu_smtp.db`), or provide a development PostgreSQL URI (e.g. from [Neon](https://neon.tech)).
- **SMTP**: Use a test Gmail account with an App Password or rely on the built-in local SMTP mock server running on port `2525`.

### 6. Run the Application
```bash
python run.py
```
Open your browser at `http://127.0.0.1:5000` to interact with the web dashboard.

---

## Project Architecture & Directory Structure

```text
rgu-notices/
├── app.py                 # Flask web application & REST API routes
├── run.py                 # Local launcher script
├── database.py            # Universal database layer (SQLite & Cloud PostgreSQL)
├── scraper.py             # Official portal web scraper & notice parser
├── notice_extractor.py    # Local parser extracting purpose, deadlines, audience
├── gemini_polisher.py     # Gemini AI & multimodal OCR summarizer
├── email_dispatcher.py    # RFC-compliant HTML email builder & SMTP sender
├── local_smtp_server.py   # In-app local SMTP mock server for safe testing
├── scheduler_engine.py    # In-process APScheduler (7:00 AM & 7:00 PM IST)
├── cron_task.py           # GitHub Actions twice-daily automated runner
├── setup_external_db.py   # CLI tool for PostgreSQL verification & migration
├── static/                # CSS styling, brand assets, and client-side JS
├── templates/             # Jinja2 dashboard templates
└── .github/workflows/     # CI/CD and automated twice-daily scan workflows
```

---

## Testing Guidelines

Before opening a pull request, verify that your changes do not break existing workflows:

### 1. Database Connection & Schema Test
```bash
python database.py
```
*Expected: Prints active database engine (SQLite or PostgreSQL) and initializes tables without error.*

### 2. Scraper Test
```bash
python scraper.py
```
*Expected: Successfully fetches and parses recent notices from the university portal.*

### 3. Safe Email Dispatch Verification
- **Do not send bulk test emails to the live Google Group!**
- Use the built-in mock SMTP server (`mode: local` in the UI or `127.0.0.1:2525`) to inspect rendered HTML emails in the in-app inbox (`/api/smtp/inbox`).
- Alternatively, test by dispatching to your personal email address.

---

## Git & Commit Conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/) for clear commit history:

- `feat:` A new feature or capability
- `fix:` A bug fix or patch
- `docs:` Documentation improvements
- `style:` Formatting, UI styles, or CSS tweaks (no code logic changes)
- `refactor:` Code restructuring without behavioral changes
- `perf:` Performance optimizations
- `test:` Adding or updating tests
- `chore:` Maintenance tasks, dependency updates, or CI workflow changes

**Example:**
```bash
git commit -m "feat(scraper): extract application submission deadlines from PDF notices"
git commit -m "fix(dispatcher): resolve STARTTLS timeout on high-latency relays"
```

---

## Submitting a Pull Request

1. **Create a Topic Branch**:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. **Make and Test Your Changes**.
3. **Commit Your Work**:
   ```bash
   git add .
   git commit -m "feat: description of changes"
   ```
4. **Push to Your Fork**:
   ```bash
   git push origin feature/my-new-feature
   ```
5. **Open a Pull Request**:
   - Go to the repository on GitHub and click **New Pull Request**.
   - Provide a clear title and description explaining what was changed and why.
   - Mention any related issues (e.g. `Fixes #12`).

---

## Security & Sensitive Data

> [!CAUTION]
> **NEVER commit secrets to Git!**
> - Do **not** commit `.env`, `.secret_key`, passwords, Gmail App Passwords, or Neon connection strings.
> - Ensure all sensitive values are listed in `.gitignore`.
> - If you accidentally commit a credential, invalidate/revoke it immediately.

---

## License

By contributing to this repository, you agree that your contributions will be licensed under the project's [MIT License](LICENSE.md).
