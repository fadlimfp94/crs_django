import { spawn } from 'child_process';
import path from 'path';

const DJANGO_DIR = path.resolve(__dirname, '..', '..', 'django');
const SETTINGS_MODULE = 'config.settings.test';

export interface DjangoServerHandle {
  baseURL: string;
  stop: () => Promise<void>;
}

function pythonBin(): string {
  // Prefer the project's own virtualenv so the suite runs with the same
  // interpreter/dependencies as `cd django && python manage.py runserver`.
  return process.env.CRS_E2E_PYTHON ?? path.join(DJANGO_DIR, '.venv', 'bin', 'python');
}

function runManageCommand(args: string[], env: NodeJS.ProcessEnv): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonBin(), ['manage.py', ...args], { cwd: DJANGO_DIR, env });
    let output = '';
    child.stdout.on('data', (chunk) => (output += chunk.toString()));
    child.stderr.on('data', (chunk) => (output += chunk.toString()));
    child.on('error', reject);
    child.on('exit', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`manage.py ${args.join(' ')} exited with code ${code}:\n${output}`));
    });
  });
}

async function waitUntilReady(url: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown = new Error('never attempted');
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.status === 200) return;
      lastError = new Error(`unexpected status ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Django server never became ready at ${url}: ${lastError}`);
}

export async function startDjangoServer(options: {
  dbPath: string;
  port: number;
}): Promise<DjangoServerHandle> {
  const { dbPath, port } = options;
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    DJANGO_SETTINGS_MODULE: SETTINGS_MODULE,
    CRS_E2E_DB_PATH: dbPath,
  };

  // Migrate and seed before the server starts, so a broken migration or seed
  // fails loudly here instead of leaving the server running against a
  // half-built database.
  await runManageCommand(['migrate', '--no-input'], env);
  await runManageCommand(['seed_demo_data', '--force'], env);
  await runManageCommand(['seed_e2e_fixtures', '--force'], env);

  const server = spawn(
    pythonBin(),
    ['manage.py', 'runserver', `127.0.0.1:${port}`, '--noreload', '--skip-checks'],
    { cwd: DJANGO_DIR, env }
  );

  let output = '';
  server.stdout.on('data', (chunk) => (output += chunk.toString()));
  server.stderr.on('data', (chunk) => (output += chunk.toString()));

  const exitedEarly = new Promise<never>((_resolve, reject) => {
    server.on('exit', (code) => {
      if (code !== null) reject(new Error(`Django server exited early with code ${code}:\n${output}`));
    });
  });

  const baseURL = `http://127.0.0.1:${port}`;
  await Promise.race([waitUntilReady(`${baseURL}/accounts/login/`, 30_000), exitedEarly]);

  const stop = () =>
    new Promise<void>((resolve) => {
      server.once('exit', () => resolve());
      server.kill('SIGTERM');
      setTimeout(() => {
        if (server.exitCode === null) server.kill('SIGKILL');
      }, 5_000);
    });

  return { baseURL, stop };
}
