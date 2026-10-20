import pytest

from scripts.build_features._helpers.tree import parse_cargo_tree
from scripts.build_features.models import ResolvedCrate
from tests.unit.scripts.build_features._helpers._test_types import ParseTreeTestCase

CLI: ResolvedCrate = ResolvedCrate(package="sqlbuild-cli v0.1.0", side="target")


@pytest.mark.parametrize(
    "test_case",
    [
        ParseTreeTestCase(
            description="normal dependencies compile for the target",
            output=(
                "sqlbuild-cli v0.1.0 (/work/crates/sqlbuild-cli)|\n"
                "├── memchr v2.8.3|alloc,std\n"
                "└── regex v1.12.2|default,std\n"
                "    └── memchr v2.8.3|alloc,std\n"
            ),
            expected_crates={
                CLI: frozenset({""}),
                ResolvedCrate(package="memchr v2.8.3", side="target"): frozenset({"alloc,std"}),
                ResolvedCrate(package="regex v1.12.2", side="target"): frozenset({"default,std"}),
            },
        ),
        ParseTreeTestCase(
            description="proc-macros and their dependencies compile for the host",
            output=(
                "sqlbuild-cli v0.1.0 (/work/crates/sqlbuild-cli)|\n"
                "├── serde v1.0.229|default,derive\n"
                "│   └── serde_derive v1.0.229 (proc-macro)|default\n"
                "│       └── syn v2.0.119|full\n"
                "└── syn v2.0.119|parsing\n"
            ),
            expected_crates={
                CLI: frozenset({""}),
                ResolvedCrate(package="serde v1.0.229", side="target"): frozenset(
                    {"default,derive"}
                ),
                ResolvedCrate(package="serde_derive v1.0.229", side="host"): frozenset({"default"}),
                ResolvedCrate(package="syn v2.0.119", side="host"): frozenset({"full"}),
                ResolvedCrate(package="syn v2.0.119", side="target"): frozenset({"parsing"}),
            },
        ),
        ParseTreeTestCase(
            description="build dependencies compile for the host until the next sibling",
            output=(
                "sqlbuild-cli v0.1.0 (/work/crates/sqlbuild-cli)|\n"
                "├── blake3 v1.8.7|std\n"
                "│   ├── cfg-if v1.0.4|\n"
                "│   [build-dependencies]\n"
                "│   └── cc v1.4.4|\n"
                "│       └── shlex v2.0.1|std\n"
                "└── libc v0.2.189|std\n"
            ),
            expected_crates={
                CLI: frozenset({""}),
                ResolvedCrate(package="blake3 v1.8.7", side="target"): frozenset({"std"}),
                ResolvedCrate(package="cfg-if v1.0.4", side="target"): frozenset({""}),
                ResolvedCrate(package="cc v1.4.4", side="host"): frozenset({""}),
                ResolvedCrate(package="shlex v2.0.1", side="host"): frozenset({"std"}),
                ResolvedCrate(package="libc v0.2.189", side="target"): frozenset({"std"}),
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cargo_tree_output_when_parsing_then_splits_host_and_target_features(
    test_case: ParseTreeTestCase,
) -> None:
    assert parse_cargo_tree(test_case.output) == test_case.expected_crates
