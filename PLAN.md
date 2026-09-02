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

### Phase 1 — Django skeleton and authentication ✅ COMPLETE
Create the project with split settings (`base`/`dev`/`test`/`prod`). Add the `accounts` app with the custom user model and both profile models — **the custom user model must land before the first `migrate`**, as swapping it later requires destroying the database. Build login, logout, and password-change views plus a role-aware base template and navigation. Register everything in Django admin. Configure `ruff` and `black`.

*Done when:* a superuser can log in, three test users (one per role) exist, and each lands on a role-appropriate placeholder dashboard.

**Delivered:** Django 5.2.17 on Python 3.13.1; `User` (+`role`) with `StudentProfile`/`LecturerProfile`; role-guard mixins; login/logout/password-change; three placeholder dashboards; configured admin; `create_test_users` command; 58 passing tests; `ruff`/`black` clean; `check --deploy` clean under prod settings.

**Deviations from plan, carried into Phase 2:**
- `StudentProfile.program` and `LecturerProfile.department` are deferred — `Program` and `Department` do not exist until Phase 2. Phase 2 adds both as FK fields via a migration (no data to migrate, so this is cheap).
- SQLite WAL mode, `foreign_keys=ON`, and a 20-second busy timeout were pulled forward from Phase 8 into `settings/base.py`, since they are one-line settings and PLAN.md §8 identifies lock contention as the main structural risk. The concurrency **load test** remains in Phase 8.
- The UI is hand-written CSS with no CDN, so the Playwright suite runs offline and deterministically.
- Templates carry `data-testid` attributes throughout, to give Phase 6 stable selectors.

### Phase 2 — Academic catalogue ✅ COMPLETE
Build the `academics` app: `Department`, `Program`, `Course`, `PrerequisiteRule`, `Term`, `Section`, `Meeting`. Rich admin with inlines (meetings inline on sections), list filters, and search. Add a `seed_demo_data` management command producing a realistic dataset: ~4 departments, ~30 courses with a prerequisite chain at least 3 levels deep, 2 terms (one open for registration, one closed), ~50 sections, and users of every role.

*Done when:* `python manage.py seed_demo_data` populates a browsable catalogue from a clean database, and the command is idempotent.

**Delivered:** all seven catalogue models with database-level constraints (not just `choices`); `academics/grades.py` with a grade-point scale; admin for all seven models with four inlines and working autocompletes; `seed_demo_data` producing 4 departments, 5 programs, 30 courses, 29 prerequisite rules, 2 terms, 56 sections and 78 meetings, plus 9 lecturers and 7 students; verified idempotent and non-destructive from a clean database; 176 passing tests (118 new), clean under `-W error::Warning`; `ruff`/`black` clean.

**Design choices worth carrying into Phase 3:**
- Seat counts are deliberately **not** stored on `Section`. Phase 3 counts `Enrollment` rows inside the write transaction, so there is no denormalised number to drift.
- Prerequisites use an explicit through-model (`PrerequisiteRule`) with a `minimum_grade`, so R3 can demand better than a bare pass. Cycle detection is a graph walk in `clean()` — the database can only catch the self-reference case.
- Grades are compared by **grade points, never strings**: `"B-" > "B+"` is true lexicographically and false academically. `academics/grades.py` owns the comparison; R3 must use it.
- At most one `Term` may be active, enforced by a partial unique index rather than application code.
- Clash detection is half-open (`a_start < b_end and b_start < a_end`), so 10:00–11:00 and 11:00–12:00 do not clash. `Section.clashes_with()` already exists for R5 to call.

**Deviations from plan:**
- `Section.room` was dropped, leaving `Meeting.room` the single source of truth — a section that meets in two rooms on two days cannot be described by one field on the section.
- The seed timetable uses a uniform, strictly non-overlapping four-slot grid, which reduces occupancy checking to a set lookup on `(day, slot_index)`. Mixed-length sessions would have needed interval arithmetic in the seeder for no demonstrable gain.
- 56 sections rather than "~50", because giving every level-100 course a second section is what makes the catalogue look real.
- `academics` ships no views. The catalogue is browsable through the admin, as the "done when" asks; the student-facing catalogue is Phase 4, so `academics.urls` is not yet in `config/urls.py`.

