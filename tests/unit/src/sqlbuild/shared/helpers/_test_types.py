from dataclasses import dataclass


@dataclass(frozen=True)
class FormatCodedErrorTestCase:
    description: str
    code: str
    message: str
    help: str | None
    use_color: bool
    expected_rendered: str


@dataclass(frozen=True)
class CliStyleTestCase:
    description: str
    use_color: bool
    expected_title: str
    expected_section: str
    expected_label: str
    expected_value: str
    expected_status_ok: str
    expected_status_error: str
    expected_status_skip: str
    expected_dbt_section: str
    expected_dbt_object_name: str


@dataclass(frozen=True)
class CliDocumentTestCase:
    description: str
    use_color: bool
    expected_rendered: str
