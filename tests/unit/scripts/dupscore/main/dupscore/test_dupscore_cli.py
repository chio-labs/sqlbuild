from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.dupscore.main.dupscore import dupscore
from tests.unit.scripts.dupscore.main.build_clone_report.helpers import (
    PYTHON_BASE,
    seed_repository,
)
from tests.unit.scripts.dupscore.main.build_report.helpers import (
    commit_all,
    initialize_repo,
    write_project_files,
)
from tests.unit.scripts.dupscore.main.dupscore._test_types import (
    CliHelpTestCase,
    CliJsonTestCase,
    CliSinceTestCase,
    CliTextTestCase,
    CliUsageErrorTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CliJsonTestCase(
            description="json output lists ranked clusters with member locations",
            arguments=("clones", "--json", "--top", "1"),
            expected_total_clusters=2,
            expected_unit_counts={"python": 5, "rust": 5},
            expected_cluster_keys=frozenset(
                {
                    "category",
                    "duplicated_tokens",
                    "links",
                    "members",
                    "rank",
                    "similarity_max",
                    "similarity_min",
                }
            ),
            expected_member_keys=frozenset(
                {"change", "end_line", "language", "name", "path", "start_line", "tokens"}
            ),
            expected_progress_fragments=(
                "detecting function clones",
                "found 2 clone clusters across 10 units",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seeded_tree_when_running_json_cli_then_prints_cluster_document(
    test_case: CliJsonTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root: Path = seed_repository(tmp_path)

    exit_code: int = dupscore([*test_case.arguments, "--repo-root", str(repo_root)])

    output: str
    errors: str
    output, errors = capsys.readouterr()
    payload: dict[str, Any] = json.loads(output)
    clusters: list[dict[str, Any]] = payload["clusters"]
    members: list[dict[str, Any]] = clusters[0]["members"]
    assert exit_code == 0
    assert payload["total_clusters"] == test_case.expected_total_clusters
    assert payload["unit_counts"] == test_case.expected_unit_counts
    assert payload["since"] is None
    assert [set(cluster) for cluster in clusters] == [set(test_case.expected_cluster_keys)]
    assert all(set(member) == test_case.expected_member_keys for member in members)
    assert all(fragment in errors for fragment in test_case.expected_progress_fragments)


@pytest.mark.parametrize(
    "test_case",
    [
        CliTextTestCase(
            description="default mode prints python clone locations",
            arguments=("--lang", "python"),
            expected_prefix="dupscore clones: 1 clusters (python 5 units;",
            expected_fragments=(
                "src/sqlbuild/alpha/orders.py:2-15 summarize_orders",
                "src/sqlbuild/beta/inventory.py:4-16 InventoryReport.rank_products",
            ),
            absent_fragment="crates/",
        ),
        CliTextTestCase(
            description="rust mode prints impl-qualified names",
            arguments=("clones", "--lang", "rust"),
            expected_prefix="dupscore clones: 1 clusters (rust 5 units;",
            expected_fragments=("crates/demo-rules/src/orders.rs:6-20 OrderBook::rank_orders",),
            absent_fragment="src/sqlbuild/",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_seeded_tree_when_running_text_cli_then_prints_locations(
    test_case: CliTextTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root: Path = seed_repository(tmp_path)

    exit_code: int = dupscore([*test_case.arguments, "--repo-root", str(repo_root)])

    output: str = capsys.readouterr().out
    assert exit_code == 0
    assert output.startswith(test_case.expected_prefix)
    assert all(fragment in output for fragment in test_case.expected_fragments)
    assert test_case.absent_fragment not in output


@pytest.mark.parametrize(
    "test_case",
    [
        CliSinceTestCase(
            description="branch copy is the only new member",
            new_files={"src/sqlbuild/delta/branch_copy.py": PYTHON_BASE},
            expected_fragments=(
                ": 1 clusters (",
                "src/sqlbuild/delta/branch_copy.py:2-15 summarize_orders (118 tokens) [new]",
            ),
            expected_new_markers=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_branch_copy_when_running_cli_since_base_then_marks_new_member(
    test_case: CliSinceTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root: Path = seed_repository(tmp_path)
    initialize_repo(repo_root)
    base_revision: str = commit_all(repo_root=repo_root, message="seed clones")
    write_project_files(repo_root=repo_root, files=test_case.new_files)

    exit_code: int = dupscore(["--repo-root", str(repo_root), "--since", base_revision])

    output: str = capsys.readouterr().out
    assert exit_code == 0
    assert output.startswith(f"dupscore clones changed since {base_revision}")
    assert all(fragment in output for fragment in test_case.expected_fragments)
    assert output.count("[new]") == test_case.expected_new_markers


@pytest.mark.parametrize(
    "test_case",
    [
        CliUsageErrorTestCase(
            description="clone options are rejected in report mode",
            arguments=("report", "--min-tokens", "10"),
            expected_error_fragment="--min-tokens only apply to the clones mode",
        ),
        CliUsageErrorTestCase(
            description="similarity outside the unit interval is rejected",
            arguments=("clones", "--min-similarity", "1.5"),
            expected_error_fragment="--min-similarity must be in (0, 1]",
        ),
        CliUsageErrorTestCase(
            description="unknown languages are rejected",
            arguments=("--lang", "go"),
            expected_error_fragment="invalid choice: 'go'",
        ),
        CliUsageErrorTestCase(
            description="domain filter is rejected in clones mode",
            arguments=("--domain", "sqlbuild.compiler"),
            expected_error_fragment="--domain only applies to the report mode",
        ),
        CliUsageErrorTestCase(
            description="clones mode takes no package names",
            arguments=("clones", "sqlbuild.alpha"),
            expected_error_fragment="takes no positional package names",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_arguments_when_running_cli_then_exits_with_usage_error(
    test_case: CliUsageErrorTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        _ = dupscore(list(test_case.arguments))

    assert raised.value.code == 2
    assert test_case.expected_error_fragment in capsys.readouterr().err


@pytest.mark.parametrize(
    "test_case",
    [
        CliHelpTestCase(
            description="help lists the clone mode and its options",
            expected_fragments=("clones", "report", "--include-tests", "--since", "--path"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_help_flag_when_running_cli_then_lists_clone_mode(
    test_case: CliHelpTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        _ = dupscore(["--help"])

    help_text: str = capsys.readouterr().out
    assert raised.value.code == 0
    assert all(fragment in help_text for fragment in test_case.expected_fragments)
