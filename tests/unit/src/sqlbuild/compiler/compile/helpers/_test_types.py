from dataclasses import dataclass


@dataclass(frozen=True)
class ExpandSqlMacrosTestCase:
    description: str
    macro_file_contents: str
    sql: str
    expected_sql: str


@dataclass(frozen=True)
class ExpandSqlMacrosErrorTestCase:
    description: str
    macro_file_contents: str
    sql: str
    expected_error_fragment: str
