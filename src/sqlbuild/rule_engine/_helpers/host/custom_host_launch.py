"""Start the custom-rule host with a scrubbed environment and a fixed hash seed."""

from __future__ import annotations

import os
import subprocess
import sys

from sqlbuild.rule_engine.constants import (
    CUSTOM_HOST_EXEC_OS_NAME,
    CUSTOM_HOST_HASH_SEED,
    CUSTOM_HOST_MODULE,
    CUSTOM_HOST_STARTUP_ENVIRONMENT,
)


def main() -> int:
    """Replace this launcher with the host, or relay to it where exec is unavailable."""

    environment: dict[str, str] = {
        name: os.environ[name] for name in CUSTOM_HOST_STARTUP_ENVIRONMENT if name in os.environ
    }
    environment["PYTHONHASHSEED"] = CUSTOM_HOST_HASH_SEED
    environment["PYTHONUTF8"] = "1"
    arguments: list[str] = [sys.executable, "-P", "-m", CUSTOM_HOST_MODULE]
    if os.name == CUSTOM_HOST_EXEC_OS_NAME:
        os.execve(sys.executable, arguments, environment)
    return subprocess.run(arguments, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
