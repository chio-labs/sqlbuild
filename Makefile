SHELL := /bin/bash

.PHONY: verify verify-quick verify-pg coverage cli-preview rust-check \
	check-e2e-shards test-e2e-duckdb test-e2e-duckdb-build-core \
	test-e2e-duckdb-build-incremental test-e2e-duckdb-build-virtual \
	test-e2e-duckdb-cli-data test-e2e-duckdb-cli test-e2e-duckdb-virtual \
	test-e2e-duckdb-integrations test-e2e-performance

format:
	uv run ruff format .


SCENE ?= all
PREVIEW_ARGS ?=

cli-preview:
	uv run python -m scripts.preview_cli $(SCENE) $(PREVIEW_ARGS)


lint:
	uv run ruff check --fix .


type:
	uv run ty check src tests


rust-check:
	cargo fmt --all --check
	cargo clippy --workspace --all-targets --all-features -- -D warnings
	cargo run -p sqlbuild-structure-checker --quiet -- --config fensu-structure.toml
	cargo test --workspace --all-features


test:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests/unit tests/integration -m "not real_warehouse and not dbt" -vv --color=yes -n auto --dist loadfile 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


test-all:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-all-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests -m "not real_warehouse and not dbt" -vv --color=yes -n auto --dist loadfile 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_ALL_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


E2E_DUCKDB_MARKERS := not real_warehouse and not dbt and not performance
E2E_DUCKDB_PYTEST_ARGS := -m "$(E2E_DUCKDB_MARKERS)" -vv --color=yes -n auto --dist loadfile

E2E_DUCKDB_BUILD_CORE_PATHS := \
	tests/e2e/src/sqlbuild/cli/commands/main/build/no_tests_no_audits \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_audit_failures.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_build.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_compile_json_behavior.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_dag_json_behavior.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_enum_contract.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_expression_sources.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_lifecycle_commands.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_manifest_artifact_gating.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_no_tests_no_audits_flags.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_plan_command_surface.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_python_hooks.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_query_change_tracking.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_query_propagation.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_remove_column_semantics.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_reusable_model_schemas.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_runtime_artifact_preservation.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_schema_backfill_behavior.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_selector_surface.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_table_function_dependency.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_template_expressions.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_validation_failures.py

E2E_DUCKDB_BUILD_INCREMENTAL_PATHS := \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_append_cursor_build.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_capped_microbatch_build.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_concurrent_microbatch_build.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_cursor_runtime_failures.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_loader_watermark_build.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_microbatch_direct_lifecycle.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_microbatch_failure_windows.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_microbatch_replay_backfill_lifecycle.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_mixed_timestamp_grain_replay.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_model_backed_cursor_build.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_seed_watermark_build.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_snapshot_build.py

E2E_DUCKDB_BUILD_VIRTUAL_PATHS := \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_virtual_build_state.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_virtual_incremental_build.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_virtual_microbatch_lifecycle.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_virtual_mode_guard.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_virtual_promote.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_virtual_python_build.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_virtual_rollback.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_virtual_seed_build.py \
	tests/e2e/src/sqlbuild/cli/commands/main/build/test_virtual_source_freshness_build.py

E2E_DUCKDB_CLI_DATA_PATHS := \
	tests/e2e/src/sqlbuild/cli/commands/main/load \
	tests/e2e/src/sqlbuild/cli/commands/main/providers \
	tests/e2e/src/sqlbuild/cli/commands/main/scenario

