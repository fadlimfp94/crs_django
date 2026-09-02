import fs from 'fs';
import os from 'os';
import path from 'path';
import { startDjangoServer } from './django-server';

// Playwright calls the function this module default-exports once before the
// run, and calls whatever it returns once after — no separate
// globalTeardown file or cross-process IPC needed for that pairing.
export default async function globalSetup() {
  const port = Number(process.env.CRS_E2E_PORT ?? 8765);
  const dbPath = path.join(os.tmpdir(), `crs-e2e-${process.pid}-${Date.now()}.sqlite3`);

  const server = await startDjangoServer({ dbPath, port });

  return async () => {
    await server.stop();
    for (const suffix of ['', '-journal', '-wal', '-shm']) {
      fs.rmSync(dbPath + suffix, { force: true });
    }
  };
}