### Phase 3 — Registration engine ✅ COMPLETE
Implement R1–R7 and the `register` / `drop` / `promote_from_waitlist` services. Cover each rule with unit tests including boundary cases: registration window opening and closing to the second, a prerequisite passed vs. failed by one grade step, credit limit hit exactly vs. exceeded by one, meetings that touch end-to-start (10:00–11:00 and 11:00–12:00 must **not** clash) vs. genuinely overlap, last seat taken, and a concurrent double-registration attempt.

*Done when:* the rule test suite passes and every rule has at least one passing and one failing case. This phase carries the highest defect risk — do not move on with tests skipped.

**Delivered:** the `registration` app with `Enrollment` (one row per (student, section) pair for the entire relationship's history, `on_delete=PROTECT` on both FKs, two `CheckConstraint`s for waitlist-position and grade consistency); `registration/services.py` implementing R1–R7 as small single-purpose functions each with its own passing/failing test, plus `register()`, `drop()`, and `promote_from_waitlist()`; waitlist promotion re-validates R4, R5, and R7 before promoting — a candidate who now fails one is skipped (left waitlisted at their existing position) and the next candidate is tried, per the design decision above; `EnrollmentAdmin` with autocomplete on student/section; 39 new passing tests (10 model, 28 service/rule, 1 real-thread concurrency test asserting exactly one of two simultaneous registrants gets the last seat); `ruff`/`black` clean; manually verified end-to-end against seeded data (register → waitlist → drop → promotion).

**Deviations from plan:**
- Added an application-level `_retry_on_lock` decorator around `register`/`drop`/`promote_from_waitlist`. SQLite's shared-cache mode raises a distinct error, `SQLITE_LOCKED` ("database table is locked"), when two same-process connections touch the same table concurrently — and SQLite deliberately skips the busy handler for this case (to avoid a same-process deadlock), so the 20-second `busy_timeout` from Phase 1 never engages. The concurrency test surfaced this; a handful of short retries resolves it, and the decorator is a no-op on PostgreSQL.
- `Enrollment.grade` uses `blank=True, default=""` rather than `null=True`, matching this codebase's `ruff` `DJ001` convention (already followed elsewhere); `""` is the "no grade yet" sentinel, excluded from `choices`.
- Fixed a pre-existing drift found while running `makemigrations`: `academics.PrerequisiteRule.minimum_grade`'s committed migration had a typographic minus (`A−`) where the model code has always used a plain hyphen (`A-`). Landed as `academics/migrations/0002_alter_prerequisiterule_minimum_grade.py` — choices metadata only, no stored-data impact.

### Phase 4 — Web UI ✅ COMPLETE
Student: catalogue browse with filters (department, term, credits, availability, free-text search), section detail, register/drop with confirmation, "my timetable" as a weekly grid, and enrollment history. Lecturer: assigned sections, roster, grade entry. Admin: registration-window control and enrollment override, beyond what Django admin gives for free. Every rule rejection surfaces the specific reason, never a generic failure.

*Done when:* a student can complete register → clash rejection → waitlist → drop → promotion entirely through the browser.

**Delivered:** three new `registration/services.py` functions (`seats_remaining`, `record_grade`, `override_enrollment` — the latter deliberately bypasses R1–R5/R7 but still runs R6, so an admin's manual enrollment still respects capacity/waitlisting); `academics` gained `CatalogueListView` (paginated, filtered by department/term/credits/availability/free-text) and `SectionDetailView` for every role, plus `TermWindowListView`/`TermWindowUpdateView` for admins; `registration` gained `RegisterView`/`DropView` (confirm-then-POST, with rule rejections re-rendering the confirm page inline via `data-testid="registration-error"` rather than redirecting to a generic failure page), `MyTimetableView` (a CSS-grid weekly timetable built from half-hour ticks computed in Python), `EnrollmentHistoryView`, `LecturerSectionListView`/`SectionRosterView`/`GradeEntryView` (lecturer-scoped via `get_queryset`, so a different lecturer's section 404s rather than leaking a roster), and `EnrollmentOverrideView`; 12 new templates extending the existing hand-written-CSS, `data-testid`-everywhere convention; 50 new tests (24 `academics`, 26 `registration`) bringing the suite to 273 passing; `ruff`/`black` clean. Manually verified end-to-end against a live `runserver` process driven by `curl` with real cookie jars and scraped CSRF tokens (not just the Django test client) — register → fill a 2-seat section → waitlist a third student → drop → promotion, a genuine R5 clash surfacing inline with the specific message, a lecturer grading a roster row, and an admin editing a term's registration window and performing one R7-bypassing override — matching the "done when" exactly. All manual-walkthrough fixtures and side effects (test sections, a demo grade, a demo override, a term's credit cap) were removed/reverted afterward so the seeded dev database is unchanged.

