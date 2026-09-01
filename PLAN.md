# Course Registration System (CRS) — Development Plan

**Status:** Draft · **Created:** 2026-09-01

CRS is a course registration platform with three deliverables:

| Component | Technology | Location |
|---|---|---|
| Web application + REST API | Django 5.2 LTS, SQLite | `django/` |
| End-to-end test suite | Playwright (TypeScript) | `playwright/` |
| Mobile applications (later phase) | Compose Multiplatform (Android + iOS) | `cmp/` |

---

## 1. Scope

### In scope
- Student self-service registration: browse the course catalogue, add/drop course sections, view a personal timetable and enrollment history.
- Registration rule enforcement: prerequisites, credit limits, section capacity, timetable clashes, open/closed registration windows.
- Waitlisting with automatic promotion when a seat frees up.
- Lecturer views: assigned sections, class rosters, grade submission.
- Administrator functions: manage terms, courses, sections, and registration windows; override enrollments.
- REST API consumed by the mobile apps and exercised directly by tests.
- Automated E2E coverage of every critical user journey.
- Native Android and iOS clients sharing one Kotlin codebase.

### Out of scope (for this plan)
Tuition/billing and payments, transcript generation and GPA calculation beyond a stored per-course grade, timetable auto-scheduling/optimisation, degree audit and graduation checks, SSO/LDAP integration, and multi-institution tenancy. Each is a candidate follow-up once the core is stable.

---

## 2. Assumptions and decisions

These are the judgment calls made while writing this plan. Flag any you disagree with — several affect work as early as Phase 1.

1. **Django templates for the web UI, not a JavaScript SPA.** Server-rendered pages keep the stack small and Playwright tests straightforward. The REST API exists in parallel to serve mobile, not to back the web UI.
2. **Django REST Framework** for the API layer, with token authentication for mobile clients and session authentication for the web app.
3. **One custom user model with a `role` field** (`STUDENT` / `LECTURER` / `ADMIN`) plus separate profile models, rather than three user models. Simpler permission checks; one identity per person.
4. **Registration rules live in a service layer** (`registration/services.py`), not in views or model `save()` methods. Views, API, admin overrides, and tests all call the same functions, so a rule cannot be enforced inconsistently across entry points.
5. **SQLite for all environments**, as specified. See the concurrency risk in §8 — this is the main technical constraint on the design.
6. **Time-slot clash detection uses discrete meeting rows**, one per (day, start, end) pair, instead of a free-text schedule string. Required for reliable clash checks.
7. **Waitlist promotion runs synchronously** inside the drop transaction. No Celery, no broker, no extra moving parts. Revisit only if drops become slow.
8. **Playwright drives a dedicated test server** with a disposable SQLite file and a fixed seeded dataset, so runs are isolated and repeatable.
9. **Mobile apps are read-and-register clients.** All business rules stay server-side; the apps never re-implement rule checks, only display the server's verdict.
10. **Python 3.12** will be installed via Homebrew (see §3). The bundled 3.9.6 cannot run Django 5.2.

---

## 3. Environment prerequisites

Verified on this machine:

