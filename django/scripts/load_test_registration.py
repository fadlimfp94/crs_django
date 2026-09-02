#!/usr/bin/env python
"""
Manual load sanity check for the registration endpoint (PLAN.md §8).

    cd django && python scripts/load_test_registration.py [--students N] [--capacity N]

Fires N concurrent authenticated HTTP requests at
``POST /api/v1/sections/<id>/register/`` for one small-capacity section,
against a real ``manage.py runserver`` process and a disposable temp-file
SQLite database — the HTTP-level counterpart to
``registration/tests/test_concurrency.py``'s in-process, ORM-direct
correctness test. This exercises the full stack that test can't reach:
middleware, DRF auth/permissions, and ``runserver``'s real threading model.

This is deliberately a script, not a test: PLAN.md calls for "a
concurrent-registration load script" a human runs deliberately before a real
registration window opens, not something CI runs on every push.

Exits non-zero if the final seat count doesn't match capacity exactly, or if
any request errored (including a "database is locked" 5xx).
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DJANGO_DIR = Path(__file__).resolve().parent.parent
SETTINGS_MODULE = "config.settings.test"
DEFAULT_PORT = 8766
READY_TIMEOUT_SECONDS = 30


def run_manage(args, env):
    result = subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=DJANGO_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"manage.py {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")


def wait_until_ready(base_url, timeout):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/accounts/login/", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"Django server never became ready at {base_url}: {last_error}")


def fetch_fixture_ids(env, student_count):
    """Read the fixture section's pk and each student's auth token directly via the ORM."""
    os.environ.update(env)
    sys.path.insert(0, str(DJANGO_DIR))
    import django

    django.setup()

    from rest_framework.authtoken.models import Token

    from academics.models import Section

    section = Section.objects.get(course__code="LOAD101", term__code="2026-FALL")
    tokens = list(
        Token.objects.filter(user__student_profile__student_number__startswith="load-")
        .order_by("user__student_profile__student_number")
        .values_list("key", flat=True)[:student_count]
    )
    return section.pk, tokens


def register(base_url, token, section_id):
    request = urllib.request.Request(
        f"{base_url}/api/v1/sections/{section_id}/register/",
        method="POST",
        data=b"",
        headers={"Authorization": f"Token {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read())
            return response.status, body.get("status")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--students", type=int, default=40)
    parser.add_argument("--capacity", type=int, default=10)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    db_path = Path(tempfile.gettempdir()) / f"crs-load-test-{os.getpid()}.sqlite3"
    base_url = f"http://127.0.0.1:{args.port}"
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": SETTINGS_MODULE,
        "CRS_E2E_DB_PATH": str(db_path),
    }

    server = None
    try:
        print(f"Preparing disposable database at {db_path} ...")
        run_manage(["migrate"], env)
        run_manage(["seed_demo_data", "--force"], env)
        run_manage(
            [
                "seed_load_test_fixtures",
                "--force",
                f"--students={args.students}",
                f"--capacity={args.capacity}",
            ],
            env,
        )

        print(f"Starting the server on {base_url} ...")
        server = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", str(args.port), "--noreload"],
            cwd=DJANGO_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_until_ready(base_url, READY_TIMEOUT_SECONDS)

        section_id, tokens = fetch_fixture_ids(env, args.students)
        if len(tokens) < args.students:
            raise RuntimeError(
                f"Expected {args.students} student tokens, found {len(tokens)} — "
                "did seed_load_test_fixtures run?"
            )

        print(f"Firing {len(tokens)} concurrent registrations at section {section_id} ...")
        started = time.monotonic()
        outcomes = Counter()
        errors = []
        with ThreadPoolExecutor(max_workers=len(tokens)) as pool:
            futures = [pool.submit(register, base_url, token, section_id) for token in tokens]
            for future in as_completed(futures):
                status_code, body = future.result()
                if status_code == 201:
                    outcomes[body] += 1
                else:
                    errors.append((status_code, body))
        elapsed = time.monotonic() - started

        print(f"Done in {elapsed:.2f}s — {dict(outcomes)}, {len(errors)} error(s)")
        for status_code, body in errors:
            print(f"  error: {status_code} {body}")

        ok = outcomes.get("ENROLLED") == args.capacity and not errors
        if not ok:
            print(
                f"FAIL: expected exactly {args.capacity} ENROLLED and zero errors.",
                file=sys.stderr,
            )
            return 1

        print("OK: seat count matched capacity, no errors.")
        return 0
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        for suffix in ("", "-journal", "-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
