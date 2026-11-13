"""不依赖 pytest 的极简测试运行器。

用法::

    python tests/run_tests.py

它会收集 ``tests/`` 下所有 ``test_*.py`` 里的 ``test_*`` 函数并逐个执行，
并提供 ``tmp_path`` / ``monkeypatch`` 两个最常用的 fixture。
（如果装了 pytest，也可以直接 ``pytest``。）
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import traceback
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS_DIR))


class MonkeyPatch:
    """最小可用的 monkeypatch 实现。"""

    def __init__(self) -> None:
        self._undo: list[tuple[object, str, object]] = []

    def setattr(self, target, name, value, raising: bool = True) -> None:  # noqa: ANN001
        try:
            old = getattr(target, name)
        except AttributeError:
            if raising:
                raise
            old = None
        self._undo.append((target, name, old))
        setattr(target, name, value)

    def undo(self) -> None:
        for target, name, old in reversed(self._undo):
            setattr(target, name, old)
        self._undo.clear()


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"bbdown_tests_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_tmp_dir() -> tempfile.TemporaryDirectory:
    """把临时目录放在工程内，避免系统临时目录的权限问题。"""
    base = ROOT / ".tmp-tests"
    base.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(dir=base, ignore_cleanup_errors=True)


def _make_tmp_dir() -> Path:
    """在工程内创建一个临时目录并返回。

    不用 ``tempfile.mkdtemp``：某些 Windows 沙箱环境下它建的目录无法被枚举。
    """
    import uuid

    base = ROOT / ".tmp-tests"
    base.mkdir(exist_ok=True)
    while True:
        path = base / ("tmp" + uuid.uuid4().hex[:8])
        try:
            path.mkdir()
            return path
        except FileExistsError:
            continue


def _run_test(func) -> str | None:  # noqa: ANN001
    params = inspect.signature(func).parameters
    kwargs = {}
    temporary: Path | None = None
    patch: MonkeyPatch | None = None
    try:
        if "tmp_path" in params:
            temporary = _make_tmp_dir()
            kwargs["tmp_path"] = temporary
        if "monkeypatch" in params:
            patch = MonkeyPatch()
            kwargs["monkeypatch"] = patch
        func(**kwargs)
        return None
    except Exception:
        return traceback.format_exc()
    finally:
        if patch is not None:
            patch.undo()
        if temporary is not None:
            import shutil

            shutil.rmtree(temporary, ignore_errors=True)


def main() -> int:
    total = 0
    failures: list[tuple[str, str]] = []

    for path in sorted(TESTS_DIR.glob("test_*.py")):
        module = _load_module(path)
        for name, func in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith("test_"):
                continue
            total += 1
            error = _run_test(func)
            label = f"{path.stem}::{name}"
            if error is None:
                print(f"ok   {label}")
            else:
                print(f"FAIL {label}")
                failures.append((label, error))

    print()
    for label, error in failures:
        print(f"===== {label} =====")
        print(error)

    print(f"通过 {total - len(failures)}/{total}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
