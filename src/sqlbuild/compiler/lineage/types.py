"""Column lineage domain types."""

from __future__ import annotations

from enum import StrEnum


class ColumnTransformKind(StrEnum):
    """High-level transform classification for one output column."""

    DIRECT = "direct"
    CAST = "cast"
    EXPRESSION = "expression"
    AGGREGATION = "aggregation"
    STAR = "star"
    CONSTANT = "constant"
    UNKNOWN = "unknown"


class InferredNullability(StrEnum):
    """Conservative nullability state inferred for an output column."""

    NON_NULL = "non_null"
    NULLABLE = "nullable"
    UNKNOWN = "unknown"


class ColumnLineageConfidence(StrEnum):
    """Coarse confidence that a lineage edge is fully understood."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ColumnLineageMode(StrEnum):
    """Column lineage analyzer mode."""

    RICH = "rich"
    FAST = "fast"


class PolyglotAnalysisDialect(StrEnum):
    """Dialect names accepted by Polyglot analyze_query."""

    GENERIC = "generic"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    BIGQUERY = "bigquery"
    SNOWFLAKE = "snowflake"
    DUCKDB = "duckdb"
    SQLITE = "sqlite"
    HIVE = "hive"
    SPARK = "spark"
    TRINO = "trino"
    PRESTO = "presto"
    REDSHIFT = "redshift"
    TSQL = "tsql"
    ORACLE = "oracle"
    CLICKHOUSE = "clickhouse"
    DATABRICKS = "databricks"
    ATHENA = "athena"
    TERADATA = "teradata"
    DORIS = "doris"
    STARROCKS = "starrocks"
    MATERIALIZE = "materialize"
    RISINGWAVE = "risingwave"
    SINGLESTORE = "singlestore"
    COCKROACHDB = "cockroachdb"
    TIDB = "tidb"
    DRUID = "druid"
    SOLR = "solr"
    TABLEAU = "tableau"
    DUNE = "dune"
    FABRIC = "fabric"
    DRILL = "drill"
    DREMIO = "dremio"
    EXASOL = "exasol"
    DATAFUSION = "datafusion"
