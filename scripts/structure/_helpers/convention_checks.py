"""Collect structure convention violations for selected paths."""

from __future__ import annotations

from pathlib import Path

from scripts.structure._helpers.filesystem import (
    collect_scoped_python_files,
    resolve_repo_root,
)
from scripts.structure._helpers.module_rules import (
    check_banned_generic_filename,
    check_constants_module,
    check_dev_tooling_location,
    check_helpers_module_name,
    check_helpers_package_layout,
    check_init_module,
    check_main_discarded_call_results,
    check_main_entry_name_collisions,
    check_main_package_layout,
    check_main_public_function_shape,
    check_model_declarations_outside_models,
    check_models_module,
    check_nested_runtime_package_direct_modules,
    check_nested_runtime_package_direct_subpackages,
    check_no_ad_hoc_dbt_graph_projection,
    check_no_ad_hoc_dbt_ref_scans,
    check_no_ad_hoc_selector_plus_parsing,
    check_no_internal_helper_exports,
    check_no_internal_reexport_modules,
    check_no_metadata_calls_in_loops,
    check_no_parameter_mutation_in_phase_helpers,
    check_no_raw_color_helper_imports,
    check_no_raw_runtime_diagnostics,
    check_no_relative_imports,
    check_no_singular_source_freshness_writer,
    check_no_source_freshness_insert_sql_outside_adapters,
    check_no_standalone_comments,
    check_no_swallowed_exception_probes,
    check_public_provider_module_shape,
    check_single_line_docstrings,
    check_single_project_macro_load_site,
    check_source_file_line_count,
    check_target_reuse_terminology,
    check_top_level_domain_direct_modules,
    check_top_level_domain_role_placement,
    check_types_module,
    parse_python_module,
)
from scripts.structure._helpers.package_rules import (
    check_adapter_class_entry_module_shape,
    check_adapter_contract_implementation_shortcuts,
    check_classes_module_name,
    check_classes_package_module_shape,
    check_client_module_shape,
    check_constants_outside_constants,
    check_cross_package_internal_imports,
    check_entry_module_shape,
    check_exception_declarations_outside_exceptions,
    check_helpers_package_shape,
    check_integration_adapter_helpers_module,
    check_integrations_package_structure,
    check_no_sibling_package_imports,
    check_private_definition_ordering,
    check_shared_package_imports,
    check_shared_package_structure,
    check_type_declarations_outside_types,
)
from scripts.structure.models import Violation


