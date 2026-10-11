"""The value text of a stored macro call's inputs, as the native memo keys persistent classes."""

from __future__ import annotations

from sqlbuild.compiler.macro_bridge._helpers.store_keys import (
    context_store_token,
    macro_store_token,
)


def macro_store_tokens() -> dict[str, object]:
    """`macro_store_token` and `context_store_token`, by the name the native memo reads them."""

    return {"macro_token": macro_store_token, "context_token": context_store_token}
