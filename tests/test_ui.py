from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import pytest


pytestmark = pytest.mark.ui


@dataclass
class StreamlitServer:
    url: str
    process: subprocess.Popen[str]
    output: deque[str]

    def log_tail(self) -> str:
        return "".join(self.output) or "(no server output captured)"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_streamlit_health(port: int, timeout_seconds: int = 45) -> None:
    deadline = time.time() + timeout_seconds
    url = f"http://127.0.0.1:{port}/_stcore/health"
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as error:
            last_error = error
        time.sleep(0.5)
    raise RuntimeError(f"Streamlit health check did not pass at {url}: {last_error}")


@pytest.fixture
def playwright_api():
    return pytest.importorskip("playwright.sync_api")


@pytest.fixture
def streamlit_server(playwright_api):
    port = free_port()
    temp_root = Path(os.environ.get("TEMP", ".")) / "shade_gis_ui_tests" / uuid.uuid4().hex
    temp_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "SHADE_GIS_DB_PATH": str(temp_root / "shade-gis-ui.sqlite3"),
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
            "STREAMLIT_SERVER_HEADLESS": "true",
        }
    )
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
        "--server.headless",
        "true",
        "--server.fileWatcherType",
        "none",
        "--browser.gatherUsageStats",
        "false",
    ]
    process: subprocess.Popen[str] = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output: deque[str] = deque(maxlen=500)

    def drain_server_output() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            output.append(line)

    output_thread = threading.Thread(target=drain_server_output, daemon=True)
    output_thread.start()
    try:
        wait_for_streamlit_health(port)
        yield StreamlitServer(f"http://127.0.0.1:{port}", process, output)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        output_thread.join(timeout=5)
        shutil.rmtree(temp_root, ignore_errors=True)


def test_builder_navigation_pages_render(playwright_api, streamlit_server: StreamlitServer):
    expected_pages = {
        "Labels": "Labeling",
        "Visuals": "Metrics And Visualizations",
        "Voting": "Public Voting",
        "Docs": "Project Documentation",
        "Preview": "Tampa Bus Stop Shade Study",
        "Deploy": "Deploy",
    }
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        chart_warnings = []
        page.on(
            "console",
            lambda message: chart_warnings.append(message.text)
            if "Scale bindings are currently only supported" in message.text
            or "Infinite extent for field" in message.text
            else None,
        )
        try:
            page.goto(streamlit_server.url, wait_until="domcontentloaded")
            page.locator(".builder-brand", has_text="Shade-GIS").wait_for(timeout=30_000)
            page.get_by_role("heading", name="Project Data", exact=True).wait_for(timeout=30_000)
            playwright_api.expect(page.get_by_role("button", name="Data", exact=True)).to_be_enabled(timeout=30_000)
            playwright_api.expect(page.get_by_test_id("stConnectionStatus")).to_have_count(0, timeout=30_000)

            for nav_label, heading in expected_pages.items():
                nav_button = page.get_by_test_id("stMainBlockContainer").get_by_role("button", name=nav_label, exact=True)
                playwright_api.expect(nav_button).to_be_enabled(timeout=30_000)
                nav_button.click()
                playwright_api.expect(nav_button).to_have_attribute("kind", "primary", timeout=30_000)
                playwright_api.expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible(timeout=30_000)
                playwright_api.expect(nav_button).to_be_enabled(timeout=30_000)
                playwright_api.expect(page.get_by_test_id("stConnectionStatus")).to_have_count(0, timeout=30_000)

            assert chart_warnings == []
            assert streamlit_server.process.poll() is None
        except Exception as error:
            raise AssertionError(f"{error}\n\nStreamlit server log tail:\n{streamlit_server.log_tail()}") from error
        finally:
            browser.close()
