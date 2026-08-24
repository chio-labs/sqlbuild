"""Cost observability defaults."""

from decimal import Decimal

from sqlbuild.cost.classes.cost_telemetry_health import CostTelemetryHealth

DEFAULT_USD_PER_CREDIT: Decimal = Decimal("3.00")
DEFAULT_RATE_SOURCE: str = "default"
STANDARD_WAREHOUSE_TYPE: str = "STANDARD"
RUNNING_EXECUTION_STATUS: str = "RUNNING"
SQLBUILD_QUERY_TAG_APP: str = "sqlbuild"
USD_PER_CREDIT_CONFIG_KEY: str = "usd_per_credit"
LATEST_COST_RUN_SELECTOR: str = "latest"
RUNNING_BUILD_STATUS: str = "running"
NO_WAREHOUSE_COMPUTE_REASON: str = "no_warehouse_compute"
MISSING_WAREHOUSE_METADATA_REASON: str = "missing_warehouse_metadata"
INCOMPLETE_HISTORY_REASON: str = "incomplete_history"
OUTSIDE_RUN_WINDOW_REASON: str = "outside_run_window"
COST_TELEMETRY_HEALTH: CostTelemetryHealth = CostTelemetryHealth()
