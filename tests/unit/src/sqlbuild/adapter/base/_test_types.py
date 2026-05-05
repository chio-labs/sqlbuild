from dataclasses import dataclass


@dataclass(frozen=True)
class BaseAdapterPythonFunctionSupportTestCase:
    description: str
    expected_error_fragment: str
