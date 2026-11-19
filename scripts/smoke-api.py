import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

root = Path(__file__).resolve().parent.parent
(root / "work").mkdir(exist_ok=True)
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
env = {key: value for key, value in os.environ.items() if not key.startswith("INSIGHTRAG_")}
executable = sys.executable
if os.name == "nt" and sys.prefix != sys.base_prefix:
    # The Windows venv executable launches the actual interpreter as a child.
    # Own that interpreter directly, preserving venv discovery through the same
    # launcher variable; terminate/wait can then close the real server's cwd.
    executable = sys._base_executable
    env["__PYVENV_LAUNCHER__"] = sys.executable
with (
    TemporaryDirectory(prefix="api-smoke-", dir=root / "work") as isolated,
    (root / "work" / "api-smoke.log").open("w", encoding="utf-8") as log,
):
    process = subprocess.Popen(
        [
            executable,
            "-m",
            "uvicorn",
            "insightrag.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=isolated,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=2, trust_env=False
        ) as client:
            for _ in range(50):
                try:
                    if client.get("/health/live").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("Uvicorn failed to become live")
            assert client.get("/health/ready").status_code == 503
            assert client.get("/api/v1/meta").json()["tenant_data_enabled"] is True
            assert client.get("/api/v1/me").status_code == 401
            assert "openapi" in client.get("/api/v1/openapi.json").json()
            echo = client.post("/api/v1/diagnostics/echo", json={"message": "synthetic-smoke"})
            assert echo.json()["request_id"] == echo.headers["x-request-id"]
            assert echo.json()["message"] == "synthetic-smoke"
            assert client.post("/api/v1/diagnostics/echo", json={"message": 2}).status_code == 422
    finally:
        try:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        finally:
            # Dispose process handles before TemporaryDirectory removes its cwd.
            del process

print(
    "PASS: real Uvicorn HTTP smoke: live, unconfigured readiness, "
    "metadata, OpenAPI, echo, validation/correlation, process and directory cleanup"
)
