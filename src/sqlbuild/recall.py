"""Public Recall sink authoring: a sink taking a ``RecallWriter`` replaces Recall's default."""

from sqlbuild._native import RecallWriter as RecallWriter

__all__ = ("RecallWriter",)
