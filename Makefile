format:
	uv run ruff format .


lint:
	uv run ruff check --fix .


type:
	uv run ty check src tests


test:
	uv run pytest tests/unit tests/integration -m "not real_warehouse" -vv


test-all:
	uv run pytest tests -m "not real_warehouse" -vv


test-real:
	uv run pytest tests -m real_warehouse -vv


test-snowflake:
	uv run pytest tests -m snowflake -vv


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
	uv run pytest tests -m "not real_warehouse" -vv
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
	uv run pytest tests -m "not real_warehouse" -vv
	uv run check-test-conventions tests
	uv run check-structure-conventions src/sqlbuild scripts
	uv run check-type-annotation-conventions src tests