E2E_DUCKDB_CLI_PATHS := \
	tests/e2e/scripts/cli_preview \
	tests/e2e/src/sqlbuild/cli/commands/main/adapters \
	tests/e2e/src/sqlbuild/cli/commands/main/audit \
	tests/e2e/src/sqlbuild/cli/commands/main/bigquery \
	tests/e2e/src/sqlbuild/cli/commands/main/check \
	tests/e2e/src/sqlbuild/cli/commands/main/compile \
	tests/e2e/src/sqlbuild/cli/commands/main/databricks \
	tests/e2e/src/sqlbuild/cli/commands/main/dbt \
	tests/e2e/src/sqlbuild/cli/commands/main/debug \
	tests/e2e/src/sqlbuild/cli/commands/main/freshness \
	tests/e2e/src/sqlbuild/cli/commands/main/init \
	tests/e2e/src/sqlbuild/cli/commands/main/kata \
	tests/e2e/src/sqlbuild/cli/commands/main/lineage \
	tests/e2e/src/sqlbuild/cli/commands/main/motherduck \
	tests/e2e/src/sqlbuild/cli/commands/main/playground \
	tests/e2e/src/sqlbuild/cli/commands/main/postgres \
	tests/e2e/src/sqlbuild/cli/commands/main/query \
	tests/e2e/src/sqlbuild/cli/commands/main/scope \
	tests/e2e/src/sqlbuild/cli/commands/main/seed \
	tests/e2e/src/sqlbuild/cli/commands/main/skills \
	tests/e2e/src/sqlbuild/cli/commands/main/snowflake \
	tests/e2e/src/sqlbuild/cli/commands/main/sqlserver \
	tests/e2e/src/sqlbuild/cli/commands/main/test

E2E_DUCKDB_VIRTUAL_PATHS := \
	tests/e2e/src/sqlbuild/cli/commands/main/clone \
	tests/e2e/src/sqlbuild/cli/commands/main/diff \
	tests/e2e/src/sqlbuild/cli/commands/main/janitor \
	tests/e2e/src/sqlbuild/cli/commands/main/plan \
	tests/e2e/src/sqlbuild/cli/commands/main/reconcile \
	tests/e2e/src/sqlbuild/cli/commands/main/state

E2E_DUCKDB_INTEGRATIONS_PATHS := tests/e2e/src/sqlbuild/integrations

E2E_DUCKDB_PATHS := \
	$(E2E_DUCKDB_BUILD_CORE_PATHS) \
	$(E2E_DUCKDB_BUILD_INCREMENTAL_PATHS) \
	$(E2E_DUCKDB_BUILD_VIRTUAL_PATHS) \
	$(E2E_DUCKDB_CLI_DATA_PATHS) \
	$(E2E_DUCKDB_CLI_PATHS) \
	$(E2E_DUCKDB_VIRTUAL_PATHS) \
	$(E2E_DUCKDB_INTEGRATIONS_PATHS)

define run_e2e_duckdb
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/$(1)-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	echo "Reproduce locally: make $(1)"; \
	echo 'Pytest scope: $(2) -m "$(E2E_DUCKDB_MARKERS)"'; \
	{ \
		status=0; \
		run_step() { \
			label="$$1"; shift; \
			echo; \
			echo "==> $$label"; \
			"$$@"; \
			rc=$$?; \
			if [ $$rc -ne 0 ]; then \
				echo "STEP_FAILED[$$rc]: $$label"; \
				if [ $$status -eq 0 ]; then status=$$rc; fi; \
			fi; \
		}; \
		run_step "$(1)" env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest $(2) $(E2E_DUCKDB_PYTEST_ARGS); \
		exit $$status; \
	} 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_E2E_DUCKDB_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status
endef

test-e2e-duckdb:
	$(call run_e2e_duckdb,$@,$(E2E_DUCKDB_PATHS))

test-e2e-duckdb-build-core:
	$(call run_e2e_duckdb,$@,$(E2E_DUCKDB_BUILD_CORE_PATHS))

test-e2e-duckdb-build-incremental:
	$(call run_e2e_duckdb,$@,$(E2E_DUCKDB_BUILD_INCREMENTAL_PATHS))

test-e2e-duckdb-build-virtual:
	$(call run_e2e_duckdb,$@,$(E2E_DUCKDB_BUILD_VIRTUAL_PATHS))

