from dataclasses import dataclass


@dataclass(frozen=True)
class ModelTestFactsTestCase:
    description: str
    model_name: str
    other_model_name: str
    direct_test_name: str
    expected_matching_names: tuple[str, ...]
    expected_all_names: tuple[str, ...]
