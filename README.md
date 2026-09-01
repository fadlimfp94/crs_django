# Course Registration System (CRS)

A course registration platform for students, lecturers, and academic administrators.

Students browse a course catalogue and register for sections; the server enforces prerequisites, credit limits, seat capacity, timetable clashes, and registration windows, and manages waitlists. Lecturers view rosters and submit grades. Administrators manage terms, courses, sections, and registration windows.

| Component | Technology | Directory |
|---|---|---|
| Web application + REST API | Django 5.2 LTS · SQLite | [`django/`](django/) |
| End-to-end tests | Playwright · TypeScript | [`playwright/`](playwright/) |
| Mobile apps (Android + iOS) | Compose Multiplatform · Kotlin | [`cmp/`](cmp/) |

See **[PLAN.md](PLAN.md)** for the full development plan, data model, and phased roadmap.

---

## Project status

**Phase 1 of 8 complete.** The Django app runs: users can sign in and each role reaches its own dashboard. There is no course catalogue or registration yet. The `playwright/` and `cmp/` directories are still placeholders, so their instructions below will not run until the phases noted beside them are done.

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Repository foundation | ✅ Done |
| 1 | Django skeleton + authentication | ✅ Done |
| 2 | Academic catalogue | ⬜ Next |
| 3 | Registration rule engine | ⬜ |
| 4 | Web UI | ⬜ |
| 5 | REST API | ⬜ |
| 6 | Playwright E2E suite | ⬜ |
| 7 | Compose Multiplatform mobile apps | ⬜ |
| 8 | CI, hardening, documentation | ⬜ |

---

## Prerequisites

| Tool | Required version | This machine |
|---|---|---|
| Python | ≥ 3.10 (3.13 recommended) | ✅ 3.13.1 (`/opt/homebrew/bin/python3.13`) |
| Node.js | ≥ 20 | ✅ 24.11.1 |
| JDK | 17 or 21 | ✅ 21.0.3 LTS |
| Android Studio | Latest stable (Phase 7) | ⬜ Not verified |
| Xcode | Latest stable, iOS target only (Phase 7) | ⬜ Not verified |

> The macOS system Python (3.9.6) is **too old** for Django 5.2. Always use `python3.13` explicitly when creating the virtual environment.

---

## Web application — `django/`

```bash
cd django

# One-time setup
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Database and accounts
python manage.py migrate
python manage.py create_test_users     # one account per role, for local use
python manage.py createsuperuser       # or your own admin account

# Run
python manage.py runserver
```

The app is served at <http://127.0.0.1:8000/>, with the Django admin at `/admin/`.

### Test accounts

`create_test_users` is idempotent and creates these, all with the password `crs-dev-password`. It refuses to run when `DEBUG` is off unless you pass `--force`.

| Sign-in | Role | Lands on |
|---|---|---|
| `2026001` | Student | `/accounts/student/` |
| `L-1001` | Lecturer | `/accounts/lecturer/` |
| `admin` | Administrator | `/accounts/administrator/` (and `/admin/`) |

### Settings modules

Selected with `DJANGO_SETTINGS_MODULE`; `manage.py` defaults to `dev`.

| Module | Used for |
|---|---|
| `config.settings.dev` | Local development — `DEBUG=True`, relaxed password rules |
| `config.settings.test` | Automated tests — in-memory database, fast password hasher |
| `config.settings.prod` | Deployment — requires `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`, and refuses to start without them |

### Tests, linting, formatting

```bash
DJANGO_SETTINGS_MODULE=config.settings.test python manage.py test
DJANGO_SETTINGS_MODULE=config.settings.test python manage.py test accounts

ruff check .          # lint  (--fix to autofix)
black .               # format
```

Before deploying, verify the production configuration:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod \
DJANGO_SECRET_KEY=... DJANGO_ALLOWED_HOSTS=crs.example.edu \
  python manage.py check --deploy
```

## End-to-end tests — `playwright/` *(available from Phase 6)*

```bash
cd playwright
npm install
npx playwright install --with-deps

npx playwright test                  # headless, all suites
npx playwright test --headed         # watch it run
npx playwright test --ui             # interactive runner
npx playwright show-report           # last HTML report
```

The suite starts and stops its own Django server against a disposable, freshly seeded SQLite database — no manual setup, and it never touches your development database.

## Mobile apps — `cmp/` *(available from Phase 7)*

```bash
cd cmp

./gradlew :composeApp:assembleDebug              # Android APK
./gradlew :composeApp:installDebug               # to a running emulator/device
open iosApp/iosApp.xcodeproj                     # then Run in Xcode for iOS
```

Both targets expect a reachable CRS API. Point them at your local server via the base URL in the shared Ktor client configuration — note that an Android emulator reaches the host machine at `10.0.2.2`, not `localhost`.

---

## Repository layout

```
CourseRegistrationSystem/
├── PLAN.md            Development plan and roadmap
├── README.md
├── django/            Web app + REST API
├── playwright/        End-to-end test suite
└── cmp/               Compose Multiplatform mobile apps
```

## Conventions

- **Business rules live in `django/registration/services.py`** — never in views, serializers, or model `save()` methods. The web UI, the REST API, and the admin all call the same service functions so a rule cannot be enforced inconsistently in one place and skipped in another.
- Python is formatted with `black` and linted with `ruff`.
- Every registration rule (R1–R7 in [PLAN.md](PLAN.md#registration-rules-the-heart-of-the-system)) has unit tests covering both a passing and a failing case.