- ✅ Java 21 LTS — sufficient for Compose Multiplatform.
- ✅ Node.js v24.11.1 — sufficient for Playwright.
- ✅ **Python 3.13.1** at `/opt/homebrew/bin/python3.13` — already installed via Homebrew, no action needed. Django 5.2 LTS supports 3.10–3.13, so 3.13 is the right target. (Homebrew also has 3.14, which is outside Django 5.2's supported range; 3.9.6 is the macOS system Python and too old. Always create the virtualenv with `python3.13` explicitly.)
- Additional needs: **Xcode** with iOS simulators (Phase 7, iOS target only), **Android Studio** with an SDK and emulator (Phase 7).

---

## 4. Repository layout (target)

```
CourseRegistrationSystem/
├── PLAN.md
├── README.md
├── .gitignore
├── .github/workflows/ci.yml
├── django/
│   ├── manage.py
│   ├── requirements.txt              # pinned; requirements-dev.txt for tooling
│   ├── pyproject.toml                # ruff + black config
│   ├── db.sqlite3                    # git-ignored
│   ├── config/                       # project package
│   │   ├── settings/{base,dev,test,prod}.py
│   │   ├── urls.py, wsgi.py, asgi.py
│   ├── accounts/                     # custom user, profiles, auth views
│   ├── academics/                    # Department, Program, Course, Term, Section, Meeting
│   ├── registration/                 # Enrollment, Waitlist, rule engine, services
│   ├── api/                          # DRF serializers, viewsets, routers
│   ├── templates/                    # base.html + per-app templates
│   ├── static/
│   └── scripts/seed_demo_data.py     # management command wrapper
├── playwright/
│   ├── package.json
│   ├── playwright.config.ts
│   ├── tests/{auth,catalogue,registration,waitlist,lecturer,admin}/
│   ├── pages/                        # Page Object Models
│   ├── fixtures/                     # auth state, seeded-user constants
│   └── utils/django-server.ts        # spin up/tear down test server
└── cmp/
    ├── settings.gradle.kts
    ├── gradle/libs.versions.toml
    ├── composeApp/src/
    │   ├── commonMain/               # UI, ViewModels, Ktor client, models
    │   ├── androidMain/
    │   └── iosMain/
    └── iosApp/                       # Xcode project wrapper
```

---

## 5. Data model

Core entities and the relationships that matter for the rule engine:

```
User (AbstractUser + role)
 ├─1:1─ StudentProfile  (student_number, program→Program, enrollment_year, status)
 └─1:1─ LecturerProfile (staff_number, department→Department, title)

Department 1─* Program
Department 1─* Course

Course (code UNIQUE, title, description, credits, department)
 └─M:M─ prerequisites → Course  (self-referential, through PrerequisiteRule)

Term (code UNIQUE e.g. "2026-FALL", start_date, end_date,
      registration_opens_at, registration_closes_at, is_active,
      max_credits_per_student)

Section (course→Course, term→Term, section_code, lecturer→LecturerProfile,
         capacity, room, UNIQUE(course, term, section_code))
 └─1:*─ Meeting (day_of_week, start_time, end_time, room)

Enrollment (student→StudentProfile, section→Section,
            status: ENROLLED|WAITLISTED|DROPPED|COMPLETED,
            waitlist_position (nullable), grade (nullable),
            registered_at, dropped_at,
            UNIQUE(student, section))
```

Key constraints and indexes:
- `UNIQUE(student, section)` — a student cannot double-register for one section.
- `UNIQUE(student, section)` is **not** sufficient to prevent registering for two sections of the same course in one term; that is a rule-engine check (R2).
- Index `Enrollment(section, status)` for fast seat counting; `Enrollment(student, status)` for the student's timetable.
- `Section.capacity` is not decremented on a counter field — seats are counted from `Enrollment` rows inside a transaction, avoiding drift.

### Registration rules (the heart of the system)

Each rule is one function in `registration/services.py`, each with its own unit tests and its own distinct error message:

| ID | Rule | Check |
|---|---|---|
| R1 | Registration window open | `Term.registration_opens_at ≤ now ≤ registration_closes_at` |
| R2 | Not already enrolled | No active `Enrollment` for this course in this term |
| R3 | Prerequisites satisfied | Every prerequisite has a `COMPLETED` enrollment with a passing grade |
| R4 | Credit limit | Current term credits + new course credits ≤ `Term.max_credits_per_student` |
| R5 | No timetable clash | New section's `Meeting` rows do not overlap any enrolled section's meetings |
| R6 | Seat available | `ENROLLED` count < `capacity`; otherwise → waitlist |
| R7 | Student in good standing | `StudentProfile.status == ACTIVE` |

`register(student, section)` runs R1–R7 in order inside `transaction.atomic()` and returns either an `ENROLLED` result, a `WAITLISTED` result, or raises a `RegistrationError` carrying the failed rule ID and a human-readable message. `drop(student, section)` releases the seat and promotes the head of the waitlist in the same transaction.

---

## 6. Phases

Each phase ends in a working, demonstrable state. Phases 1–4 are strictly sequential; 5 and 6 can overlap once 4 lands; 7 needs 5 complete.

### Phase 0 — Foundation ✅ COMPLETE
Verify the Python toolchain. Create `.gitignore` (Python, Node, Gradle, Xcode, `db.sqlite3`, `.env`). Initialise the git repository (this directory is not yet one). Write a `README.md` with setup steps for all three components.

*Done when:* `git log` shows an initial commit and a Django-compatible Python is confirmed working.

### Phase 1 — Django skeleton and authentication
Create the project with split settings (`base`/`dev`/`test`/`prod`). Add the `accounts` app with the custom user model and both profile models — **the custom user model must land before the first `migrate`**, as swapping it later requires destroying the database. Build login, logout, and password-change views plus a role-aware base template and navigation. Register everything in Django admin. Configure `ruff` and `black`.

*Done when:* a superuser can log in, three test users (one per role) exist, and each lands on a role-appropriate placeholder dashboard.

### Phase 2 — Academic catalogue
Build the `academics` app: `Department`, `Program`, `Course`, `PrerequisiteRule`, `Term`, `Section`, `Meeting`. Rich admin with inlines (meetings inline on sections), list filters, and search. Add a `seed_demo_data` management command producing a realistic dataset: ~4 departments, ~30 courses with a prerequisite chain at least 3 levels deep, 2 terms (one open for registration, one closed), ~50 sections, and users of every role.

*Done when:* `python manage.py seed_demo_data` populates a browsable catalogue from a clean database, and the command is idempotent.

### Phase 3 — Registration engine
Implement R1–R7 and the `register` / `drop` / `promote_from_waitlist` services. Cover each rule with unit tests including boundary cases: registration window opening and closing to the second, a prerequisite passed vs. failed by one grade step, credit limit hit exactly vs. exceeded by one, meetings that touch end-to-start (10:00–11:00 and 11:00–12:00 must **not** clash) vs. genuinely overlap, last seat taken, and a concurrent double-registration attempt.

*Done when:* the rule test suite passes and every rule has at least one passing and one failing case. This phase carries the highest defect risk — do not move on with tests skipped.

### Phase 4 — Web UI
Student: catalogue browse with filters (department, term, credits, availability, free-text search), section detail, register/drop with confirmation, "my timetable" as a weekly grid, and enrollment history. Lecturer: assigned sections, roster, grade entry. Admin: registration-window control and enrollment override, beyond what Django admin gives for free. Every rule rejection surfaces the specific reason, never a generic failure.

*Done when:* a student can complete register → clash rejection → waitlist → drop → promotion entirely through the browser.

### Phase 5 — REST API
DRF setup with token auth, viewsets and serializers for courses, sections, terms, enrollments, and the student's own profile. Registration and drop are `POST` actions returning structured errors (`{"rule": "R5", "detail": "..."}`) so mobile can present them meaningfully. Add pagination, filtering, throttling, and OpenAPI schema generation via `drf-spectacular`. Permission classes must enforce that students see and touch only their own enrollments.

*Done when:* the OpenAPI schema is served, and API-level tests cover the same journeys as Phase 4 plus authorisation checks (student A cannot read or modify student B's enrollments).

### Phase 6 — Playwright E2E suite
Scaffold TypeScript Playwright. Build `utils/django-server.ts` to start a Django server on a disposable seeded SQLite file and tear it down after the run. Page Object Models for each screen. Storage-state fixtures for pre-authenticated student/lecturer/admin contexts.

Suites: authentication (login, bad credentials, logout, role redirects), catalogue (search, filter, pagination, detail), registration (happy path, each of R1–R7 rejected with the right message visible), waitlist (join, position shown, promotion after a drop), lecturer (roster, grade submission), admin (window control, override). Run on Chromium as the gate, Firefox and WebKit in the nightly build.

*Done when:* `npx playwright test` passes from a clean checkout with no manual setup, and the run is stable over 3 consecutive executions (no flakes).

### Phase 7 — Compose Multiplatform mobile
Scaffold the CMP project (Kotlin Multiplatform, Android + iOS). Shared `commonMain`: Ktor client against the Phase 5 API, `kotlinx.serialization` models, repositories, ViewModels, Compose UI, and secure token storage per platform. Screens: login, catalogue with search, section detail, register/drop, my timetable, profile. Handle offline gracefully — cache the catalogue, queue nothing, and show clear connectivity state. Surface API rule errors verbatim from the server.

*Done when:* both an Android emulator and an iOS simulator run a full login → browse → register → view timetable flow against a local Django server.

### Phase 8 — CI, hardening, documentation
GitHub Actions: lint → Django unit tests → Playwright E2E on every push; CMP build on changes under `cmp/`. Then a hardening pass: SQLite `WAL` mode and a busy timeout, `SECRET_KEY` and `DEBUG` from the environment, CSRF/session/security headers, throttling on auth endpoints, structured logging, and a load sanity check on the registration endpoint (see §8). Finish the README, API docs, and a data-model diagram.

*Done when:* CI is green on a fresh clone and the hardening checklist is fully ticked.

---

## 7. Milestones

| # | Milestone | Phases | Demonstrates |
|---|---|---|---|
| M1 | Walking skeleton | 0–1 | Login works, roles separate |
| M2 | Catalogue live | 2 | Real academic data browsable |
| M3 | **Registration works** | 3–4 | Core value delivered end to end |
| M4 | API ready | 5 | Mobile unblocked |
| M5 | Regression-protected | 6 | Changes are safe to make |
| M6 | Mobile shipped | 7 | All three clients working |
| M7 | Production-ready | 8 | CI green, hardened, documented |

M3 is the point at which CRS becomes useful. Everything before it is scaffolding; everything after extends reach.

---

## 8. Risks

**SQLite write concurrency — the main structural risk.** SQLite serialises writes with a database-level lock. Registration is exactly the workload that hurts: a whole cohort competing for the last seats in the same section, at the same minute, the moment a window opens. Under load you will see `database is locked` errors. Mitigations: enable WAL mode and a generous `busy_timeout`, keep transactions as short as possible (do all rule reads before opening the write transaction), and retry on lock with backoff. Test this deliberately in Phase 8 with a concurrent-registration load script rather than discovering it on registration day. If concurrent registrations exceed roughly the low tens per second, PostgreSQL becomes the honest answer — the service layer is deliberately ORM-only so the swap is a settings change plus a data migration, not a rewrite.

**Seat overselling under race.** Two students taking one remaining seat simultaneously. Counting seats inside `transaction.atomic()` with `select_for_update()` on the section row is the fix; the concurrency test in Phase 3 must actually assert on it.

**Rule-engine complexity.** R1–R7 interact, and prerequisite chains plus clash detection are where subtle bugs hide. Keeping every rule a small pure-ish function with its own tests is the containment strategy.

**E2E flakiness.** Timing-dependent tests erode trust in the suite until people ignore red builds. Use Playwright's web-first assertions and auto-waiting, never fixed sleeps; seed data deterministically; and treat any flake as a bug to fix, not to retry.

**iOS toolchain friction.** CMP iOS builds need a correctly configured Xcode and can surface obscure Kotlin/Native linking errors. Validate an empty CMP project builds on both platforms at the *start* of Phase 7, before writing any feature code.

---

## 9. Immediate next steps

1. ~~Verify the Python toolchain.~~ ✅ Python 3.13.1 confirmed.
2. ~~`git init`, add `.gitignore`, first commit.~~ ✅ Done.
3. ~~Write `README.md`.~~ ✅ Done.
4. Confirm or amend the assumptions in §2 — particularly #1 (templates over SPA) and #5 (SQLite in production).
5. Begin Phase 1. **Note:** the custom user model must be created before the first `migrate`.
