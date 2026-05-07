def expected_or_actual[T](expected: T | None, actual: T) -> T:
    if expected is None:
        return actual
    return expected