def collect_violations(*, paths: list[Path], repo_root: Path | None = None) -> list[Violation]:
    """Collect structure convention violations for the provided paths."""

    target_paths: list[Path] = (
        [path.resolve() for path in paths] if paths else _default_target_paths()
    )
    actual_repo_root: Path = (
        repo_root.resolve() if repo_root is not None else resolve_repo_root(target_paths)
    )
    python_files: list[Path] = collect_scoped_python_files(
        repo_root=actual_repo_root, paths=target_paths
    )

    violations: list[Violation] = []
    for file_path in python_files:
        module: object = parse_python_module(file_path)
        violations.extend(
            check_source_file_line_count(repo_root=actual_repo_root, file_path=file_path)
        )
        violations.extend(check_no_relative_imports(file_path=file_path, module=module))
        violations.extend(
            check_dev_tooling_location(repo_root=actual_repo_root, file_path=file_path)
        )
        violations.extend(
            check_top_level_domain_role_placement(repo_root=actual_repo_root, file_path=file_path)
        )
        violations.extend(
            check_top_level_domain_direct_modules(repo_root=actual_repo_root, file_path=file_path)
        )
        violations.extend(
            check_public_provider_module_shape(
                repo_root=actual_repo_root, file_path=file_path, module=module
            )
        )
        violations.extend(
            check_nested_runtime_package_direct_modules(
                repo_root=actual_repo_root, file_path=file_path
            )
        )
        violations.extend(
            check_nested_runtime_package_direct_subpackages(
                repo_root=actual_repo_root, file_path=file_path
            )
        )
        violations.extend(check_banned_generic_filename(file_path))
        violations.extend(check_helpers_module_name(file_path))
        violations.extend(check_classes_module_name(file_path))
        violations.extend(
            check_classes_package_module_shape(
                repo_root=actual_repo_root, file_path=file_path, module=module
            )
        )
        violations.extend(check_init_module(file_path=file_path, module=module))
        violations.extend(check_entry_module_shape(file_path=file_path, module=module))
        violations.extend(check_main_public_function_shape(file_path=file_path, module=module))
        violations.extend(check_main_discarded_call_results(file_path=file_path, module=module))
        violations.extend(
            check_main_entry_name_collisions(repo_root=actual_repo_root, file_path=file_path)
        )
        violations.extend(check_types_module(file_path=file_path, module=module))
        violations.extend(check_models_module(file_path=file_path, module=module))
        violations.extend(check_constants_module(file_path=file_path, module=module))
        violations.extend(
            check_model_declarations_outside_models(file_path=file_path, module=module)
        )
        violations.extend(check_no_raw_color_helper_imports(file_path=file_path, module=module))
        violations.extend(
            check_no_internal_reexport_modules(
                repo_root=actual_repo_root, file_path=file_path, module=module
            )
        )
        violations.extend(
            check_no_internal_helper_exports(
                repo_root=actual_repo_root, file_path=file_path, module=module
            )
        )
        violations.extend(check_no_raw_runtime_diagnostics(file_path=file_path, module=module))
        violations.extend(check_target_reuse_terminology(file_path))
        violations.extend(check_no_swallowed_exception_probes(file_path=file_path, module=module))
        violations.extend(check_no_metadata_calls_in_loops(file_path=file_path, module=module))
        violations.extend(
            check_no_singular_source_freshness_writer(file_path=file_path, module=module)
        )
        violations.extend(check_no_source_freshness_insert_sql_outside_adapters(file_path))
        violations.extend(check_no_ad_hoc_dbt_ref_scans(file_path=file_path, module=module))
        violations.extend(check_no_ad_hoc_dbt_graph_projection(file_path=file_path, module=module))
        violations.extend(check_no_ad_hoc_selector_plus_parsing(file_path=file_path, module=module))
        violations.extend(check_single_line_docstrings(file_path=file_path, module=module))
        violations.extend(check_single_project_macro_load_site(file_path=file_path, module=module))
        violations.extend(check_no_standalone_comments(file_path))
        violations.extend(
            check_no_parameter_mutation_in_phase_helpers(
                repo_root=actual_repo_root, file_path=file_path, module=module
            )
        )
        violations.extend(check_private_definition_ordering(file_path=file_path, module=module))
        violations.extend(check_type_declarations_outside_types(file_path=file_path, module=module))
        violations.extend(
            check_exception_declarations_outside_exceptions(file_path=file_path, module=module)
        )
        violations.extend(check_constants_outside_constants(file_path=file_path, module=module))
        violations.extend(
            check_helpers_package_shape(repo_root=actual_repo_root, file_path=file_path)
        )
        violations.extend(
            check_helpers_package_layout(repo_root=actual_repo_root, file_path=file_path)
        )
        violations.extend(
            check_main_package_layout(repo_root=actual_repo_root, file_path=file_path)
        )
        violations.extend(
            check_shared_package_structure(repo_root=actual_repo_root, file_path=file_path)
        )
        violations.extend(
            check_integrations_package_structure(repo_root=actual_repo_root, file_path=file_path)
        )
        violations.extend(
            check_integration_adapter_helpers_module(
                repo_root=actual_repo_root, file_path=file_path
            )
        )
        violations.extend(
            check_client_module_shape(
                repo_root=actual_repo_root, file_path=file_path, module=module
            )
        )
        violations.extend(
            check_adapter_class_entry_module_shape(
                repo_root=actual_repo_root, file_path=file_path, module=module
            )
        )
        violations.extend(
            check_adapter_contract_implementation_shortcuts(
                repo_root=actual_repo_root, file_path=file_path, module=module
            )
        )
        violations.extend(
            check_no_sibling_package_imports(
                repo_root=actual_repo_root, file_path=file_path, module=module
            )
        )
        violations.extend(
            check_shared_package_imports(
                repo_root=actual_repo_root, file_path=file_path, module=module
            )
        )
        violations.extend(
            check_cross_package_internal_imports(
                repo_root=actual_repo_root, file_path=file_path, module=module
            )
        )

    return sorted(
        violations, key=lambda violation: (str(violation.path), violation.line or 0, violation.code)
    )


def _default_target_paths() -> list[Path]:
    return [Path("src/sqlbuild").resolve(), Path("scripts").resolve()]
