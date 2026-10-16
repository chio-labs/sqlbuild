from pathlib import Path
from types import SimpleNamespace
from typing import cast

from sqlbuild._native import DiscoveredProjectInputs


def build_selector_discovered_inputs(
    *, tests: frozenset[str], resources: frozenset[str]
) -> DiscoveredProjectInputs:
    """Discovered inputs naming these unit tests and, as model files, these resources."""

    inputs: SimpleNamespace = SimpleNamespace(
        test_files=(
            SimpleNamespace(
                relative_path=Path("tests/unit_tests.sql"),
                blocks=tuple(SimpleNamespace(name=name) for name in sorted(tests)),
            ),
        ),
        model_files=tuple(
            SimpleNamespace(file_path=Path(f"models/{name}.sql")) for name in sorted(resources)
        ),
        schema_files=(),
        source_files=(),
        seed_files=(),
        sql_function_files=(),
        python_function_files=(),
        loader_functions=(),
        task_functions=(),
        asset_functions=(),
        check_functions=(),
    )
    return cast(DiscoveredProjectInputs, inputs)
