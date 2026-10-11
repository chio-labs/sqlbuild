"""Stop this invocation from leaving a launch record."""

from sqlbuild.cli.entry._helpers.launch_state import withhold_offered_launch_record


def withhold_launch_record() -> None:
    """Withhold the launch record: `sqb` cannot replay what this invocation also depends on."""

    _ = withhold_offered_launch_record()
