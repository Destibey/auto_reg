"""Turnstile Solver 进程管理 - 后端启动时自动拉起"""
import subprocess
import sys
import os
import time
import threading
import requests
from pathlib import Path

_proc: subprocess.Popen = None
_log_file = None
_lock = threading.Lock()
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _solver_enabled() -> bool:
    return _get_runtime_env("APP_ENABLE_SOLVER", "1").lower() not in {"0", "false", "no"}


def _solver_port() -> int:
    return int(_get_runtime_env("SOLVER_PORT", "8889"))


def _solver_url() -> str:
    return (_get_runtime_env("LOCAL_SOLVER_URL") or f"http://127.0.0.1:{_solver_port()}").rstrip("/")


def _solver_bind_host() -> str:
    return _get_runtime_env("SOLVER_BIND_HOST", "0.0.0.0")


def _solver_browser_type() -> str:
    return _get_runtime_env("SOLVER_BROWSER_TYPE", "camoufox")


def _solver_thread() -> int:
    try:
        return max(1, int(_get_runtime_env("SOLVER_THREAD", "1")))
    except Exception:
        return 1


def _get_runtime_env(key: str, default: str = "") -> str:
    value = os.getenv(key, "").strip()
    if value:
        return value
    try:
        lines = _ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        item_key, item_value = line.split("=", 1)
        if item_key.strip() == key:
            return item_value.strip().strip("'\"")
    return default


def _solver_log_path() -> str:
    runtime_dir = _get_runtime_env("APP_RUNTIME_DIR")
    if runtime_dir:
        log_dir = Path(runtime_dir) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return str(log_dir / "solver.log")
    return os.path.join(os.path.dirname(__file__), "turnstile_solver", "solver.log")


def is_running() -> bool:
    try:
        r = requests.get(f"{_solver_url()}/", timeout=2)
        return r.status_code < 500
    except Exception:
        return False


def start():
    global _proc, _log_file
    with _lock:
        if not _solver_enabled():
            print("[Solver] 已禁用，跳过自动启动")
            return
        if is_running():
            print("[Solver] 已在运行")
            return
        solver_script = os.path.join(
            os.path.dirname(__file__), "turnstile_solver", "start.py"
        )
        log_path = _solver_log_path()
        _log_file = open(log_path, "a", encoding="utf-8")
        _proc = subprocess.Popen(
            [
                sys.executable,
                "-u",
                solver_script,
                "--browser_type",
                _solver_browser_type(),
                "--host",
                _solver_bind_host(),
                "--port",
                str(_solver_port()),
                "--thread",
                str(_solver_thread()),
            ],
            stdout=_log_file,
            stderr=subprocess.STDOUT,
        )
        # 等待服务就绪（最多30s）
        for _ in range(30):
            time.sleep(1)
            if is_running():
                print(f"[Solver] 已启动 PID={_proc.pid}")
                return
            if _proc.poll() is not None:
                print(f"[Solver] 启动失败，退出码={_proc.returncode}，日志: {log_path}")
                _proc = None
                if _log_file:
                    _log_file.close()
                    _log_file = None
                return
        print(f"[Solver] 启动超时，日志: {log_path}")


def stop():
    global _proc, _log_file
    with _lock:
        if _proc and _proc.poll() is None:
            _proc.terminate()
            _proc.wait(timeout=5)
            print("[Solver] 已停止")
        _proc = None
        if _log_file:
            _log_file.close()
            _log_file = None


def start_async():
    """在后台线程启动，不阻塞主进程"""
    t = threading.Thread(target=start, daemon=True)
    t.start()
