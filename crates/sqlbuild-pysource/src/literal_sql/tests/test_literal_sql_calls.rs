use crate::literal_sql::main::literal_sql_calls::literal_sql_calls;
use crate::literal_sql::models::{FunctionSource, LiteralSql};
use crate::literal_sql::tests::test_types::LiteralSqlTestCase;

const PLACEHOLDER: &str = "__value_";

/// Expectations recorded from the CPython 3.12 `ast` implementation this replaces.
#[test]
fn given_function_source_when_reading_literal_sql_then_matches_cpython_walk() {
    let test_cases = [
        LiteralSqlTestCase {
            description: "positional and keyword SQL in walk order",
            source: "def task(ctx):\n    ctx.execute_sql(sql=\"delete from orders\")\n    if ready:\n        ctx.query(\"select * from customers\")\n    ctx.query(f\"select * from {table} where id = {key!r:>{width}}\")\n",
            expected_calls: &[
                ("execute_sql", "delete from orders", 11),
                ("query", "select * from __value_1 where id = __value_3", 14),
                ("query", "select * from customers", 13),
            ],
        },
        LiteralSqlTestCase {
            description: "a well-known context name wins over the first parameter",
            source: "def hook(self, context):\n    self.query(\"select 1\")\n    context.query(**{\"sql\": \"select 2\"})\n",
            expected_calls: &[("query", "select 2", 12)],
        },
        LiteralSqlTestCase {
            description: "implicit concatenation, debug text and bytes",
            source: "async def check(ctx, /):\n    ctx.query(\"select \" \"1\")\n    ctx.query(f\"{ value = }\" \"tail\")\n    ctx.query(b\"select 3\")\n    ctx.query(sql)\n",
            expected_calls: &[
                ("query", "select 1", 11),
                ("query", " value = __value_1tail", 12),
            ],
        },
        LiteralSqlTestCase {
            description: "nested calls come after their parents",
            source: "def task(ctx):\n    ctx.query(ctx.query(\"inner\"))\n    ctx.query(\"outer\")\n",
            expected_calls: &[("query", "outer", 12), ("query", "inner", 11)],
        },
        LiteralSqlTestCase {
            description: "a source that does not parse",
            source: "def task(ctx):\n    ctx.query(\"select 1\"\n",
            expected_calls: &[],
        },
        LiteralSqlTestCase {
            description: "a source that is not a function",
            source: "owner = lambda ctx: ctx.query(\"select 1\")\n",
            expected_calls: &[],
        },
        LiteralSqlTestCase {
            description: "a function without parameters",
            source: "def task():\n    ctx.query(\"select 1\")\n",
            expected_calls: &[],
        },
    ];
    for test_case in test_cases {
        let calls: Vec<LiteralSql> = literal_sql_calls(&FunctionSource {
            text: test_case.source,
            start_line: 10,
            placeholder: PLACEHOLDER,
            python_version: (3, 12),
        });
        let found: Vec<(&str, &str, usize)> = calls
            .iter()
            .map(|call| (call.method.as_str(), call.sql.as_str(), call.line))
            .collect();
        assert_eq!(found, test_case.expected_calls, "{}", test_case.description);
    }
}