**Deviations from plan:**
- No JS anywhere — even the weekly timetable is a server-computed CSS Grid (`grid-row`/`grid-column` set inline per meeting block from Python-computed half-hour ticks), not a client-side calendar widget.
- `TermWindowForm` deliberately excludes `is_active`, so the one-active-term partial-unique-index constraint from Phase 2 can never collide from this screen; toggling the active term stays a Django-admin action.
- Grade entry and enrollment override became small `forms.Form`s (`GradeEntryForm`, `OverrideEnrollmentForm`) rather than `ModelForm`s, since neither maps cleanly onto `Enrollment` (grading transitions `status` as a side effect; override takes a `(student, section)` pair, not a bound instance).

### Phase 5 — REST API ✅ COMPLETE
DRF setup with token auth, viewsets and serializers for courses, sections, terms, enrollments, and the student's own profile. Registration and drop are `POST` actions returning structured errors (`{"rule": "R5", "detail": "..."}`) so mobile can present them meaningfully. Add pagination, filtering, throttling, and OpenAPI schema generation via `drf-spectacular`. Permission classes must enforce that students see and touch only their own enrollments.

*Done when:* the OpenAPI schema is served, and API-level tests cover the same journeys as Phase 4 plus authorisation checks (student A cannot read or modify student B's enrollments).

**Delivered:** a new `api` app that is purely a second front door onto Phase 3's `registration/services.py` — no new business logic. `api/exceptions.py`'s `crs_exception_handler` turns any `RegistrationError` into `{"rule": "R5"|null, "detail": "..."}` at `status=400`, so every action that calls `register`/`drop`/`record_grade`/`override_enrollment` gets a structured error for free. `api/permissions.py`'s `IsStudent`/`IsLecturer`/`IsAdministrator` wrap the same `is_student`/`is_lecturer`/`is_administrator` properties `accounts.mixins.RoleRequiredMixin` already uses. `CourseViewSet`/`SectionViewSet`/`TermViewSet`/`EnrollmentViewSet` (`DefaultRouter`, giving a free browsable API root) plus `MeView` and a throttled `ObtainAuthTokenThrottled` token-obtain endpoint. `SectionViewSet.register` and `EnrollmentViewSet.drop`/`grade`/`override` call the exact same service functions Phase 4's views call. `EnrollmentViewSet.get_queryset()` scopes students to their own enrollments and lecturers to none (they use `SectionViewSet.roster` instead) — this scoping alone is what makes reading or dropping another student's enrollment 404. Token + session authentication, `PageNumberPagination` at `PAGE_SIZE=20`, anon/user/auth-scoped throttling, and an OpenAPI schema via `drf-spectacular` served at `/api/v1/schema/` with Swagger UI at `/api/v1/docs/`. 52 new tests across 7 files (`api/tests/`) bringing the suite to 325 passing, including the explicit authorisation checks (student A cannot read, drop, or see student B's enrollment) and one round-trip test per rule (R1–R5, R7) plus a `rule: null` case; `ruff`/`black` clean. Manually verified end-to-end against a live `runserver` driven by `curl` with `Authorization: Token` headers (no cookies/CSRF needed) — register → fill a 1-seat section → waitlist a second student → drop → promotion, a genuine R5 clash returning the structured error, a lecturer reading a roster and grading a row, and an admin PATCHing a term's registration window and performing one R7-bypassing override, plus confirming the schema and docs endpoints serve. All manual-walkthrough fixtures (two temporary sections/meetings/enrollments, four issued auth tokens, a temporarily-widened term credit cap) were removed/reverted afterward so the seeded dev database is unchanged.