test-e2e-duckdb-cli-data:
	$(call run_e2e_duckdb,$@,$(E2E_DUCKDB_CLI_DATA_PATHS))

test-e2e-duckdb-cli:
	$(call run_e2e_duckdb,$@,$(E2E_DUCKDB_CLI_PATHS))

test-e2e-duckdb-virtual:
	$(call run_e2e_duckdb,$@,$(E2E_DUCKDB_VIRTUAL_PATHS))

test-e2e-duckdb-integrations:
	$(call run_e2e_duckdb,$@,$(E2E_DUCKDB_INTEGRATIONS_PATHS))

check-e2e-shards:
	bash scripts/check_e2e_shards.sh \
		--shard build-core $(E2E_DUCKDB_BUILD_CORE_PATHS) \
		--shard build-incremental $(E2E_DUCKDB_BUILD_INCREMENTAL_PATHS) \
		--shard build-virtual $(E2E_DUCKDB_BUILD_VIRTUAL_PATHS) \
		--shard cli-data $(E2E_DUCKDB_CLI_DATA_PATHS) \
		--shard cli $(E2E_DUCKDB_CLI_PATHS) \
		--shard virtual $(E2E_DUCKDB_VIRTUAL_PATHS) \
		--shard integrations $(E2E_DUCKDB_INTEGRATIONS_PATHS)


test-e2e-performance:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-e2e-performance-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests/e2e \
		-m "performance and not real_warehouse and not dbt" \
		-vv --log-cli-level=INFO --color=yes 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_E2E_PERFORMANCE_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


test-virtual:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-virtual-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 TESTCONTAINERS_RYUK_DISABLED=true SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest \
		$(VIRTUAL_TEST_ROOTS) \
		-k "$(VIRTUAL_TEST_KEYWORD)" \
		-m "not dbt and not performance" -vv --color=yes -n auto --dist loadfile 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_VIRTUAL_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


skills:
	uv run python -m scripts.generate_docs_skill
	uv run sqb skills --global --target opencode
	uv run fensu skills


DBT_EXECUTABLE ?= dbt
export DBT_EXECUTABLE

SQLBUILD_CONCURRENCY ?= 8

VIRTUAL_TEST_ROOTS ?= tests/e2e/src/sqlbuild/cli/commands/main tests/e2e/src/sqlbuild/integrations/dagster
VIRTUAL_TEST_KEYWORD ?= virtual or reconcile or diff or janitor or snapshot or dagster


test-dbt:
	@mkdir -p /tmp/opencode
	@log=/tmp/opencode/test-dbt-$$(date +%Y%m%d-%H%M%S).log; \
	echo "Logging to $$log (DBT_EXECUTABLE=$(DBT_EXECUTABLE))"; \
	uv run pytest tests/integration/src/sqlbuild/integrations/dbt tests/e2e/src/sqlbuild/cli/commands/main/dbt -m "dbt and not real_warehouse" -vv --color=yes -n auto --dist load 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "Full output saved to $$log"; \
	exit $$status


DBT_TEST_PATHS := tests/integration/src/sqlbuild/integrations/dbt tests/e2e/src/sqlbuild/cli/commands/main/dbt


test-dbt-real:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-dbt-real-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest $(DBT_TEST_PATHS) -m "dbt and real_warehouse" -vv --color=yes -n auto --dist load 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_DBT_REAL_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


test-dbt-real-snowflake:
	uv run pytest $(DBT_TEST_PATHS) -m "dbt and real_warehouse and snowflake" -vv -n auto --dist load


test-dbt-real-bigquery:
	uv run pytest $(DBT_TEST_PATHS) -m "dbt and real_warehouse and bigquery" -vv -n auto --dist load


test-dbt-real-databricks:
	uv run pytest $(DBT_TEST_PATHS) -m "dbt and real_warehouse and databricks" -vv -n auto --dist load


