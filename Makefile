format:
	uv run ruff format .


lint:
	uv run ruff check --fix .


type:
	uv run ty check src tests


test:
	uv run pytest tests/unit tests/integration -m "not real_warehouse and not dbt" -vv


test-all:
	uv run pytest tests -m "not real_warehouse and not dbt" -vv


test-dbt:
	uv run pytest tests/integration/src/sqlbuild/integrations/dbt tests/e2e/src/sqlbuild/cli/commands/main/dbt -m "dbt and not real_warehouse" -vv


waffle-shop:
	cd tests/e2e/fixtures/waffle_shop && $${SHELL:-/bin/sh}


test-real:
	uv run pytest tests -m real_warehouse -vv


test-real-all: test-real


test-real-snowflake:
	uv run pytest tests -m "real_warehouse and snowflake" -vv


test-real-bigquery:
	uv run pytest tests -m "real_warehouse and bigquery" -vv


test-real-databricks:
	uv run pytest tests -m "real_warehouse and databricks" -vv


test-real-postgres:
	TESTCONTAINERS_RYUK_DISABLED=true uv run pytest tests -m "real_warehouse and postgres" -vv


test-real-motherduck:
	uv run pytest tests -m "real_warehouse and motherduck" -vv


test-e2e-real-snowflake:
	uv run pytest tests/e2e -m "real_warehouse and snowflake" -vv


test-e2e-real-bigquery:
	uv run pytest tests/e2e -m "real_warehouse and bigquery" -vv


test-e2e-real-databricks:
	uv run pytest tests/e2e -m "real_warehouse and databricks" -vv


check-test-conventions:
	uv run check-test-conventions tests


check-structure-conventions:
	uv run check-structure-conventions src/sqlbuild scripts


check-type-annotation-conventions:
	uv run check-type-annotation-conventions src tests


check:
	uv run ruff format .
	uv run ruff check --fix .
	uv run ty check src tests
	uv run check-test-conventions tests
	uv run check-structure-conventions src/sqlbuild scripts
	uv run check-type-annotation-conventions src tests


verify:
	uv run ruff format .
	uv run ruff check --fix .
	uv run ty check src tests
	uv run pytest tests -m "not real_warehouse and not dbt" -vv
	uv run check-test-conventions tests
	uv run check-structure-conventions src/sqlbuild scripts
	uv run check-type-annotation-conventions src tests


check-ci:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check src tests
	uv run check-test-conventions tests
	uv run check-structure-conventions src/sqlbuild scripts
	uv run check-type-annotation-conventions src tests


verify-ci:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check src tests
	uv run pytest tests -m "not real_warehouse and not dbt" -vv
	uv run check-test-conventions tests
	uv run check-structure-conventions src/sqlbuild scripts
	uv run check-type-annotation-conventions src tests