**Deviations from plan:**
- No `django-filter` dependency — catalogue-style filtering (department/term/credits/availability/free-text/`mine`) is manual query-param parsing in `get_queryset()`, mirroring `academics.forms.CatalogueFilterForm`'s logic exactly rather than adding a new framework for it.
- `TermWindowUpdateSerializer.validate()` duplicates, at the serializer level, the window-ordering check `TermWindowForm` gets for free from `Model.full_clean()` → `validate_constraints()` — a plain `ModelSerializer.is_valid()` does not call `full_clean()`, so the three-field cross-check (`registration_opens_at` vs. `registration_closes_at`, defaulting to `self.instance`'s stored value so a partial `PATCH` is still checked against the other side) is reproduced explicitly instead.
- `TermViewSet` widens read access beyond Phase 4's admin-only term screens: `list`/`retrieve` are open to every authenticated role, because `SectionSerializer` needs full term data (including the registration window) for every listed section — a student needs it to understand *why* an R1/R4 rejection happened. Only the `PATCH` (and, as before, `is_active`, which stays excluded) remains admin-only.
- The generated OpenAPI schema does not document the custom `{"rule", "detail"}` error envelope — drf-spectacular has no visibility into a custom `EXCEPTION_HANDLER`'s response shape without per-action `@extend_schema(responses=...)` annotations, which was out of scope for this phase.

### Phase 6 — Playwright E2E suite ✅ COMPLETE
Scaffold TypeScript Playwright. Build `utils/django-server.ts` to start a Django server on a disposable seeded SQLite file and tear it down after the run. Page Object Models for each screen. Storage-state fixtures for pre-authenticated student/lecturer/admin contexts.

Suites: authentication (login, bad credentials, logout, role redirects), catalogue (search, filter, pagination, detail), registration (happy path, each of R1–R7 rejected with the right message visible), waitlist (join, position shown, promotion after a drop), lecturer (roster, grade submission), admin (window control, override). Run on Chromium as the gate, Firefox and WebKit in the nightly build.

*Done when:* `npx playwright test` passes from a clean checkout with no manual setup, and the run is stable over 3 consecutive executions (no flakes).

**Delivered:** `config/settings/test.py` now reads `CRS_E2E_DB_PATH` (falling back to `:memory:`, so `manage.py test` is unaffected) to point a real temp-file SQLite database at a separate `runserver` process — the mechanism the aspirational comment had been waiting on since Phase 1. A new `academics/management/commands/seed_e2e_fixtures.py` layers hard-to-reach fixtures on top of `seed_demo_data` (a capacity-1 section for the waitlist suite; a same-time section pair for the R5 clash; a credit-cap setup for R4; a pre-graded enrollment for the lecturer suite) — idempotent, `--force`/`--password`-gated, and never run outside the Playwright bootstrap. `playwright/utils/global-setup.ts` picks a temp DB path and a fixed port, runs `migrate` → `seed_demo_data` → `seed_e2e_fixtures` → `runserver` via `utils/django-server.ts`, polls for readiness, and returns a teardown that stops the server and deletes the temp DB and its sidecars. 13 Page Object Models cover every screen; `fixtures/auth.ts` exposes pre-authenticated `studentPage`/`lecturerPage`/`adminPage` fixtures built from `tests/setup/auth.setup.ts`'s storage states, while the eleven single-scenario accounts (R1–R7, waitlist pair, clash, overload, grademe) log in fresh per test since each is used exactly once. 28 tests across 8 spec files (auth, catalogue, registration rules, drop, timetable/history, waitlist promotion, lecturer roster, admin term windows and override) — `npx playwright test` (Chromium-only gate) passes cleanly, confirmed over 3 consecutive runs with zero flakes; `playwright.nightly.config.ts` adds Firefox/WebKit (78 tests total) for the nightly build. Python suite still green at 325 tests; `ruff`/`black` clean.

**Deviations from plan:**
- The plan's literal R4 fixture ("a course whose credits alone exceed the cap") isn't reachable: `Course.credits` is capped at 12 by `MaxValueValidator(12)`, well under the term's 24-credit ceiling. Used two pre-registered 12-credit sections (exactly at the cap) plus a third, small course the Playwright test itself attempts to register into through the UI — tipping the student over the cap is the actual action under test, rather than a precondition.
- R1 (closed window), R2 (duplicate), R3 (prerequisite), and R7 (standing) needed no new fixtures at all, contrary to the plan's implication that all seven rules would need dedicated E2E data — `seed_demo_data`'s existing closed Spring term, multi-section courses, prerequisite chain, and probationary student already reach them. Only R4, R5, and the waitlist/lecturer suites needed `seed_e2e_fixtures.py`.
- R2 is reached by registering into a *second section* of an already-enrolled course (`MATH101` has two Fall sections), not by re-registering into the same section — `RegisterView.get()` redirects away with an info message if the student already holds an active enrollment in that exact section, so the confirm page (and its inline error) is only reachable via a sibling section.
- Logout required clicking the real `logout-button` (a POST form in `base.html`) rather than a bare `page.goto('/accounts/logout/')` — Django's `LogoutView` only accepts `POST`.
- The lecturer grading test asserts the graded row *disappears* from the roster's "Enrolled" table rather than asserting the recorded letter grade is shown there — `record_grade` transitions the enrollment to `COMPLETED`, and `roster.html` has no table for completed students.
- `tsconfig.json` uses `"moduleResolution": "bundler"` rather than the plan's implied default — the installed TypeScript 7 removed the classic `"node"` alias outright (`TS5108`).

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
4. ~~Confirm the assumptions in §2.~~ ✅ Confirmed 2026-09-01 — templates over SPA, and the one-user-model-plus-profiles shape.
5. ~~Phase 1.~~ ✅ Done.
6. ~~Phase 2 — the academic catalogue.~~ ✅ Done. The migration added all seven models and wired up the two deferred profile FKs.
7. ~~Phase 3 — the registration engine.~~ ✅ Done. `register`/`drop`/`promote_from_waitlist` implement R1–R7; the concurrency test confirmed no overselling under a real race.
8. ~~Phase 4 — the web UI.~~ ✅ Done. Student catalogue browse/filter, section detail, register/drop with confirmation, "my timetable", enrollment history; lecturer roster and grade entry; admin registration-window control and enrollment override — verified through a real HTTP walkthrough, not just the test client.
9. ~~Phase 5 — the REST API.~~ ✅ Done. DRF viewsets/serializers for courses, sections, terms, and enrollments; token auth for mobile; structured `{"rule": "R5", "detail": "..."}` errors on registration/drop failures; permission classes enforcing that a student only ever sees their own enrollments.
10. ~~Phase 6 — the Playwright E2E suite.~~ ✅ Done. Disposable-database server lifecycle, 13 Page Object Models, and 28 tests covering auth, catalogue, all seven registration rules, waitlist promotion, lecturer grading, and admin controls — 3 consecutive clean runs confirmed.
11. Begin Phase 7 — the Compose Multiplatform mobile client.
