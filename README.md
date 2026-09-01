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

**Phase 0 of 8 complete — foundation only.** The component directories are placeholders; no application code exists yet. The setup instructions below describe the intended workflow and will not run until the phases noted beside them are done.

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Repository foundation | ✅ Done |
| 1 | Django skeleton + authentication | ⬜ Next |
| 2 | Academic catalogue | ⬜ |
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

## Web application — `django/` *(available from Phase 1)*

```bash
cd django

# One-time setup
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Database and demo data
python manage.py migrate
python manage.py seed_demo_data      # Phase 2 onward
python manage.py createsuperuser

# Run
python manage.py runserver
```

The app is then served at <http://127.0.0.1:8000/>, with the Django admin at `/admin/`.

Unit tests:

```bash
python manage.py test                        # all
python manage.py test registration           # rule engine only
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
