"""Real CLI coverage of cache-safe custom Rules evaluated by the guarded host."""

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.rules._test_types import (
    HashSeedCase,
    HermeticRuleCase,
    ModuleStatementEditCase,
    NonHermeticRuleCase,
    ProjectTreeCacheCase,
    ScrubbedEnvironmentCase,
    WorkingDirectoryCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.rules.helpers import (
    custom_rule_codes,
    custom_rule_diagnostics,
    custom_rule_messages,
    custom_rule_paths,
    custom_rule_source,
    rule_cache_hits,
    run_compile_cli,
    string_set_order,
    write_custom_rule_project,
)

_ENTITY_NAMES: tuple[str, ...] = (
    "customers",
    "orders",
    "products",
    "inventory",
    "fulfillment",
    "support_tickets",
    "shipments",
    "returns",
)


@pytest.mark.parametrize(
    "test_case",
    [
        HermeticRuleCase(
            description="pure rule using re.compile, fnmatch, and json is evaluated",
            code="XSQBRPURE001",
            files=(
                (
                    "rules/orders.py",
                    custom_rule_source(
                        code="XSQBRPURE001",
                        header=(
                            "import fnmatch\nimport json\nimport re\n\n"
                            "from sqlbuild.rules import Finding, Model, RuleContext, rule\n\n"
                            '_ORDERS = re.compile(r"^ord")\n'
                        ),
                        body=(
                            '    payload = json.loads(json.dumps({"name": model.name}))\n'
                            '    matched = fnmatch.fnmatchcase(payload["name"], "*ers")\n'
                            "    if matched and _ORDERS.match(model.name):\n"
                            "        return [ctx.finding(subject=model)]\n"
                            "    return []\n"
                        ),
                    ),
                ),
            ),
            expected_rule_codes=("XSQBRPURE001",),
        ),
        HermeticRuleCase(
            description="unrelated rules file importing a disallowed module is ignored",
            code="XSQBRNAME001",
            files=(
                (
                    "rules/orders.py",
                    custom_rule_source(
                        code="XSQBRNAME001",
                        body="    return [ctx.finding(subject=model)]\n",
                    ),
                ),
                (
                    "rules/scratch/test_orders.py",
                    "import subprocess\n\n\ndef test_orders() -> None:\n"
                    '    assert subprocess.run(["true"], check=False).returncode == 0\n',
                ),
            ),
            expected_rule_codes=("XSQBRNAME001",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_hermetic_rule_when_compiling_then_rule_is_evaluated(
    tmp_path: Path, test_case: HermeticRuleCase
) -> None:
    write_custom_rule_project(
        project_dir=tmp_path, selected_rules=(test_case.code,), files=test_case.files
    )

    result: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "non-hermetic" not in result.stderr
    assert custom_rule_codes(result) == test_case.expected_rule_codes


@pytest.mark.parametrize(
    "test_case",
    [
        NonHermeticRuleCase(
            description="directory listing through an allowed module is rejected",
            code="XSQBRLIST001",
            source=custom_rule_source(
                code="XSQBRLIST001",
                body='    return [ctx.finding(subject=model)] * len(pathlib.os.listdir("models"))\n',
            ),
            expected_line=8,
            expected_action="listing a directory",
        ),
        NonHermeticRuleCase(
            description="file opened through an indirect builtin spelling is rejected",
            code="XSQBROPEN001",
            source=custom_rule_source(
                code="XSQBROPEN001",
                body=(
                    '    reader = getattr(pathlib, "__builtins__")["op" + "en"]\n'
                    '    reader("models/orders.sql").close()\n'
                    "    return []\n"
                ),
            ),
            expected_line=9,
            expected_action="opening 'models/orders.sql'",
        ),
        NonHermeticRuleCase(
            description="file read through an aliased method is rejected even when caught",
            code="XSQBROPEN002",
            source=custom_rule_source(
                code="XSQBROPEN002",
                body=(
                    "    reader = pathlib.Path.read_text\n"
                    "    try:\n"
                    '        reader(pathlib.Path("models/orders.sql"))\n'
                    "    except Exception:\n"
                    "        pass\n"
                    "    return []\n"
                ),
            ),
            expected_line=10,
            expected_action="opening 'models/orders.sql'",
        ),
        NonHermeticRuleCase(
            description="command run through an allowed module is rejected",
            code="XSQBRCMD001",
            source=custom_rule_source(
                code="XSQBRCMD001",
                body='    pathlib.os.system("true")\n    return []\n',
            ),
            expected_line=8,
            expected_action="running a command",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_hermetic_rule_when_compiling_then_fails_naming_rule_and_location(
    tmp_path: Path, test_case: NonHermeticRuleCase
) -> None:
    write_custom_rule_project(
        project_dir=tmp_path,
        selected_rules=(test_case.code,),
        files=(("rules/orders.py", test_case.source),),
    )

    result: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    expected: str = (
        f"non-hermetic custom rule {test_case.code} at rules/orders.py:{test_case.expected_line}: "
        f"{test_case.expected_action} is not allowed"
    )
    assert expected in result.stderr, result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        ScrubbedEnvironmentCase(
            description="environment read through an allowed module sees no parent variables",
            code="XSQBRENV001",
            source=custom_rule_source(
                code="XSQBRENV001",
                body=(
                    '    flag = pathlib.os.environ.get("ORDERS_RULE_FLAG")\n'
                    "    return [ctx.finding(subject=model)] * int(bool(flag))\n"
                ),
            ),
            parent_environment=(("ORDERS_RULE_FLAG", "enabled"),),
            expected_returncode=0,
            expected_rule_codes=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_parent_environment_variable_when_rule_reads_environment_then_host_is_scrubbed(
    tmp_path: Path, test_case: ScrubbedEnvironmentCase
) -> None:
    write_custom_rule_project(
        project_dir=tmp_path,
        selected_rules=(test_case.code,),
        files=(("rules/orders.py", test_case.source),),
    )

    result: subprocess.CompletedProcess[str] = run_compile_cli(
        tmp_path, environment=test_case.parent_environment
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    assert custom_rule_codes(result) == test_case.expected_rule_codes


@pytest.mark.parametrize(
    "test_case",
    [
        HashSeedCase(
            description="string set iteration follows the fixed host hash seed",
            code="XSQBRSET001",
            names=_ENTITY_NAMES,
            expected_hash_seed="0",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rule_iterating_a_string_set_when_compiling_then_order_uses_fixed_hash_seed(
    tmp_path: Path, test_case: HashSeedCase
) -> None:
    write_custom_rule_project(
        project_dir=tmp_path,
        selected_rules=(test_case.code,),
        files=(
            (
                "rules/orders.py",
                custom_rule_source(
                    code=test_case.code,
                    body=(
                        f"    names = {{*{list(test_case.names)!r}}}\n"
                        '    return [ctx.finding(subject=model, message=",".join(names))]\n'
                    ),
                ),
            ),
        ),
    )

    result: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    (finding,) = custom_rule_diagnostics(result)
    assert string_set_order(names=test_case.names, hash_seed=test_case.expected_hash_seed) in str(
        finding["message"]
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectTreeCacheCase(
            description="mediated read and glob work and invalidate cached results",
            code="XSQBRTREE001",
            source=custom_rule_source(
                code="XSQBRTREE001",
                body=(
                    '    policy = ctx.project.tree.read_text("rules/orders_policy.yaml")\n'
                    '    models = ctx.project.tree.glob("models/*.sql")\n'
                    '    required = "required: true" in policy and len(models) > 1\n'
                    "    return [ctx.finding(subject=model)] * int(required)\n"
                ),
            ),
            policy_path="rules/orders_policy.yaml",
            added_model_path="models/customers.sql",
            expected_paths_after_glob_change=("models/customers.sql", "models/orders.sql"),
            expected_minimum_cache_hits=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_tree_rule_when_inputs_change_then_reads_work_and_cache_invalidates(
    tmp_path: Path, test_case: ProjectTreeCacheCase
) -> None:
    write_custom_rule_project(
        project_dir=tmp_path,
        selected_rules=(test_case.code,),
        files=(
            (test_case.policy_path, "required: true\n"),
            ("rules/orders.py", test_case.source),
        ),
    )

    single_model: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path)
    (tmp_path / test_case.added_model_path).write_text(
        'MODEL (description "Customers");\nSELECT 1 AS customer_id\n', encoding="utf-8"
    )
    two_models: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path)
    (tmp_path / test_case.policy_path).write_text("required: false\n", encoding="utf-8")
    relaxed: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path)
    repeated: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path)

    assert single_model.returncode == 0, single_model.stdout + single_model.stderr
    assert custom_rule_paths(single_model) == ()
    assert two_models.returncode == 1, two_models.stdout + two_models.stderr
    assert custom_rule_paths(two_models) == test_case.expected_paths_after_glob_change
    assert relaxed.returncode == 0, relaxed.stdout + relaxed.stderr
    assert custom_rule_paths(relaxed) == ()
    assert rule_cache_hits(repeated) >= test_case.expected_minimum_cache_hits


@pytest.mark.parametrize(
    "test_case",
    [
        ModuleStatementEditCase(
            description="appended module statement invalidates the cached rule result",
            code="XSQBRSTMT001",
            source=custom_rule_source(
                code="XSQBRSTMT001",
                header=(
                    "from sqlbuild.rules import Finding, Model, RuleContext, rule\n\n"
                    "_NAMES: set[str] = set()\n"
                ),
                body="    return [ctx.finding(subject=model)] * int(model.name in _NAMES)\n",
            ),
            appended_statement='\n_NAMES.add("orders")\n',
            expected_rule_codes_before_edit=(),
            expected_rule_codes_after_edit=("XSQBRSTMT001",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cached_rule_when_module_statement_is_appended_then_rule_is_reevaluated(
    tmp_path: Path, test_case: ModuleStatementEditCase
) -> None:
    write_custom_rule_project(
        project_dir=tmp_path,
        selected_rules=(test_case.code,),
        files=(("rules/orders.py", test_case.source),),
    )
    before: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path)
    rule_file: Path = tmp_path / "rules" / "orders.py"
    rule_file.write_text(test_case.source + test_case.appended_statement, encoding="utf-8")

    after: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path)

    assert custom_rule_codes(before) == test_case.expected_rule_codes_before_edit
    assert custom_rule_codes(after) == test_case.expected_rule_codes_after_edit, after.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        WorkingDirectoryCase(
            description="rules observe the project directory wherever sqb is invoked",
            code="XSQBRCWD001",
            source=custom_rule_source(
                code="XSQBRCWD001",
                body="    return [ctx.finding(subject=model, message=str(pathlib.Path.cwd()))]\n",
            ),
            invocation_directories=("invoked/first", "invoked/second"),
            expected_working_directory="project",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rule_observing_cwd_when_invoked_from_different_directories_then_value_is_fixed(
    tmp_path: Path, test_case: WorkingDirectoryCase
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    write_custom_rule_project(
        project_dir=project_dir,
        selected_rules=(test_case.code,),
        files=(("rules/orders.py", test_case.source),),
        configuration="\n[rules.cache]\nenabled = false\n",
    )
    messages: list[tuple[str, ...]] = []
    for directory in test_case.invocation_directories:
        invocation: Path = tmp_path / directory
        invocation.mkdir(parents=True)
        messages.append(
            custom_rule_messages(run_compile_cli(project_dir, working_directory=invocation))
        )

    expected: str = str((tmp_path / test_case.expected_working_directory).resolve())
    assert messages == [(expected,)] * len(test_case.invocation_directories)