test-dbt-real-postgres:
	TESTCONTAINERS_RYUK_DISABLED=true uv run pytest $(DBT_TEST_PATHS) -m "dbt and real_warehouse and postgres" -vv -n auto --dist load


test-dbt-real-sqlserver:
	uv run pytest $(DBT_TEST_PATHS) -m "dbt and real_warehouse and sqlserver" -vv -n auto --dist load


test-dbt-real-motherduck:
	uv run pytest $(DBT_TEST_PATHS) -m "dbt and real_warehouse and motherduck" -vv -n auto --dist load


waffle-shop:
	cd tests/e2e/fixtures/waffle_shop && $${SHELL:-/bin/sh}


test-real:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-real-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests -m real_warehouse -vv --color=yes -n auto --dist load 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_REAL_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


test-real-all: test-real


test-real-snowflake:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-real-snowflake-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests -m "real_warehouse and snowflake" -vv --color=yes -n auto --dist load 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_REAL_SNOWFLAKE_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


test-real-bigquery:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-real-bigquery-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests -m "real_warehouse and bigquery" -vv --color=yes -n auto --dist load 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_REAL_BIGQUERY_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


test-real-databricks:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-real-databricks-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests -m "real_warehouse and databricks" -vv --color=yes -n auto --dist load 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_REAL_DATABRICKS_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


test-real-postgres:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-real-postgres-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 TESTCONTAINERS_RYUK_DISABLED=true SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests -m "real_warehouse and postgres" -vv --color=yes -n auto --dist load 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_REAL_POSTGRES_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


test-real-sqlserver:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-real-sqlserver-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests -m "real_warehouse and sqlserver" -vv --color=yes -n auto --dist load 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_REAL_SQLSERVER_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


test-real-motherduck:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-real-motherduck-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests -m "real_warehouse and motherduck" -vv --color=yes -n auto --dist load 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_REAL_MOTHERDUCK_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


test-e2e-real-snowflake:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-e2e-real-snowflake-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests/e2e -m "real_warehouse and snowflake" -vv --color=yes -n auto --dist load 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_E2E_REAL_SNOWFLAKE_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


test-e2e-real-bigquery:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-e2e-real-bigquery-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests/e2e -m "real_warehouse and bigquery" -vv --color=yes -n auto --dist load 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_E2E_REAL_BIGQUERY_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


test-e2e-real-databricks:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-e2e-real-databricks-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
	env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests/e2e -m "real_warehouse and databricks" -vv --color=yes -n auto --dist load 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_E2E_REAL_DATABRICKS_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


check-fensu:
	uv run fensu check


dupscore:
	uv run dupscore report


check:
	uv run ruff format .
	uv run ruff check --fix .
	uv run ty check src tests
	uv run pytest tests/unit/src/sqlbuild/adapter/contract/classes/strict_adapter/test_strict_adapter.py -q
	uv run fensu check


verify-pg:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/verify-pg-$$(date +%Y%m%d-%H%M%S).log"; \
	{ \
		status=0; \
		run_verify_step() { \
			label="$$1"; \
			shift; \
			echo; \
			echo "==> $$label"; \
			"$$@"; \
			rc=$$?; \
			if [ $$rc -ne 0 ]; then \
				echo "STEP_FAILED[$$rc]: $$label"; \
				if [ $$status -eq 0 ]; then status=$$rc; fi; \
			fi; \
		}; \
		run_verify_step "ruff format" uv run ruff format .; \
		run_verify_step "ruff check" uv run ruff check --fix .; \
		run_verify_step "type check" uv run ty check src tests; \
		run_verify_step "tests" env PYTHONUNBUFFERED=1 TESTCONTAINERS_RYUK_DISABLED=true SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests/unit tests/integration tests/e2e -m "((not real_warehouse and not dbt) or (dbt and not real_warehouse) or (real_warehouse and postgres)) and not performance" -vv --color=yes -n auto --dist loadfile; \
		run_verify_step "performance tests" env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests/e2e -m "performance and not real_warehouse and not dbt" -vv --color=yes; \
		run_verify_step "fensu" uv run fensu check; \
		exit $$status; \
	} 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "VERIFY_PG_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


