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
import tempfile


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
    # Streamlit delays its running indicator by ~500 ms. Waiting past that
    # threshold distinguishes a rendered page from a fully completed script run.
    #
    # Newer Streamlit versions may keep the connection-status element mounted
    # in the DOM and toggle its visibility / contents during reconnects. Tests
    # should therefore check that the running icon is gone and that there is
    # no visible "Connecting" text or active "Connection error" dialog.
    page.wait_for_timeout(700)
    playwright_api.expect(page.get_by_test_id("stStatusWidgetRunningIcon")).to_have_count(0, timeout=timeout_ms)

    # The connection status node may remain mounted in newer Streamlit
    # versions. If it exists, assert it is not visible instead of asserting
    # its absence from the DOM.
    connection_status = page.get_by_test_id("stConnectionStatus")
    try:
        if connection_status.count() > 0:
            playwright_api.expect(connection_status).not_to_be_visible(timeout=timeout_ms)
    except Exception:
        # If the locator operations fail for some reason, fall back to the
        # more general check for visible "Connecting" text.
        try:
            playwright_api.expect(page.get_by_text("Connecting")).to_have_count(0, timeout=timeout_ms)
        except Exception:
            pass


def reconnect_streamlit_page(page, streamlit_server: StreamlitServer, attempts: int = 3) -> None:
    """Reconnect after a wedged frontend, retrying transient server unavailability."""
    last_error: Exception | None = None
    port = int(streamlit_server.url.rsplit(":", 1)[1])
    for _ in range(attempts):
        if streamlit_server.process.poll() is not None:
            raise RuntimeError(
                f"Streamlit server exited with code {streamlit_server.process.returncode}.\n"
                f"Server log tail:\n{streamlit_server.log_tail()}"
            )
        try:
            wait_for_streamlit_health(port, timeout_seconds=15)
            page.goto(streamlit_server.url, wait_until="domcontentloaded", timeout=30_000)
            return
        except Exception as error:
            last_error = error
            page.wait_for_timeout(1000)
    raise RuntimeError(f"Could not reconnect to the Streamlit test server: {last_error}") from last_error


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
            "PYTHONFAULTHANDLER": "1",
            "SHADE_GIS_DB_PATH": str(temp_root / "shade-gis-ui.sqlite3"),
            "SHADE_GIS_VOTE_DB_PATH": str(temp_root / "shade-gis-votes-ui.sqlite3"),
            "SHADE_GIS_TEST_DISABLE_AUTO_SAVE": "1",
            "SHADE_GIS_TEST_MAX_SEED_ROWS": "100",
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
        "--runner.fastReruns",
        "false",
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
        # Ensure the root page is responding with HTTP 200. The Streamlit app
        # frontend is rendered client-side via JS and WebSocket; a successful
        # HTTP response is sufficient here. The test itself uses Playwright to
        # wait for rendered content.
        root_url = f"http://127.0.0.1:{port}/"
        root_deadline = time.time() + 45
        last_error: Exception | None = None
        while time.time() < root_deadline:
            try:
                with urllib.request.urlopen(root_url, timeout=2) as response:
                    if getattr(response, "status", None) == 200:
                        break
            except Exception as error:
                last_error = error
            time.sleep(0.5)
        else:
            raise RuntimeError(f"Streamlit root page did not become available: {last_error}")
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
        chart_events: list[tuple[str, str]] = []
        current_surface = {"name": "Data"}
        # Capture all console messages, page errors, failed requests, and
        # websocket events for later debugging in CI.
        page.on("console", lambda message: chart_events.append((message.type, message.text)))
        page.on("pageerror", lambda error: chart_events.append(("pageerror", str(error))))
        # Record failed network requests
        page.on("requestfailed", lambda request: chart_events.append(("requestfailed", request.url)))
        # Record websocket connections and closures (Playwright exposes a WebSocket object)
        def _on_ws(ws):
            try:
                chart_events.append(("websocket", getattr(ws, "url", "")))
                ws.on("close", lambda _: chart_events.append(("websocket_closed", getattr(ws, "url", ""))))
            except Exception:
                pass

        page.on("websocket", _on_ws)
        # Keep the original targeted warnings separate for assertions.
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
                target_heading = page.get_by_role("heading", name=heading, exact=True)

                for attempt in range(2):
                    navigation_error: Exception | None = None
                    try:
                        # Streamlit mounts the next page's header before its rerun has
                        # necessarily finished. During that window the nav buttons are
                        # visible but disabled, so visibility alone is not a safe signal
                        # that another navigation click can be accepted.
                        nav_button.wait_for(state="visible", timeout=15_000)
                        playwright_api.expect(nav_button).to_be_enabled(timeout=60_000)
                        nav_button.click(timeout=60_000)
                        playwright_api.expect(target_heading).to_be_visible(timeout=30_000)
                        break
                    except Exception as error:
                        navigation_error = error

                    if attempt == 1:
                        assert navigation_error is not None
                        raise navigation_error

                    # A healthy server does not guarantee that the browser's current
                    # Streamlit WebSocket session recovered. When that session is
                    # wedged, every button remains disabled indefinitely and retrying
                    # against the same DOM cannot succeed. Reconnect the page before
                    # resolving a fresh locator for the second attempt. The UI fixture
                    # uses a temporary durable project store, so a replacement frontend
                    # session still loads the same test project.
                    reconnect_streamlit_page(page, streamlit_server)
                    page.locator(
                        ".builder-brand",
                        has_text="Shade-GIS",
                    ).wait_for(timeout=30_000)
                    wait_for_streamlit_idle(playwright_api, page)

                    nav_button = (
                        page.get_by_test_id("stMainBlockContainer").get_by_role("button", name=nav_label, exact=True)
                    )
                wait_for_streamlit_idle(playwright_api, page)
                playwright_api.expect(nav_button).to_have_attribute("kind", "primary", timeout=60_000)
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
            # Save debugging artifacts: screenshot, full HTML, body text, and console log.
            try:
                dump_dir = Path(tempfile.gettempdir()) / "shade_gis_ui_failure_logs"
                dump_dir.mkdir(parents=True, exist_ok=True)
                basename = f"ui_failure_{int(time.time())}_{uuid.uuid4().hex}"
                screenshot_path = dump_dir / f"{basename}.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                html_path = dump_dir / f"{basename}.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(page.content())
                text_path = dump_dir / f"{basename}.txt"
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(page.locator("body").inner_text())
                console_path = dump_dir / f"{basename}_console.txt"
                with open(console_path, "w", encoding="utf-8") as f:
                    for kind, msg in chart_events:
                        f.write(f"{kind}: {msg}\n")
            except Exception:
                # Best-effort debug dump; ignore failures here to not hide original error.
                pass
            raise AssertionError(
                f"UI failure while testing {current_surface['name']}: {error}"
                f"\n\nStreamlit server log tail:\n{streamlit_server.log_tail()}"
            ) from error
        finally:
            browser.close()
