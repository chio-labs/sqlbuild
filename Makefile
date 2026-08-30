SHELL := /bin/bash

.PHONY: verify verify-quick verify-pg coverage cli-preview rust-check

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


test-e2e-duckdb:
	@mkdir -p /tmp/opencode
	@log="/tmp/opencode/test-e2e-duckdb-$$(date +%Y%m%d-%H%M%S).log"; \
	echo "Logging to $$log"; \
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
		run_step "duckdb e2e" env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests/e2e -m "not real_warehouse and not dbt and not performance" -vv --color=yes -n auto --dist loadfile; \
		run_step "duckdb performance" env PYTHONUNBUFFERED=1 SQLBUILD_CONCURRENCY=$(SQLBUILD_CONCURRENCY) uv run pytest tests/e2e -m "performance and not real_warehouse and not dbt" -vv --log-cli-level=INFO --color=yes; \
		exit $$status; \
	} 2>&1 | tee "$$log"; \
	status=$${PIPESTATUS[0]}; \
	echo "TEST_E2E_DUCKDB_EXIT=$$status (log: $$log)" | tee -a "$$log"; \
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


check-ci:
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
