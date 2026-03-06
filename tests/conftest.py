"""
Global test configuration and fixtures for Recall test suite.

Provides:
  - Automatic server startup for API integration tests (B-series)
  - ``recall_server`` session fixture that starts/stops the server
"""
import warnings
# 必须在任何第三方库导入之前设置 —— 拦截 jieba 等库在 Python 3.12 下的编译时 SyntaxWarning
warnings.filterwarnings("ignore", category=SyntaxWarning)

import os
import sys
import time
import socket
import subprocess
import pytest

# ---------------------------------------------------------------------------
# Server auto-start fixture
# ---------------------------------------------------------------------------
API_HOST = '127.0.0.1'
API_PORT = 18888

# Global flag — set to True once the server is confirmed reachable.
_server_available = False
_managed_server_proc = None


def _is_port_open(host=API_HOST, port=API_PORT, timeout=2):
    """Check if the server port is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


def is_server_running():
    """Public helper — used by test files to check server availability."""
    return _server_available


@pytest.fixture(scope="session", autouse=True)
def recall_server():
    """Auto-start Recall server if not already running.

    * If port 18888 is already open -> assume external server.
    * Otherwise -> start ``python -m recall serve`` as a subprocess,
      wait up to 120 s for it to accept connections.
    * On teardown -> terminate the subprocess.
    * If the server fails to start, ``_server_available`` stays False and
      API tests can choose to skip themselves -- offline tests are NOT blocked.
    """
    global _managed_server_proc, _server_available

    if _is_port_open():
        _server_available = True
        yield  # External server detected
        return

    # Locate the Python interpreter in the project venv
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_python = os.path.join(project_root, 'recall-env', 'Scripts', 'python.exe')
    if not os.path.exists(venv_python):
        venv_python = os.path.join(project_root, 'recall-env', 'bin', 'python')
    if not os.path.exists(venv_python):
        venv_python = sys.executable

    env = os.environ.copy()
    _managed_server_proc = subprocess.Popen(
        [venv_python, '-m', 'recall', 'serve',
         '--host', API_HOST, '--port', str(API_PORT)],
        cwd=project_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
    )

    # Wait for server readiness
    max_wait = 120
    for _ in range(max_wait):
        if _managed_server_proc.poll() is not None:
            # Server exited -- leave _server_available as False
            stdout = _managed_server_proc.stdout.read().decode(errors='replace')[:3000]
            stderr = _managed_server_proc.stderr.read().decode(errors='replace')[:3000]
            print(
                f"\n[conftest] WARNING: Recall server exited prematurely "
                f"(code={_managed_server_proc.returncode})\n"
                f"--- stdout (last 3 KB) ---\n{stdout}\n"
                f"--- stderr (last 3 KB) ---\n{stderr}",
                file=sys.stderr,
            )
            _managed_server_proc = None
            break
        if _is_port_open():
            _server_available = True
            break
        time.sleep(1)
    else:
        # Timed out
        if _managed_server_proc:
            _managed_server_proc.kill()
            _managed_server_proc = None
        print(
            f"\n[conftest] WARNING: Recall server did not start within {max_wait}s",
            file=sys.stderr,
        )

    yield

    # Teardown
    if _managed_server_proc and _managed_server_proc.poll() is None:
        _managed_server_proc.terminate()
        try:
            _managed_server_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            _managed_server_proc.kill()


@pytest.fixture
def require_server():
    """Fixture that skips the test if the Recall server is not available."""
    if not _server_available:
        pytest.skip("Recall server is not running")
    _managed_server_proc = None
