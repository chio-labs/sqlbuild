"""Cost observability defaults."""

from decimal import Decimal

from sqlbuild.cost.classes.cost_telemetry_health import CostTelemetryHealth

DEFAULT_USD_PER_CREDIT: Decimal = Decimal("3.00")
DEFAULT_RATE_SOURCE: str = "default"
SQLBUILD_QUERY_TAG_APP: str = "sqlbuild"
LEDGER_PERSISTENCE_FAILURE_LIMITATION_PREFIX: str = "Statement-ledger persistence failed ("
COST_TELEMETRY_HEALTH: CostTelemetryHealth = CostTelemetryHealth()
