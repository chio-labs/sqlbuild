"""Code-owned semantic remediation; no catch-all help for unrelated diagnostics."""

_TIMESTAMP: str = "TIMESTAMP"
_DATE: str = "DATE"
_BIGQUERY: str = "bigquery"
_SEMANTIC_HELP: dict[str, str] = {
    "B003": "qualify this column with the intended input alias",
    "B004": "give each referenced relation a visible alias in this scope",
    "B005": "match the relation alias list to its available output columns",
    "B101": "check the function spelling or declare the project function before using it",
    "B102": "pass the number of arguments required by this function's signature",
    "B210": "use an expression whose inferred type satisfies this SQL construct",
    "B211": "use a Boolean predicate in this condition",
    "B212": "use operands supported by this arithmetic operator, or convert them explicitly",
    "B213": "supply argument types supported by this function or conditional expression",
    "B214": "make the assigned expression compatible with the destination type",
    "B215": "align the corresponding types in each set-operation branch",
    "B216": "return the same number of columns on both sides of this operation",
    "B217": "compare compatible types using a correctly typed literal or explicit conversion",
    "B218": "choose a supported source-to-target cast for this dialect",
    "B219": "declare or cast this expression's unknown type so it can be checked",
    "B230": "add this expression to GROUP BY or use it inside an aggregate",
    "B231": "move this aggregate to SELECT or HAVING, or compute it in an input CTE",
    "B232": "use this window function with a valid OVER clause and window context",
    "B233": "use distinct names for relations or CTEs within this scope",
    "B234": "use a valid constant bound for LIMIT or OFFSET",
    "B300": "change the metadata column name to an existing output column",
    "B301": "align this declared metadata or audit value with the column or argument type",
    "B302": "align the SQL-test fixture or expected columns with the tested resource's output",
    "W210": "check comparison inputs for values that cannot be converted at runtime",
    "W211": "check arithmetic inputs before relying on implicit numeric conversion",
    "W212": "validate values before assigning them through an implicit conversion",
    "W213": "validate the cast input or declare the extension-defined target type",
    "W214": "validate values converted between these set-operation branches",
    "W215": "handle NULL explicitly when this predicate must return TRUE or FALSE",
    "W216": "validate function arguments before their implicit conversion",
    "W217": "convert aggregate inputs explicitly to the intended result type",
    "W218": "use a wider numeric type or bound the inputs to avoid overflow",
    "W219": "use a target type with enough length or precision to avoid truncation",
}


def semantic_help_catalogue() -> dict[str, str]:
    """Return the code-owned remediation catalogue."""
    return dict(_SEMANTIC_HELP)


def semantic_help(code: str) -> str | None:
    """Return help only for a code with its own remediation."""
    return _SEMANTIC_HELP.get(code)


def comparison_help(*, types: tuple[str, ...], dialect: str | None) -> str:
    """Offer a concrete literal for a proven temporal comparison mismatch."""
    if any(_TIMESTAMP in value for value in types):
        literal: str = "TIMESTAMP '2026-04-01'"
        if dialect == _BIGQUERY:
            literal = "TIMESTAMP '2026-04-01 00:00:00+00'"
        return f"compare with a timestamp, for example {literal}"
    if _DATE in types:
        return "compare with a date, for example DATE '2026-04-01'"
    return _SEMANTIC_HELP["B217"]
