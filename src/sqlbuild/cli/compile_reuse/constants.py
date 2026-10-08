"""Compile reuse storage, fingerprint, and environment constants."""

from __future__ import annotations

from typing import Literal

from sqlbuild.cli.compile_reuse.classes.compile_artifact_write_registry import (
    CompileArtifactWriteRegistry,
)
from sqlbuild.compiler.frontier.constants import (
    COMPILE_REUSE_DISABLE_ENV_VAR,
    COMPILER_ENGINE_ENV_VAR,
    STAGE_CAPTURE_DIR_ENV_VAR,
)
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR

REUSE_FORMAT_VERSION: int = 1
REUSE_ENTRY_DIRECTORY_NAME: str = "project-reuse-v1"
REUSE_ENTRY_MAGIC: bytes = b"SQBREUSE1\n"
REUSE_ENTRY_SUFFIX: str = ".entry"
REUSE_STDOUT_SUFFIX: str = ".stdout"
REUSE_STDOUT_SEPARATOR: str = "-"
REUSE_ENTRY_LENGTH_BYTES: int = 8
REUSE_ENTRY_CHECKSUM_BYTES: int = 4
REUSE_ENTRY_BYTE_ORDER: Literal["big"] = "big"
REUSE_MAX_ENTRY_BYTES: int = 512 * 1024 * 1024
REUSE_MAX_STORED_ENTRIES: int = 8
REUSE_DISABLE_ENV_VAR: str = COMPILE_REUSE_DISABLE_ENV_VAR
REUSE_DISABLE_VALUE: str = "1"
REUSE_LOGGER_NAME: str = "sqlbuild.compile.reuse"
TRACKED_ENVIRONMENT_PREFIXES: tuple[str, ...] = ("SQLBUILD_", "SQB_")
UNTRACKED_ENVIRONMENT_NAMES: frozenset[str] = frozenset(
    {
        ANALYSIS_RECORD_DIR_ENV_VAR,
        COMPILE_REUSE_DISABLE_ENV_VAR,
        COMPILER_ENGINE_ENV_VAR,
        STAGE_CAPTURE_DIR_ENV_VAR,
    }
)
MISSING_ENVIRONMENT_VALUE: str = "\0missing"
MISSING_FILE_DIGEST: str = "\0missing"
PROJECT_CONFIG_FILENAMES: tuple[str, ...] = ("sqlbuild_project.toml", "sqlbuild_project.yml")

RACY_WINDOW_NS: int = 2_000_000_000
DIGEST_SIZE_BYTES: int = 16
READ_CHUNK_BYTES: int = 1024 * 1024
MISSING_PATH_MTIME_NS: int = -1
PROJECT_ROOT_PATH_MTIME_NS: int = -2
OUTPUT_FILE_DESCRIPTORS: tuple[int, ...] = (1, 2)

TARGET_DIRECTORY_NAME: str = "target"
COMPILED_DIRECTORY_NAME: str = "compiled"
EXCLUDED_ROOT_DIRECTORIES: frozenset[str] = frozenset(
    {
        "logs",
        "target",
        "venv",
        ".cache",
        ".fensu",
        ".hg",
        ".idea",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".sqlbuild",
        ".svn",
        ".tox",
        ".venv",
        ".vscode",
    }
)
EXCLUDED_DIRECTORIES: frozenset[str] = frozenset({".git", "__pycache__"})
PRESENCE_ONLY_FILE_SUFFIXES: tuple[str, ...] = (".duckdb", ".duckdb.wal")

FILE_KIND: str = "f"
FILE_LINK_KIND: str = "fl"
DIRECTORY_KIND: str = "d"
DIRECTORY_LINK_KIND: str = "dl"
BROKEN_LINK_KIND: str = "bl"
SPECIAL_FILE_KIND: str = "s"
PRESENCE_ONLY_KIND: str = "p"

COMPILE_TIMINGS_OPENING: str = '\n  "compile_timings": {'
COMPILE_TIMINGS_CLOSING: str = "\n  }"
JSON_OBJECT_OPENING: str = "{"
REUSE_HIT_TIMING: str = "project_reuse_hits"
REUSE_MISS_TIMING: str = "project_reuse_misses"
REUSE_BYPASS_TIMING: str = "project_reuse_bypasses"
REUSE_CHECK_TIMING: str = "project_reuse_check_ms"
TOTAL_TIMING: str = "total_ms"
REUSE_HIT_MESSAGE: str = "Inputs unchanged; reused the previous compile ({seconds:.1f} s)"
MILLISECONDS_PER_SECOND: int = 1000
REUSE_STORE_NOTICE_BYTES: int = 64 * 1024 * 1024
REUSE_STORE_NOTICE_PATHS: int = 100_000
BYTES_PER_MEBIBYTE: int = 1024 * 1024
REUSE_STORE_START_MESSAGE: str = (
    "Recording compile for reuse ({paths} paths, {mebibytes:.0f} MiB to hash)..."
)
REUSE_STORE_DONE_MESSAGE: str = "Recorded compile for reuse ({seconds:.1f} s)"
REUSE_STORE_SKIPPED_MESSAGE: str = (
    "Did not record compile for reuse: files changed while it ran ({seconds:.1f} s)"
)
COMPILE_ARTIFACT_WRITES: CompileArtifactWriteRegistry = CompileArtifactWriteRegistry(
    digest_size=DIGEST_SIZE_BYTES
)
