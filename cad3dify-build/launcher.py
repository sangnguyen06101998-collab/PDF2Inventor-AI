import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path


def app_data_dir():
    path = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Cad3Dify"
    path.mkdir(parents=True, exist_ok=True)
    return path


def choose_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def open_browser_when_ready(url, port):
    for _ in range(90):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(1)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "Cad3Dify chưa khởi động được giao diện. Hãy xem log tại thư mục AppData\\Local\\Cad3Dify.",
            "Cad3Dify",
            0x10,
        )
    except Exception:
        pass


def main():
    try:
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        app_script = root / "app" / "app.py"
        if not app_script.is_file():
            raise FileNotFoundError(f"Không tìm thấy giao diện Cad3Dify: {app_script}")

        port = choose_port()
        url = f"http://127.0.0.1:{port}"
        os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
        os.environ["STREAMLIT_SERVER_ADDRESS"] = "127.0.0.1"
        os.environ["STREAMLIT_SERVER_PORT"] = str(port)
        os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
        os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"

        threading.Thread(target=open_browser_when_ready, args=(url, port), daemon=True).start()

        from streamlit.web import cli as stcli
        sys.argv = [
            "streamlit", "run", str(app_script),
            "--server.headless=true",
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--server.fileWatcherType=none",
            "--browser.gatherUsageStats=false",
        ]
        stcli.main()
    except BaseException as exc:
        try:
            log = app_data_dir() / "launcher_error.log"
            log.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        if isinstance(exc, KeyboardInterrupt):
            return
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"Cad3Dify gặp lỗi khởi động: {type(exc).__name__}: {exc}\n\n"
                "Có thể xem launcher_error.log trong AppData\\Local\\Cad3Dify.",
                "Cad3Dify - Startup Error",
                0x10,
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
