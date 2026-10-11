"""Where this invocation may leave a launch record for the native `sqb` executable."""

from pathlib import Path

from sqlbuild.cli.entry._helpers.launch_state import offered_launch_record


def launch_record_path() -> Path | None:
    """The launch record path `sqb` offered, unless an input outside its key was read."""

    return offered_launch_record()
