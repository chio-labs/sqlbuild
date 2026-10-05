"""Shared builders for layered render storage unit tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.compile_render_reuse._helpers.render_state_file import (
    read_render_state,
    render_state_layer,
)
from sqlbuild.cli.compile_render_reuse.models import StoredRenderState
from sqlbuild.cli.compile_reuse.models import RenderStateLayer
from sqlbuild.compiler.compile.models import RenderReuseState

MODEL_PATHS: tuple[str, ...] = tuple(f"models/orders_{index:02d}.sql" for index in range(20))


def publish_render_state(*, directory: Path, name: str, layer: RenderStateLayer) -> Path:
    """Write one render layer as the store would publish it."""

    path: Path = directory / name
    path.write_bytes(b"".join(bytes(chunk) for chunk in layer.chunks))
    return path


def read_stored(path: Path) -> StoredRenderState:
    """Read a render file that must decode."""

    stored: StoredRenderState | None = read_render_state(path=path, changed_paths=frozenset())
    assert stored is not None
    return stored


def stored_base(directory: Path) -> tuple[Path, StoredRenderState]:
    """Publish a base render file holding every model and one group, and read it back."""

    state: RenderReuseState = RenderReuseState(
        model_paths=MODEL_PATHS,
        model_payloads={path: memoryview(f"render {path}".encode() * 20) for path in MODEL_PATHS},
        group_payloads={"sources": memoryview(b"source renders" * 20)},
    )
    path: Path = publish_render_state(
        directory=directory,
        name="orders-base.render",
        layer=render_state_layer(state=state, stored=None),
    )
    return path, read_stored(path)


def next_render_state(
    *, stored: StoredRenderState, edited: tuple[str, ...], removed: tuple[str, ...] = ()
) -> RenderReuseState:
    """Return the renders of the next compile: some models edited, some stored renders dropped."""

    kept: dict[str, memoryview] = dict(
        filter(lambda item: item[0] not in removed, stored.state.model_payloads.items())
    )
    return RenderReuseState(
        model_paths=MODEL_PATHS,
        model_payloads={
            **kept,
            **{path: memoryview(f"edited {path}".encode() * 20) for path in edited},
        },
        group_payloads=dict(stored.state.group_payloads),
    )


def payload_bytes(state: RenderReuseState) -> dict[str, bytes]:
    """Return every model payload as bytes for comparison."""

    return {path: bytes(payload) for path, payload in state.model_payloads.items()}


def store_edit_chain(*, directory: Path, edits: tuple[str, ...]) -> StoredRenderState:
    """Store one compile per edited model, each layered on the previous one, and read the last."""

    stored: StoredRenderState
    _, stored = stored_base(directory)
    for index, edited in enumerate(edits):
        path: Path = publish_render_state(
            directory=directory,
            name=f"orders-edit-{index}.render",
            layer=render_state_layer(
                state=next_render_state(stored=stored, edited=(edited,)), stored=stored
            ),
        )
        stored = read_stored(path)
    return stored


def chain_payload_bytes(edits: tuple[str, ...]) -> dict[str, bytes]:
    """Return the model payloads an edit chain must leave readable."""

    return {
        **{path: f"render {path}".encode() * 20 for path in MODEL_PATHS},
        **{path: f"edited {path}".encode() * 20 for path in edits},
    }


def flipped_last_byte(directory: Path) -> tuple[Path, frozenset[str]]:
    """Store a base render file and corrupt its last payload byte."""

    path, _ = stored_base(directory)
    data: bytearray = bytearray(path.read_bytes())
    data[-1] ^= 0xFF
    path.write_bytes(bytes(data))
    return path, frozenset()


def truncated(directory: Path) -> tuple[Path, frozenset[str]]:
    """Store a base render file and cut off its tail."""

    path, _ = stored_base(directory)
    path.write_bytes(path.read_bytes()[:-7])
    return path, frozenset()


def emptied(directory: Path) -> tuple[Path, frozenset[str]]:
    """Store a base render file and empty it."""

    path, _ = stored_base(directory)
    path.write_bytes(b"")
    return path, frozenset()


def overlay_without_base(directory: Path) -> tuple[Path, frozenset[str]]:
    """Store an overlay and delete the base file it layers on."""

    base_path, stored = stored_base(directory)
    overlay_path: Path = publish_render_state(
        directory=directory,
        name="orders-overlay.render",
        layer=render_state_layer(
            state=next_render_state(stored=stored, edited=(MODEL_PATHS[0],)), stored=stored
        ),
    )
    base_path.unlink()
    return overlay_path, frozenset()


def changed_macro(directory: Path) -> tuple[Path, frozenset[str]]:
    """Store a base render file and report a changed path that is not a stored model."""

    path, _ = stored_base(directory)
    return path, frozenset({"macros/currency.py"})


def intact(directory: Path) -> tuple[Path, frozenset[str]]:
    """Store a base render file and report one stored model as changed."""

    path, _ = stored_base(directory)
    return path, frozenset({MODEL_PATHS[4]})
