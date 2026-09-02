// Every seeded account (seed_demo_data.py + seed_e2e_fixtures.py) shares this
// password. Never a secret worth protecting — it's the repo's well-known
// dev/test password, seeded on a disposable database that's destroyed after
// every run.
export const PASSWORD = 'crs-dev-password';

export interface SeededUser {
  username: string;
}

export const ADMIN: SeededUser = { username: 'admin' };
export const LECTURER: SeededUser = { username: 'L-1001' };

// One dedicated account per scenario, so fullyParallel workers never race
// over the same student/enrollment row.
export const STUDENTS = {
  // 2026001 holds no enrollment history — reused for browsing/auth checks
  // (read-only) and for the R3 (missing prerequisite) test.
  default: { username: '2026001' } as SeededUser,
  happyPath: { username: '2026002' } as SeededUser,
  closedWindow: { username: '2025001' } as SeededUser, // R1
  duplicate: { username: '2024001' } as SeededUser, // R2
  probation: { username: '2025002' } as SeededUser, // R7
  suspended: { username: '2024002' } as SeededUser, // admin override target
  waitlistFirst: { username: 'e2e-wl-1' } as SeededUser,
  waitlistSecond: { username: 'e2e-wl-2' } as SeededUser,
  clash: { username: 'e2e-clash' } as SeededUser, // R5
  overload: { username: 'e2e-overload' } as SeededUser, // R4
  grademe: { username: 'e2e-grademe' } as SeededUser,
};
