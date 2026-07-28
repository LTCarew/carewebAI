# CareWeb

> **AI-assisted caregiver-client matching registry for Independent Living Centers**

CareWeb is a full-stack Django web application that automates the caregiver discovery, placement, and stability monitoring workflow for home-care organizations. It uses GPT-4o to score compatibility between caregivers and clients, tracks placement health over time via a **Stability Module**, and gives org administrators a single dashboard to manage their entire care workforce.

---

## Table of Contents

1. [App Description](#app-description)
2. [Tech Stack](#tech-stack)
3. [Features](#features)
4. [Project Structure](#project-structure)
5. [How to Install](#how-to-install)
6. [How to Seed the Database](#how-to-seed-the-database)
7. [Running the Development Server](#running-the-development-server)
8. [Running Unit Tests](#running-unit-tests)
9. [Running UI (Selenium) Tests](#running-ui-selenium-tests)
10. [Docker](#docker)
11. [Environment Variables](#environment-variables)
12. [Deployment](#deployment)
13. [Contributing](#contributing)

---

## App Description

CareWeb bridges the gap between caregivers seeking employment and clients who need care — within the context of an Independent Living Center (ILC) or similar nonprofit organization.

**The core workflow:**

```
Caregiver applies ──► Org reviews ──► AI matches caregiver ↔ client
                                                │
                                                ▼
                             Org monitors match stability over time
                                                │
                                                ▼
                             Flag matches for stabilization review
```

The platform is designed for organizations that currently manage their Personal Care Coordination and Stabilization workflows in spreadsheets or paper files. CareWeb replaces that with a structured, AI-enhanced digital registry with full audit trails.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.13 · Django 4.x |
| **Database** | PostgreSQL (production) · SQLite in-memory (tests) |
| **AI / LLM** | OpenAI GPT-4o via `openai` Python SDK |
| **AI Fallback** | Local weighted heuristic scorer (no API required) |
| **Frontend** | Django templates · Bulma CSS · Vanilla JS (multi-step wizard) |
| **Auth** | Django session auth · Custom `UserProfile` extension |
| **UI Testing** | Selenium 4.33 · headless Chrome · Selenium Manager |
| **Containerization** | Docker (Python 3.13 slim image) |
| **Infrastructure** | Google Cloud Platform (Cloud Run + Cloud SQL) |
| **IaC** | Terraform |
| **CI/CD** | GitHub Actions (planned) |

---

## Features

### 🧑‍⚕️ Caregiver Management
- Self-service **6-step application wizard** (no page reloads, JS-driven)
- Certification level, languages, specializations, attendant-care programs
- Weekly schedule with recurring availability slots
- Geographic availability radius
- Desired hours per week

### 👤 Client Management
- Self-service **6-step application wizard** matching the caregiver wizard
- ADL care needs, preferred language, schedule preferences
- Geographic location-based filtering

### 🤖 AI-Assisted Matching
- GPT-4o compatibility scoring (0–100) with natural-language explanation
- Automatic fallback to local weighted heuristic when OpenAI is unavailable
- Match tags: language match, availability overlap, certification match, geography, etc.
- Staff-accessible AI match form to initiate new matches

### 📊 Organization Dashboard
- Unified dashboard for org admins and staff
- Paginated lists of active caregivers and clients
- Active matches table with AI score badges and **Stability column**
- One-click access to stability detail pages

### 🔁 Match Stability Module *(feature/stability)*
- `compute_stability_status(match)` aggregates session rating history
- Status levels: **Not Yet Rated** · **Stable** · **At Risk** · **Critical**
- Per-match stability detail page with rating history timeline
- **Flag for Stabilization Review** / **Remove Flag** staff actions with timestamp
- Color-coded Bulma CSS badges in the dashboard

### 🔐 Authentication & Roles
- Custom login with "account pending approval" message for inactive users
- Roles: `org_admin` · `org_staff` · `caregiver` · `client`
- Email-invite onboarding for staff members
- Multi-organization support (caregiver/client can belong to multiple orgs)

### 🧪 Comprehensive Test Suite
- **232 Django unit tests** across all modules
- **27 Selenium browser-level smoke tests** (headless Chrome, no manual driver install)
- **Total: 259 tests, 100% passing**

---

## Project Structure

```
carewebAi/
├── caregiver_registry/               # Django project root
│   ├── accounts/                     # User model, UserProfile, auth views
│   │   └── tests.py                  # 41 unit tests
│   ├── config/                       # Django settings
│   │   ├── settings.py               # Base settings (env-var driven)
│   │   └── test_settings.py          # In-memory SQLite, mocked OpenAI
│   ├── matching/                     # AI match engine + Stability module
│   │   ├── models.py                 # Match, MatchTag
│   │   ├── stability.py              # compute_stability_status()
│   │   ├── views.py                  # Match views + stability detail
│   │   ├── tests.py                  # 62 unit tests
│   │   ├── tests_views.py            # 40 view tests
│   │   └── tests_stability.py        # 90 stability unit tests
│   ├── organizations/                # Organization, StaffInvite
│   │   └── tests.py
│   ├── registry/                     # Caregiver & Client profiles, dashboards
│   │   ├── management/commands/
│   │   │   └── seed_cil_care.py      # Database seeder
│   │   ├── models.py
│   │   ├── views.py
│   │   └── tests.py                  # 89 unit tests
│   ├── static/css/
│   │   └── style.css                 # Custom Bulma overrides
│   ├── templates/                    # Django HTML templates
│   │   ├── base.html
│   │   ├── matching/
│   │   │   ├── _match_table.html     # Active matches partial
│   │   │   ├── _score_cell.html      # Score/stability badge partial
│   │   │   └── stability_detail.html # Per-match stability page
│   │   └── registry/
│   │       ├── caregiver_apply.html  # 6-step caregiver wizard
│   │       ├── client_apply.html     # 6-step client wizard
│   │       └── org_dashboard.html    # Main admin dashboard
│   ├── ui_tests/                     # Selenium smoke tests
│   │   └── test_ui_smoke.py          # 27 browser-level tests
│   ├── tests_helpers.py              # Shared test fixtures
│   ├── manage.py
│   └── requirements.txt
├── requirements-dev.txt              # Dev/test extras (selenium)
├── infra/
│   ├── DEPLOY.md                     # GCP deployment guide
│   └── terraform/                    # Cloud Run + Cloud SQL modules
└── README.md
```

---

## How to Install

### Prerequisites

- Python 3.11+ (project uses 3.13)
- PostgreSQL (for production) or SQLite (auto-used for tests)
- Google Chrome (for UI tests — any recent version)
- Git

### 1. Clone the repository

```bash
git clone https://github.com/LTCarew/carewebAI.git
cd carewebAI
```

### 2. Create and activate a virtual environment

**Windows (Git Bash / PowerShell):**
```bash
cd caregiver_registry
python -m venv venv
source venv/Scripts/activate        # Git Bash
# or
.\venv\Scripts\Activate.ps1         # PowerShell
```

**macOS / Linux:**
```bash
cd caregiver_registry
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

For development and UI testing also install:
```bash
pip install -r ../requirements-dev.txt
```

### 4. Configure environment variables

Copy the example file and fill in your values:
```bash
cp .env.example .env
```

Edit `.env`:
```env
SECRET_KEY=your-django-secret-key
DATABASE_URL=postgres://user:pass@localhost:5432/carewebai
OPENAI_API_KEY=sk-...
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

> **Note:** If `OPENAI_API_KEY` is not set or the API is unreachable, the app automatically falls back to local heuristic scoring — all features remain functional.

### 5. Apply database migrations

```bash
python manage.py migrate
```

### 6. Collect static files (production only)

```bash
python manage.py collectstatic --noinput
```

---

## How to Seed the Database

The `seed_cil_care` management command creates realistic sample data for a Center for Independent Living:

```bash
python manage.py seed_cil_care
```

**What gets created:**

| Item | Default count |
|------|--------------|
| Organization | 1 (`"Pacific Northwest CIL"`) |
| Org admin user | 1 (`admin` / `admin123`) |
| Caregiver profiles | 20 |
| Client profiles | 15 |
| AI-scored matches | 10 |

**Custom counts:**
```bash
python manage.py seed_cil_care \
    --caregivers 50 \
    --clients 30 \
    --matches 25
```

After seeding, log in at `http://localhost:8000/` with `admin` / `admin123`.

---

## Running the Development Server

```bash
cd caregiver_registry
python manage.py runserver
```

Open `http://localhost:8000/` in your browser.

---

## Running Unit Tests

All 232 unit tests run against an in-memory SQLite database — no external services required:

```bash
cd caregiver_registry

# Run all unit tests
python manage.py test accounts registry matching.tests \
    matching.tests_views matching.tests_stability \
    --settings=config.test_settings --verbosity=1

# Run a specific module
python manage.py test matching.tests_stability \
    --settings=config.test_settings --verbosity=2

# Run a specific test class
python manage.py test matching.tests_stability.StabilityComputeTest \
    --settings=config.test_settings --verbosity=2
```

**Expected result:**
```
Ran 232 tests in ~290s
OK
```

> The two `ChatGPT match scoring failed` log lines are expected — the test settings mock the OpenAI client and the local scorer is used as intended.

---

## Running UI (Selenium) Tests

The UI test suite drives a real headless Chrome browser against a live in-process Django server.

### Prerequisites

1. **Google Chrome** must be installed (version 90+)
   - Windows default path: `C:\Program Files\Google\Chrome\Application\chrome.exe`
   - macOS: `/Applications/Google Chrome.app/...`

2. **Selenium in venv:**
   ```bash
   # Windows
   ./venv/Scripts/pip install "selenium==4.33.0"
   # macOS/Linux
   ./venv/bin/pip install "selenium==4.33.0"
   ```

   > **ChromeDriver is downloaded automatically** by Selenium Manager — no manual installation needed.

### Run UI tests

```bash
cd caregiver_registry

# Windows
./venv/Scripts/python.exe manage.py test ui_tests \
    --settings=config.test_settings --verbosity=2

# macOS/Linux
./venv/bin/python manage.py test ui_tests \
    --settings=config.test_settings --verbosity=2
```

**Expected result:**
```
Ran 27 tests in ~85s
OK
```

### Run everything (unit + UI)

```bash
./venv/Scripts/python.exe manage.py test \
    accounts registry matching.tests matching.tests_views \
    matching.tests_stability ui_tests \
    --settings=config.test_settings --verbosity=1
```

**Expected result:**
```
Ran 259 tests
OK
```

### UI Test Coverage Summary

| Test Class | Tests | Covers |
|-----------|-------|--------|
| `HomePageTest` | 2 | Home page, navbar |
| `LoginPageTest` | 3 | Login form fields and rendering |
| `SuccessfulLoginTest` | 1 | Login → dashboard redirect |
| `FailedLoginTest` | 1 | Bad credentials → error |
| `InactiveUserLoginTest` | 1 | Inactive account → approval message |
| `CaregiverApplyFormTest` | 3 | Form, fields, multi-step wizard |
| `ClientApplyFormTest` | 2 | Form, required fields |
| `OrgDashboardUITest` | 4 | Dashboard, Stability column, badges |
| `StabilityDetailUITest` | 7 | Detail page, flag/unflag, auth |
| `CaregiverDashboardUITest` | 1 | Caregiver dashboard |
| `ClientDashboardUITest` | 1 | Client dashboard |
| `AIMatchFormUITest` | 1 | AI match form access |

---

## Docker

### Build the image

```bash
cd caregiver_registry
docker build -t carewebai:latest .
```

### Run with Docker

```bash
docker run -p 8000:8000 \
  -e SECRET_KEY=your-secret-key \
  -e DATABASE_URL=postgres://user:pass@host:5432/db \
  -e OPENAI_API_KEY=sk-... \
  carewebai:latest
```

### Docker Compose (with PostgreSQL)

```yaml
# docker-compose.yml
version: "3.9"
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: carewebai
      POSTGRES_USER: carewebai
      POSTGRES_PASSWORD: secret
  web:
    build: ./caregiver_registry
    command: python manage.py runserver 0.0.0.0:8000
    ports:
      - "8000:8000"
    depends_on:
      - db
    environment:
      DATABASE_URL: postgres://carewebai:secret@db:5432/carewebai
      SECRET_KEY: your-secret-key
      OPENAI_API_KEY: sk-...
      DEBUG: "True"
```

```bash
docker compose up
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | Django secret key (generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`) |
| `DATABASE_URL` | ✅ (prod) | PostgreSQL connection string. Omit for SQLite (dev only) |
| `OPENAI_API_KEY` | ⚠️ Optional | GPT-4o API key. If missing/unreachable, local heuristic scoring is used automatically |
| `DEBUG` | ⚠️ | `True` for development, `False` for production |
| `ALLOWED_HOSTS` | ✅ (prod) | Comma-separated list of allowed hostnames |

---

## Deployment

See [`infra/DEPLOY.md`](infra/DEPLOY.md) for the full GCP Cloud Run deployment guide.

**Quick summary:**
1. Build and push Docker image to Google Artifact Registry
2. Apply Terraform to provision Cloud SQL (PostgreSQL) + Cloud Run service + VPC connector
3. Set environment variables as Cloud Run secrets
4. Run migrations via Cloud Run Jobs or a one-off task container

```bash
# From infra/terraform/
terraform init
terraform plan
terraform apply
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run the full test suite and ensure all 259 tests pass
5. Open a pull request

**Code style:** PEP 8 enforced via `flake8`. Run `flake8 .` before committing.

**Test requirements:** All new features must include both unit tests and, for any new page/view, a Selenium UI smoke test in `ui_tests/test_ui_smoke.py`.

---

## License

MIT License — see `LICENSE` for details.

---

*CareWeb — Empowering Independent Living Centers with intelligent caregiver matching.*
