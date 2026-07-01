from __future__ import annotations

from pathlib import Path


def test_core_modules_compile_without_bytecode_writes():
    for filename in ["builder_app.py", "platform_store.py", "app.py", "published_app.py"]:
        source = Path(filename).read_text(encoding="utf-8")
        compile(source, filename, "exec")


def test_deploy_source_comes_from_public_app_module():
    import builder_app

    assert builder_app.published_app_source() == Path("published_app.py").read_text(encoding="utf-8")


def test_app_py_is_builder_entrypoint():
    import app

    assert app.main.__module__ == "builder_app"
