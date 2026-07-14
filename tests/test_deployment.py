from __future__ import annotations

import io
import hashlib
import json
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

import pytest

from shade_gis.deployment import (
    CommandResult,
    DeploymentTarget,
    deployment_readiness,
    detect_deployment_target,
    github_repository_slug,
    publish_website,
    unpublish_website,
)


@pytest.fixture
def deployment_tmp():
    directory = Path(".pytest-shade-deployment") / uuid.uuid4().hex
    directory.mkdir(parents=True)
    try:
        yield directory.resolve()
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _bundle_bytes() -> bytes:
    files = {
        "app.py": b"print('published')\n",
        "public_voting.py": b"VOTING = True\n",
        "shade_study_stops.csv": b"stop_id\n1001\n",
        "shade_study_config.json": b"{}",
        "requirements.txt": b"streamlit\n",
    }
    manifest_core = {
        "schema_version": 1,
        "study_id": "test-study",
        "project_name": "Test study",
        "repository": "owner/study",
        "deploy_mode": "existing",
        "entrypoint": "preview_app/app.py",
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }
    manifest_core["bundle_id"] = hashlib.sha256(
        json.dumps(manifest_core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
        bundle.writestr("deployment_manifest.json", json.dumps(manifest_core))
    return output.getvalue()


def test_github_repository_slug_supports_detected_remote_formats():
    assert github_repository_slug("https://github.com/owner/study.git") == "owner/study"
    assert github_repository_slug("git@github.com:owner/study.git") == "owner/study"
    assert github_repository_slug("owner/study") == "owner/study"
    assert github_repository_slug("https://example.com/owner/study") == ""


def test_publish_rejects_bundle_for_another_repository_before_git_runs():
    result = publish_website(
        _bundle_bytes(),
        DeploymentTarget(repository="owner/other", repository_url="https://github.com/owner/other"),
    )

    assert result.success is False
    assert "targets owner/study, not owner/other" in result.message


def test_publish_rejects_tampered_bundle_before_git_runs():
    original = _bundle_bytes()
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(output, "w") as changed:
        for name in source.namelist():
            content = source.read(name)
            changed.writestr(name, b"tampered\n" if name == "app.py" else content)

    result = publish_website(
        output.getvalue(),
        DeploymentTarget(repository="owner/study", repository_url="https://github.com/owner/study"),
    )

    assert result.success is False
    assert "app.py does not match its manifest hash" in result.message


def test_detect_deployment_target_uses_origin_and_remote_default_branch(deployment_tmp):
    tmp_path = deployment_tmp
    responses = {
        ("git", "rev-parse", "--show-toplevel"): str(tmp_path),
        ("git", "config", "--get", "remote.origin.url"): "https://github.com/owner/study.git",
        ("git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"): "origin/release",
    }

    def fake_runner(args, _cwd, _timeout):
        value = responses.get(tuple(args), "")
        return CommandResult(0 if value else 1, stdout=value)

    target = detect_deployment_target(tmp_path, runner=fake_runner)

    assert target.repository == "owner/study"
    assert target.repository_url == "https://github.com/owner/study.git"
    assert target.branch == "release"
    assert target.detected is True


def test_readiness_returns_one_outcome_level_blocker():
    target = DeploymentTarget()

    result = deployment_readiness(stops_empty=True, target=target, bundle_error="low-level build error")

    assert result.ready is False
    assert result.title == "Add project data before publishing"
    assert result.action_label == "Open Data"
    assert "low-level" not in result.message


def test_publish_and_unpublish_existing_repository_automatically(deployment_tmp, monkeypatch):
    target = DeploymentTarget(
        repository="owner/study",
        repository_url="https://github.com/owner/study.git",
        branch="main",
        mode="existing",
    )
    stages: list[str] = []
    observed: dict[str, object] = {"published": False, "pushes": 0, "statuses": 0}
    temporary_counter = iter(range(10))

    class WorkspaceTemporaryDirectory:
        def __init__(self, prefix="tmp"):
            self.path = deployment_tmp / f"{prefix}{next(temporary_counter)}"

        def __enter__(self):
            self.path.mkdir()
            return str(self.path)

        def __exit__(self, _exc_type, _exc, _traceback):
            shutil.rmtree(self.path, ignore_errors=True)

    monkeypatch.setattr(tempfile, "TemporaryDirectory", WorkspaceTemporaryDirectory)

    def fake_runner(args, cwd, _timeout):
        command = tuple(args)
        if command[:2] == ("git", "clone"):
            worktree = Path(args[-1])
            worktree.mkdir(parents=True)
            (worktree / "README.md").write_text("existing repository\n", encoding="utf-8")
            if observed["published"]:
                preview = worktree / "preview_app"
                preview.mkdir()
                (preview / "app.py").write_text("print('published')\n", encoding="utf-8")
            return CommandResult(0)
        if command[:3] == ("git", "diff", "--cached"):
            return CommandResult(1)
        if command == ("git", "config", "user.name"):
            return CommandResult(0, stdout="Shade-GIS Test")
        if command == ("git", "config", "user.email"):
            return CommandResult(0, stdout="shade-gis-test@example.com")
        if command[:2] == ("git", "add"):
            observed["app"] = (Path(cwd) / "preview_app" / "app.py").read_text(encoding="utf-8")
            observed["readme"] = (Path(cwd) / "README.md").read_text(encoding="utf-8")
            observed["manifest"] = (Path(cwd) / "preview_app" / "deployment_manifest.json").exists()
            return CommandResult(0)
        if command[:2] == ("git", "rm"):
            observed["removed"] = list(args[5:])
            return CommandResult(0)
        if command[:2] == ("git", "push"):
            observed["published"] = not bool(observed["published"])
            observed["pushes"] = int(observed["pushes"]) + 1
            return CommandResult(0)
        if command == ("git", "status", "--short", "--branch"):
            observed["statuses"] = int(observed["statuses"]) + 1
            return CommandResult(0, stdout="## main...origin/main")
        if command == ("git", "rev-parse", "HEAD"):
            return CommandResult(0, stdout="abc123")
        return CommandResult(0)

    result = publish_website(
        _bundle_bytes(),
        target,
        progress=lambda stage, _message: stages.append(stage),
        runner=fake_runner,
        verify_attempts=1,
        verify_interval=0,
    )

    assert result.success is True
    assert result.changed is True
    assert result.needs_host_setup is True
    assert result.verification_skipped is False
    assert stages == ["Check project", "Prepare website", "Publish", "Verify website"]
    assert observed["app"] == "print('published')\n"
    assert observed["readme"] == "existing repository\n"
    assert observed["manifest"] is True
    assert observed["statuses"] == 2

    unpublished = unpublish_website(target, runner=fake_runner)

    assert unpublished.success is True
    assert unpublished.changed is True
    assert observed["removed"] == ["preview_app"]
    assert observed["pushes"] == 2
