import pytest

from sqlbuild import _native


def memo_reuses() -> int:
    """Native rules evaluations answered from the response memo since the last reset."""

    return _native.compile_stage_work_info().get("rules_memo_reuses", 0)


def rebuild_identity(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend the compiled code changed, as after installing another build."""

    identity: str = _native.compiled_code_identity()
    monkeypatch.setattr(_native, "compiled_code_identity", lambda: f"{identity}-rebuilt")
