"""Compare the crates the sqb and extension builds share."""

from __future__ import annotations

from scripts.build_features.models import FeatureDrift, ResolvedCrate


def find_feature_drift(
    *,
    target: str,
    sqb: dict[ResolvedCrate, frozenset[str]],
    extension: dict[ResolvedCrate, frozenset[str]],
) -> tuple[FeatureDrift, ...]:
    """Return every crate both builds compile on the same side with different features."""
    return tuple(
        FeatureDrift(
            target=target,
            crate=crate,
            sqb_features=sqb[crate],
            extension_features=extension[crate],
        )
        for crate in sorted(sqb.keys() & extension.keys(), key=lambda c: (c.package, c.side))
        if sqb[crate] != extension[crate]
    )
