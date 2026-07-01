from __future__ import annotations

from pathlib import Path


def test_core_modules_compile_without_bytecode_writes():
    for filename in ["builder_app.py", "platform_store.py", "app.py"]:
        source = Path(filename).read_text(encoding="utf-8")
        compile(source, filename, "exec")

