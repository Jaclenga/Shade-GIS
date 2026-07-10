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


def wait_for_streamlit_idle(playwright_api, page, timeout_ms: int = 60_000) -> None:
    # Streamlit delays its running indicator by 500 ms. Waiting past that
    # threshold distinguishes a rendered page from a fully completed script run.
    page.wait_for_timeout(700)
    playwright_api.expect(page.get_by_test_id("stStatusWidgetRunningIcon")).to_have_count(0, timeout=timeout_ms)
    playwright_api.expect(page.get_by_test_id("stConnectionStatus")).to_have_count(0, timeout=timeout_ms)


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
            "SHADE_GIS_VOTE_DB_PATH": str(temp_root / "shade-gis-votes-ui.sqlite3"),
            "SHADE_GIS_TEST_DISABLE_AUTO_SAVE": "1",
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
        # Wait for the root page to return the app HTML. This avoids a flaky
        # client "Connection" state where the server's health endpoint is
        # available but the app frontend hasn't finished initializing.
        root_url = f"http://127.0.0.1:{port}/"
        root_deadline = time.time() + 45
        last_error: Exception | None = None
        while time.time() < root_deadline:
            try:
                with urllib.request.urlopen(root_url, timeout=2) as response:
                    body = response.read(4096).decode("utf-8", errors="ignore")
                    if "Shade-GIS" in body or "Project Data" in body:
                        break
            except Exception as error:
                last_error = error
            time.sleep(0.5)
        else:
            raise RuntimeError(f"Streamlit root page did not return app HTML: {last_error}")
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
        current_surface = {"name": "Data"}
        page.on(
            "console",
            lambda message: chart_warnings.append(f"{current_surface['name']}: {message.text}")
            if "Scale bindings are currently only supported" in message.text
            or "Infinite extent for field" in message.text
            else None,
        )
        try:
            page.goto(streamlit_server.url, wait_until="domcontentloaded")
            page.locator(".builder-brand", has_text="Shade-GIS").wait_for(timeout=30_000)
            page.get_by_role("heading", name="Project Data", exact=True).wait_for(timeout=30_000)
            playwright_api.expect(page.get_by_role("button", name="Data", exact=True)).to_be_enabled(timeout=30_000)
            wait_for_streamlit_idle(playwright_api, page)

            for nav_label, heading in expected_pages.items():
                current_surface["name"] = nav_label
                nav_button = page.get_by_test_id("stMainBlockContainer").get_by_role("button", name=nav_label, exact=True)
                wait_for_streamlit_idle(playwright_api, page)
                playwright_api.expect(nav_button).to_be_enabled(timeout=60_000)
                nav_button.click()
                playwright_api.expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible(timeout=60_000)
                wait_for_streamlit_idle(playwright_api, page)
                playwright_api.expect(nav_button).to_have_attribute("kind", "primary", timeout=60_000)
                playwright_api.expect(nav_button).to_be_enabled(timeout=60_000)
                if nav_label == "Voting":
                    voting_toggle_container = page.get_by_test_id("stCheckbox").filter(
                        has_text="Let deployed-app visitors vote on stop coverage"
                    )
                    voting_toggle = voting_toggle_container.get_by_role("checkbox")
                    voting_toggle_container.click()
                    playwright_api.expect(voting_toggle).to_be_checked(timeout=30_000)
                    playwright_api.expect(
                        page.get_by_text(
                            "Voting is currently hidden in the deployed app. Enable it to publish this interface.",
                            exact=True,
                        )
                    ).to_have_count(0, timeout=60_000)
                    wait_for_streamlit_idle(playwright_api, page)
                elif nav_label == "Preview":
                    voting_tab = page.get_by_role("tab", name="Voting", exact=True)
                    stop_details_tab = page.get_by_role("tab", name="Stop details", exact=True)
                    playwright_api.expect(voting_tab).to_be_visible(timeout=60_000)
                    playwright_api.expect(stop_details_tab).to_be_visible(timeout=60_000)
                    voting_tab.click()
                    playwright_api.expect(voting_tab).to_have_attribute("aria-selected", "true", timeout=60_000)
                    playwright_api.expect(
                        page.get_by_role("heading", name="Help document this stop", exact=True)
                    ).to_be_visible(timeout=60_000)
                    stop_details_tab.click()
                    playwright_api.expect(stop_details_tab).to_have_attribute("aria-selected", "true", timeout=60_000)
                    playwright_api.expect(
                        page.get_by_role("heading", name="Stop Details", exact=True)
                    ).to_be_visible(timeout=60_000)
                    voting_tab.click()
                    playwright_api.expect(
                        page.get_by_role("heading", name="Help document this stop", exact=True)
                    ).to_be_visible(timeout=60_000)
                    analytics_tab = page.get_by_role("tab", name="Analytics", exact=True)
                    analytics_tab.click()
                    playwright_api.expect(analytics_tab).to_have_attribute("aria-selected", "true", timeout=60_000)
                    playwright_api.expect(
                        page.get_by_role("heading", name="Summary Statistics", exact=True)
                    ).to_be_visible(timeout=60_000)
                    wait_for_streamlit_idle(playwright_api, page)

            assert chart_warnings == []
            assert streamlit_server.process.poll() is None
        except Exception as error:
            raise AssertionError(f"{error}\n\nStreamlit server log tail:\n{streamlit_server.log_tail()}") from error
        finally:
            browser.close()
