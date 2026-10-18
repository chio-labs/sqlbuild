from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT: Path = Path(__file__).resolve().parents[5]
REPOSITORY: str = "example-org/example-project"
CONTEXTS: dict[str, Any] = {
    "github": {
        "event_name": "pull_request",
        "repository": REPOSITORY,
        "event": {"pull_request": {"head": {"ref": "Release-Please--branches--main"}}},
    }
}


def read_verify_job() -> dict[str, Any]:
    """Return the repository Verify workflow's aggregate job."""
    workflow: Any = yaml.safe_load(
        (REPOSITORY_ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    )
    return workflow["jobs"]["verify"]


def write_workflows(
    *, root: Path, verify_job: dict[str, Any], release_checks_job: dict[str, Any]
) -> None:
    """Write a Verify workflow and a Release Please workflow holding the given jobs."""
    workflows: Path = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "verify.yml").write_text(
        yaml.safe_dump({"name": "Verify", "jobs": {"verify": verify_job}}), encoding="utf-8"
    )
    (workflows / "release-please.yml").write_text(
        yaml.safe_dump(
            {
                "name": "Release Please",
                "jobs": {
                    "release-please": {"runs-on": "ubuntu-24.04"},
                    "release-checks": release_checks_job,
                },
            }
        ),
        encoding="utf-8",
    )
