// Course codes and term labels the registration/waitlist suites target, one
// per rule, chosen up front so fullyParallel workers never race over the
// same section. Real seed_demo_data courses cover the rules reachable from
// its realistic dataset (R1/R2/R3/R7); the E2E101-107 courses come from
// seed_e2e_fixtures.py, which pre-registers the preconditions each of these
// needs (see that file's docstring for the exact shape).
export const TERM_NAMES = {
  fall: 'Fall 2026',
  spring: 'Spring 2026',
};

export const RULE_COURSES = {
  happyPath: 'CS102', // no prerequisite
  closedWindow: 'CS201', // registered against Spring, whose window is shut (R1)
  duplicate: 'MATH101', // register twice with the same student, same term (R2)
  prerequisite: 'CS201', // Fall; the default student holds no grades (R3)
  standing: 'CS101', // no prerequisite, so a probationary student's attempt reaches R7
  waitlist: 'E2E101', // capacity 1
  clashAttempt: 'E2E103', // e2e-clash is pre-registered into E2E102, same day/time (R5)
  overloadAttempt: 'E2E106', // e2e-overload is pre-registered into E2E104+E2E105, 24 credits already (R4)
  grademe: 'E2E107',
};

// Exact ModelChoiceField option labels for the admin override form
// (str(StudentProfile) / str(Section) — see academics/models.py, accounts/models.py).
export const OVERRIDE_TARGET = {
  studentLabel: '2024002 — Iwan Kurniawan', // suspended — R7 would otherwise reject them
  sectionLabel: 'CS102-01 (2026-FALL)',
};