coverage:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/coverage-$$(date +%Y%m%d-%H%M%S).log"; \
	PYTHONUNBUFFERED=1 uv run pytest tests -m "not real_warehouse and not dbt" -vv --color=yes \
		--cov=src/sqlbuild --cov-branch \
		--cov-report=term-missing --cov-report=html --cov-report=xml \
		2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "COVERAGE_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


verify:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/verify-$$(date +%Y%m%d-%H%M%S).log"; \
	{ \
		status=0; \
		run_verify_step() { \
			label="$$1"; \
			shift; \
			echo; \
			echo "==> $$label"; \
			"$$@"; \
			rc=$$?; \
			if [ $$rc -ne 0 ]; then \
				echo "STEP_FAILED[$$rc]: $$label"; \
				if [ $$status -eq 0 ]; then status=$$rc; fi; \
			fi; \
		}; \
		run_verify_step "ruff format" uv run ruff format .; \
		run_verify_step "ruff check" uv run ruff check --fix .; \
		run_verify_step "type check" uv run ty check src tests; \
		run_verify_step "tests" env PYTHONUNBUFFERED=1 TESTCONTAINERS_RYUK_DISABLED=true SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests/unit tests/integration tests/e2e -m "((not real_warehouse and not dbt) or (dbt and not real_warehouse)) and not performance" -vv --color=yes -n auto --dist loadfile; \
		run_verify_step "performance tests" env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests/e2e -m "performance and not real_warehouse and not dbt" -vv --color=yes; \
		run_verify_step "fensu" uv run fensu check; \
		exit $$status; \
	} 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "VERIFY_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


verify-quick:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/verify-quick-$$(date +%Y%m%d-%H%M%S).log"; \
	{ \
		status=0; \
		run_verify_step() { \
			label="$$1"; \
			shift; \
			echo; \
			echo "==> $$label"; \
			"$$@"; \
			rc=$$?; \
			if [ $$rc -ne 0 ]; then \
				echo "STEP_FAILED[$$rc]: $$label"; \
				if [ $$status -eq 0 ]; then status=$$rc; fi; \
			fi; \
		}; \
		run_verify_step "ruff format" uv run ruff format .; \
		run_verify_step "ruff check" uv run ruff check --fix .; \
		run_verify_step "type check" uv run ty check src tests; \
		run_verify_step "tests" env PYTHONUNBUFFERED=1 TESTCONTAINERS_RYUK_DISABLED=true SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests/unit tests/integration -m "((not real_warehouse and not dbt) or (dbt and not real_warehouse)) and not performance" -vv --color=yes -n auto --dist loadfile; \
		run_verify_step "fensu" uv run fensu check; \
		exit $$status; \
	} 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "VERIFY_QUICK_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
	exit $$status


check-ci: check-e2e-shards
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check src tests
	uv run pytest tests/unit/src/sqlbuild/adapter/contract/classes/strict_adapter/test_strict_adapter.py -q
	uv run fensu check


check-pr-metadata:
	@test -n "$(PR_TITLE)" || { echo "PR_TITLE is required" >&2; exit 2; }
	@test -n "$(PR_BODY_FILE)" || { echo "PR_BODY_FILE is required" >&2; exit 2; }
	uv run python -m scripts.validate_pr_metadata \
		--title "$(PR_TITLE)" \
		--body-file "$(PR_BODY_FILE)"


verify-ci:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check src tests
	uv run pytest tests/unit tests/integration -m "not real_warehouse and not dbt" -vv -n auto --dist loadfile
	uv run pytest tests/e2e -m "not real_warehouse and not dbt and not performance" -vv -n auto --dist loadfile
	uv run pytest tests/e2e -m "performance and not real_warehouse and not dbt" -vv
	uv run fensu check
