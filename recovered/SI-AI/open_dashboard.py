"""Launch the localhost SI-AI dashboard when a notification is tapped."""

import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


BASE_DIR = Path(__file__).resolve().parent
PYTHON_BIN = Path(sys.executable)
TERMUX_BIN = PYTHON_BIN.parent
DASHBOARD_STATUS_URL = "http://127.0.0.1:5000/status"


def dashboard_is_ready():
    try:
        with urlopen(DASHBOARD_STATUS_URL, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return (
            isinstance(payload, dict)
            and payload.get("name") == "SI AI"
            and payload.get("trading_mode") == "Analysis Only"
            and payload.get("automatic_orders") is False
        )
    except Exception:
        return False


def show_error(message):
    toast = TERMUX_BIN / "termux-toast"
    if toast.is_file():
        try:
            subprocess.run(
                [str(toast), message],
                check=False,
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            pass


def main():
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else ""
    if symbol and (
        "/" not in symbol
        or symbol.count("/") != 1
        or not symbol.endswith("/USDT")
        or not symbol.replace("/", "").isalnum()
    ):
        show_error("SI-AI: invalid signal symbol")
        return 2

    if not dashboard_is_ready():
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "dashboard.log"
        try:
            with log_path.open("a", encoding="utf-8") as log_handle:
                subprocess.Popen(
                    [sys.executable, str(BASE_DIR / "main.py")],
                    cwd=str(BASE_DIR),
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
        except OSError:
            show_error("SI-AI dashboard could not be started")
            return 1

        for _ in range(40):
            if dashboard_is_ready():
                break
            time.sleep(0.25)

    if not dashboard_is_ready():
        show_error("SI-AI dashboard did not become ready; check logs/dashboard.log")
        return 1

    query = urlencode({"symbol": symbol}) if symbol else ""
    dashboard_url = "http://127.0.0.1:5000/signal"
    if query:
        dashboard_url = f"{dashboard_url}?{query}"

    open_url = TERMUX_BIN / "termux-open-url"
    try:
        if open_url.is_file():
            subprocess.run(
                [str(open_url), dashboard_url],
                check=True,
                timeout=10,
            )
        else:
            android_am = Path("/system/bin/am")
            if not android_am.is_file():
                raise FileNotFoundError("No Android URL opener is available")
            subprocess.run(
                [
                    str(android_am), "start",
                    "-a", "android.intent.action.VIEW",
                    "-d", dashboard_url,
                ],
                check=True,
                timeout=10,
            )
    except (OSError, subprocess.SubprocessError):
        show_error("SI-AI dashboard is ready, but Android could not open the browser")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
