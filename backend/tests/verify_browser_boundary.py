"""Explicit local check of the test server's default-off production boundary."""
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def main() -> None:
    env = {key: value for key, value in os.environ.items() if key != "DPCIS_BROWSER_TEST"}
    result = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0, 'tests'); import browser_server"],
        cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True,
        check=False,
    )
    if result.returncode == 0 or "requires DPCIS_BROWSER_TEST=1" not in result.stderr:
        raise RuntimeError("Browser harness did not fail closed")
    settings = Settings(_env_file=None, APP_ENV="test", DATABASE_URL=None, DIRECT_DATABASE_URL=None)
    with TestClient(create_app(settings)) as client:
        if client.get("/__test_session").status_code != 404:
            raise RuntimeError("Normal application exposes a test session")
    print("Default-off backend guard: PASS; normal app /__test_session: 404")


if __name__ == "__main__":
    main()
