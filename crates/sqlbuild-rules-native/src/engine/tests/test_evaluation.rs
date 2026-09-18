use serde_json::{Value, json};
use tempfile::TempDir;

use crate::engine::main::evaluate::evaluate_json;
use crate::engine::tests::helpers;
use crate::engine::tests::test_types;
use crate::rules::_helpers::evaluation::normalize_rules_sql;

#[test]
fn given_repeated_native_evaluation_when_faulting_then_returns_deterministic_complete_facts()
-> Result<(), String> {
    let test_cases = [test_types::NativeEvaluationTestCase {
        description: "repeated native evaluation preserves every fault fact",
        config: json!({
            "select": ["SQBRCONTRACT101"],
            "cache": {"enabled": false}
        }),
        expected_faults: json!([{
            "code": "SQBRCONTRACT101",
            "path": "models/mart/commerce__mart__orders.sql",
            "line": 1,
            "column": 1,
            "message": "models must declare an enforced output contract",
            "remediation": "Declare contract enforced and list the authoritative output columns in MODEL()."
        }]),
    }];

    for test_case in &test_cases {
        let project_dir = TempDir::new().map_err(|error| error.to_string())?;
        let request_json = helpers::request(&project_dir, &test_case.config);
        let first: Value = serde_json::from_str(&evaluate_json(&request_json)?)
            .map_err(|error| error.to_string())?;
        let second: Value = serde_json::from_str(&evaluate_json(&request_json)?)
            .map_err(|error| error.to_string())?;

        assert_eq!(
            first["faults"], second["faults"],
            "{}",
            test_case.description
        );
        assert_eq!(
            first["faults"], test_case.expected_faults,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_enforced_contract_when_column_type_is_missing_then_typed_contract_rule_faults()
-> Result<(), String> {
    let test_cases = [
        test_types::TypedContractColumnTestCase {
            description: "enforced contract has one untyped column",
            contract: "enforced",
            columns: json!([
                {"name": "order_id", "type": "INTEGER", "type_proven": true},
                {"name": "status", "type": "", "type_proven": false}
            ]),
            expected_fault_count: 1,
            expected_messages: &["contract column \"status\" has no declared type"],
        },
        test_types::TypedContractColumnTestCase {
            description: "enforced contract has only typed columns",
            contract: "enforced",
            columns: json!([
                {"name": "order_id", "type": "INTEGER", "type_proven": true}
            ]),
            expected_fault_count: 0,
            expected_messages: &[],
        },
        test_types::TypedContractColumnTestCase {
            description: "unenforced column metadata remains outside this rule",
            contract: "none",
            columns: json!([
                {"name": "status", "type": "", "type_proven": false}
            ]),
            expected_fault_count: 0,
            expected_messages: &[],
        },
    ];

    for test_case in test_cases {
        let project_dir = TempDir::new().map_err(|error| error.to_string())?;
        let mut request: Value = serde_json::from_str(&helpers::request(
            &project_dir,
            &json!({
                "select": ["SQBRCONTRACT106"],
                "cache": {"enabled": false}
            }),
        ))
        .map_err(|error| error.to_string())?;
        request["models"][0]["config"] = json!({"contract": test_case.contract});
        request["models"][0]["columns"] = test_case.columns;

        let result: Value = serde_json::from_str(&evaluate_json(&request.to_string())?)
            .map_err(|error| error.to_string())?;
        let faults = result["faults"]
            .as_array()
            .ok_or_else(|| "faults must be an array".to_string())?;
        let messages = faults
            .iter()
            .filter_map(|fault| fault["message"].as_str())
            .collect::<Vec<_>>();

        assert_eq!(
            faults.len(),
            test_case.expected_fault_count,
            "{}",
            test_case.description
        );
        assert_eq!(
            messages, test_case.expected_messages,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_scoped_suppression_when_evaluating_native_fault_then_returns_no_faults()
-> Result<(), String> {
    let test_cases = [test_types::NativeEvaluationTestCase {
        description: "native evaluation applies a matching scoped suppression",
        config: json!({
            "select": ["SQBRCONTRACT101"],
            "cache": {"enabled": false},
            "rule_ignores": [{
                "rules": ["SQBRCONTRACT"],
                "paths": ["models/mart/**"],
                "reason": "Tracked migration"
            }]
        }),
        expected_faults: json!([]),
    }];

    for test_case in &test_cases {
        let project_dir = TempDir::new().map_err(|error| error.to_string())?;
        let request_json = helpers::request(&project_dir, &test_case.config);
        let result: Value = serde_json::from_str(&evaluate_json(&request_json)?)
            .map_err(|error| error.to_string())?;

        assert_eq!(
            result["faults"], test_case.expected_faults,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_declaration_only_project_when_evaluating_project_rule_then_rule_still_runs()
-> Result<(), String> {
    let test_cases = [test_types::NativeEvaluationTestCase {
        description: "duplicate enum rule runs without a model anchor",
        config: json!({
            "select": ["SQBRDECLARATION201"],
            "cache": {"enabled": false}
        }),
        expected_faults: json!(["SQBRDECLARATION201"]),
    }];
    for test_case in test_cases {
        let project_dir = TempDir::new().map_err(|error| error.to_string())?;
        let mut request: Value =
            serde_json::from_str(&helpers::request(&project_dir, &test_case.config))
                .map_err(|error| error.to_string())?;
        request["models"] = json!([]);
        request["public_enums"] = json!([
            {
                "name": "order_status",
                "relative_path": "enums/orders/order_status.sql",
                "members": [{"name": "OPEN", "value": "open"}]
            },
            {
                "name": "support_status",
                "relative_path": "enums/support/support_status.sql",
                "members": [{"name": "OPEN", "value": "open"}]
            }
        ]);
        let result: Value = serde_json::from_str(&evaluate_json(&request.to_string())?)
            .map_err(|error| error.to_string())?;
        let actual_codes = Value::Array(
            result["faults"]
                .as_array()
                .into_iter()
                .flatten()
                .map(|fault| fault["code"].clone())
                .collect(),
        );
        assert_eq!(
            actual_codes, test_case.expected_faults,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_scoped_and_global_declarations_when_evaluating_domain_rule_then_only_global_is_checked()
-> Result<(), String> {
    let test_cases = [
        test_types::DeclarationScopeTestCase {
            description: "local test declaration is outside global domain policy",
            scope: "local",
            path: "tests/unit/orders/_sqlbuild/enums/status.sql",
            expected_fault_count: 0,
        },
        test_types::DeclarationScopeTestCase {
            description: "global declaration without domain remains in policy",
            scope: "global",
            path: "enums/status.sql",
            expected_fault_count: 1,
        },
    ];
    for test_case in test_cases {
        let project_dir = TempDir::new().map_err(|error| error.to_string())?;
        let config = json!({
            "select": ["SQBRDECLARATION301"],
            "domains": ["orders"],
            "cache": {"enabled": false}
        });
        let mut request: Value = serde_json::from_str(&helpers::request(&project_dir, &config))
            .map_err(|error| error.to_string())?;
        request["models"] = json!([]);
        request["scope_index"] = helpers::scope_index();
        request["scope_index"]["declarations"][0]["scope"] = json!(test_case.scope);
        request["scope_index"]["declarations"][0]["path"] = json!(test_case.path);
        let result: Value = serde_json::from_str(&evaluate_json(&request.to_string())?)
            .map_err(|error| error.to_string())?;
        assert_eq!(
            result["faults"].as_array().map_or(0, Vec::len),
            test_case.expected_fault_count,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_snowflake_expression_when_evaluating_rules_then_uses_project_dialect() -> Result<(), String>
{
    let project_dir = TempDir::new().map_err(|error| error.to_string())?;
    let test_cases = [test_types::DialectEvaluationTestCase {
        description: "Snowflake compiler expressions use the resolved project dialect",
        dialect: "snowflake",
        query_sql: concat!(
            "SELECT * EXCLUDE (ignored), ",
            "TRANSFORM(values, leg INT -> leg + 1) AS adjusted, ",
            "payload:product_id::STRING AS product_id, ",
            "CAST(amounts AS ARRAY(NUMBER(38, 10))) AS amounts, ",
            "OBJECT_CONSTRUCT_KEEP_NULL('group_id', group_id) AS details, ",
            "FROM __table_fn(\"inventory_items\")(42)"
        ),
        expected_code: "SQBRCONTRACT101",
    }];

    for test_case in test_cases {
        let config = json!({"select": ["SQBRCONTRACT101"], "cache": {"enabled": false}});
        let mut request: Value = serde_json::from_str(&helpers::request(&project_dir, &config))
            .map_err(|error| error.to_string())?;
        request["dialect"] = json!(test_case.dialect);
        request["models"][0]["query_sql"] = json!(test_case.query_sql);
        let result: Value = serde_json::from_str(&evaluate_json(&request.to_string())?)
            .map_err(|error| error.to_string())?;
        assert_eq!(
            result["faults"][0]["code"], test_case.expected_code,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_enforced_contract_outputs_when_evaluating_explicit_type_rule_then_returns_expected_faults()
-> Result<(), String> {
    let test_cases = [
        test_types::ExplicitOutputTypeTestCase {
            description: "proven direct passthrough in final CTE",
            query_sql: "WITH final AS (SELECT order_id FROM orders) SELECT order_id FROM final",
            columns: json!([{"name": "order_id", "type": "INTEGER", "type_proven": true}]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "calculated output without outer cast",
            query_sql: "WITH final AS (SELECT amount + 1 AS total FROM orders) SELECT total FROM final",
            columns: json!([{"name": "total", "type": "INTEGER", "type_proven": true}]),
            contract: "enforced",
            expected_fault_count: 1,
            expected_message_fragment: "calculated without an outer explicit cast",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "proven outer cast",
            query_sql: "WITH final AS (SELECT CAST(amount + 1 AS INTEGER) AS total FROM orders) SELECT total FROM final",
            columns: json!([{"name": "total", "type": "INTEGER", "type_proven": true}]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "exact outer cast establishes type when inference remains unproven",
            query_sql: "SELECT CAST(amount AS INTEGER) AS total FROM orders",
            columns: json!([{"name": "total", "type": "INTEGER", "type_proven": false}]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "outer cast targets a different declared type",
            query_sql: "SELECT CAST(amount AS BIGINT) AS total FROM orders",
            columns: json!([{"name": "total", "type": "INTEGER", "type_proven": true}]),
            contract: "enforced",
            expected_fault_count: 1,
            expected_message_fragment: "outer cast that does not target",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "unproven direct passthrough",
            query_sql: "SELECT order_id FROM orders",
            columns: json!([{"name": "order_id", "type": "INTEGER", "type_proven": false}]),
            contract: "enforced",
            expected_fault_count: 1,
            expected_message_fragment: "passthrough whose type is not proven",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "contract declarations map by output name rather than declaration order",
            query_sql: "SELECT 'ready' AS label, CAST(1 AS INTEGER) AS order_id",
            columns: json!([
                {"name": "order_id", "type": "INTEGER", "type_proven": true},
                {"name": "label", "type": "", "type_proven": false}
            ]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "wildcard output boundary",
            query_sql: "SELECT * FROM orders",
            columns: json!([{"name": "order_id", "type": "INTEGER", "type_proven": true}]),
            contract: "enforced",
            expected_fault_count: 1,
            expected_message_fragment: "wildcard output",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "proven dependency import wildcard",
            query_sql: "WITH final AS (SELECT * FROM __ref(\"orders\")) SELECT order_id FROM final",
            columns: json!([{"name": "order_id", "type": "INTEGER", "type_proven": true}]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "unproven dependency import wildcard",
            query_sql: "WITH final AS (SELECT * FROM __ref(\"orders\")) SELECT order_id FROM final",
            columns: json!([{"name": "order_id", "type": "INTEGER", "type_proven": false}]),
            contract: "enforced",
            expected_fault_count: 1,
            expected_message_fragment: "wildcard output",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "positional set branches require casts",
            query_sql: "SELECT order_id FROM current_orders UNION ALL SELECT order_id FROM archived_orders",
            columns: json!([{"name": "order_id", "type": "INTEGER", "type_proven": true}]),
            contract: "enforced",
            expected_fault_count: 2,
            expected_message_fragment: "set-operation branch that must cast",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "positional set branches with proven casts",
            query_sql: "SELECT CAST(order_id AS INTEGER) AS order_id FROM current_orders UNION ALL SELECT CAST(order_id AS INTEGER) AS order_id FROM archived_orders",
            columns: json!([{"name": "order_id", "type": "INTEGER", "type_proven": true}]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "exact set branch casts establish types when inference remains unproven",
            query_sql: "SELECT CAST(order_id AS INTEGER) AS order_id FROM current_orders UNION ALL SELECT CAST(order_id AS INTEGER) AS order_id FROM archived_orders",
            columns: json!([{"name": "order_id", "type": "INTEGER", "type_proven": false}]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "by-name set branches map reordered outputs",
            query_sql: "SELECT CAST(order_id AS INTEGER) AS order_id, CAST(amount AS DECIMAL(18, 2)) AS amount FROM current_orders UNION ALL BY NAME SELECT CAST(amount AS DECIMAL(18, 2)) AS amount, CAST(order_id AS INTEGER) AS order_id FROM archived_orders",
            columns: json!([
                {"name": "order_id", "type": "INTEGER", "type_proven": true},
                {"name": "amount", "type": "DECIMAL(18, 2)", "type_proven": true}
            ]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "cast inside conditional is not outer cast",
            query_sql: "SELECT CASE WHEN active THEN CAST(amount AS INTEGER) ELSE 0 END AS total FROM orders",
            columns: json!([{"name": "total", "type": "INTEGER", "type_proven": true}]),
            contract: "enforced",
            expected_fault_count: 1,
            expected_message_fragment: "calculated without an outer explicit cast",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "contract-none model is outside rule scope",
            query_sql: "SELECT amount + 1 AS total FROM orders",
            columns: json!([{"name": "total", "type": "INTEGER", "type_proven": true}]),
            contract: "none",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "renamed and reordered terminal columns map to the final CTE",
            query_sql: "WITH final AS (SELECT CAST(amount AS DECIMAL(18, 2)) AS amount, CAST(order_id AS INTEGER) AS order_id FROM orders) SELECT order_id AS id, amount AS total FROM final",
            columns: json!([
                {"name": "id", "type": "INTEGER", "type_proven": true},
                {"name": "total", "type": "DECIMAL(18, 2)", "type_proven": true}
            ]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "final CTE maps contract declarations by terminal output name",
            query_sql: "WITH final AS (SELECT 'ready' AS label, CAST(1 AS INTEGER) AS order_id) SELECT label, order_id FROM final",
            columns: json!([
                {"name": "order_id", "type": "INTEGER", "type_proven": true},
                {"name": "label", "type": "", "type_proven": false}
            ]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "wildcard terminal maps contract declarations to final CTE output order",
            query_sql: "WITH final AS (SELECT 'ready' AS label, CAST(1 AS INTEGER) AS order_id) SELECT * FROM final",
            columns: json!([
                {"name": "order_id", "type": "INTEGER", "type_proven": true},
                {"name": "label", "type": "", "type_proven": false}
            ]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "wildcard terminal maps explicit final CTE column aliases by name",
            query_sql: "WITH final(order_id, amount) AS (SELECT CAST(raw_id AS INTEGER) AS raw_id, CAST(raw_amount AS DECIMAL(18, 2)) AS raw_amount FROM orders) SELECT * FROM final",
            columns: json!([
                {"name": "amount", "type": "DECIMAL(18, 2)", "type_proven": true},
                {"name": "order_id", "type": "INTEGER", "type_proven": true}
            ]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "renamed and reordered terminal columns map through positional set branches",
            query_sql: "WITH final AS (SELECT CAST(amount AS DECIMAL(18, 2)) AS amount, CAST(order_id AS INTEGER) AS order_id FROM current_orders UNION ALL SELECT CAST(amount AS DECIMAL(18, 2)) AS amount, CAST(order_id AS INTEGER) AS order_id FROM archived_orders) SELECT order_id AS id, amount AS total FROM final",
            columns: json!([
                {"name": "id", "type": "INTEGER", "type_proven": true},
                {"name": "total", "type": "DECIMAL(18, 2)", "type_proven": true}
            ]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "terminal subset ignores extra final CTE outputs",
            query_sql: "WITH final AS (SELECT CAST(order_id AS INTEGER) AS order_id, ignored_count + 1, ignored_label, CAST(amount AS DECIMAL(18, 2)) AS amount FROM orders) SELECT order_id AS id, amount AS total FROM final",
            columns: json!([
                {"name": "id", "type": "INTEGER", "type_proven": true},
                {"name": "total", "type": "DECIMAL(18, 2)", "type_proven": true}
            ]),
            contract: "enforced",
            expected_fault_count: 0,
            expected_message_fragment: "",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "terminal subset reports the selected calculated final CTE output",
            query_sql: "WITH final AS (SELECT CAST(order_id AS INTEGER) AS order_id, ignored_count, ignored_label, amount + 1 AS amount FROM orders) SELECT order_id AS id, amount AS total FROM final",
            columns: json!([
                {"name": "id", "type": "INTEGER", "type_proven": true},
                {"name": "total", "type": "DECIMAL(18, 2)", "type_proven": true}
            ]),
            contract: "enforced",
            expected_fault_count: 1,
            expected_message_fragment: "output \"amount\" is calculated without an outer explicit cast",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "terminal subset maps outputs introduced by right by-name branch",
            query_sql: "WITH final AS (SELECT CAST(1 AS INTEGER) AS ignored UNION ALL BY NAME SELECT 2 + 1 AS amount) SELECT amount AS total FROM final",
            columns: json!([
                {"name": "total", "type": "INTEGER", "type_proven": true}
            ]),
            contract: "enforced",
            expected_fault_count: 1,
            expected_message_fragment: "output \"amount\" is calculated without an outer explicit cast",
        },
        test_types::ExplicitOutputTypeTestCase {
            description: "terminal subset maps explicit final CTE column aliases",
            query_sql: "WITH final(order_id, ignored) AS (SELECT 1 + 1 AS raw_id, 3 AS extra) SELECT order_id AS id FROM final",
            columns: json!([
                {"name": "id", "type": "INTEGER", "type_proven": true}
            ]),
            contract: "enforced",
            expected_fault_count: 1,
            expected_message_fragment: "output \"raw_id\" is calculated without an outer explicit cast",
        },
    ];
    for test_case in test_cases {
        let project_dir = TempDir::new().map_err(|error| error.to_string())?;
        let config = json!({"select": ["SQBRCONTRACT105"], "cache": {"enabled": false}});
        let mut request: Value = serde_json::from_str(&helpers::request(&project_dir, &config))
            .map_err(|error| error.to_string())?;
        request["models"][0]["query_sql"] = json!(test_case.query_sql);
        request["models"][0]["authored_sql"] = json!(test_case.query_sql);
        request["models"][0]["config"] = json!({"contract": test_case.contract});
        request["models"][0]["columns"] = test_case.columns;

        let result: Value = serde_json::from_str(&evaluate_json(&request.to_string())?)
            .map_err(|error| error.to_string())?;
        let faults = result["faults"]
            .as_array()
            .ok_or("faults must be an array")?;
        assert_eq!(
            faults.len(),
            test_case.expected_fault_count,
            "{}",
            test_case.description
        );
        assert!(
            faults.iter().all(|fault| fault["message"]
                .as_str()
                .is_some_and(|message| message.contains(test_case.expected_message_fragment))),
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_snowflake_parser_extensions_when_normalizing_then_preserves_source_positions() {
    let test_cases = [test_types::NormalizationTestCase {
        description: "normalization changes syntax only outside strings and comments",
        dialect: "snowflake",
        sql: concat!(
            "SELECT * EXCLUDE (\n  ignored,\n  obsolete\n), ",
            "TRANSFORM(values, leg INT -> leg + 1),\n",
            "'__table_fn(\"quoted\")(7)', /* leg INT -> unchanged */ payload:key::STRING,\n",
            "CAST(amounts AS ARRAY(\n  NUMBER(38, 10)\n)) AS amounts\n",
            "FROM __table_fn(\"orders)archive\")(42)"
        ),
        expected_typed_lambda: "leg     -> leg + 1",
        expected_quoted_call: "'__table_fn(\"quoted\")(7)'",
        expected_comment: "/* leg INT -> unchanged */",
        expected_table_function: "__table_fn(\"orders)archive\", 42)",
        expected_other_dialect_lambda: "leg INT -> leg + 1",
    }];

    for test_case in test_cases {
        let normalized = normalize_rules_sql(test_case.dialect, test_case.sql);
        assert_eq!(
            normalized.len(),
            test_case.sql.len(),
            "{}",
            test_case.description
        );
        assert_eq!(
            normalized.lines().count(),
            test_case.sql.lines().count(),
            "{}",
            test_case.description
        );
        assert!(
            normalized.contains(test_case.expected_typed_lambda),
            "{}",
            test_case.description
        );
        assert!(
            normalized.contains(test_case.expected_quoted_call),
            "{}",
            test_case.description
        );
        assert!(
            normalized.contains(test_case.expected_comment),
            "{}",
            test_case.description
        );
        assert!(
            normalized.contains(test_case.expected_table_function),
            "{}",
            test_case.description
        );
        let other = normalize_rules_sql("duckdb", test_case.sql);
        assert!(
            other.contains(test_case.expected_other_dialect_lambda),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_deep_valid_expression_when_evaluating_rules_then_parser_budget_is_sufficient()
-> Result<(), String> {
    let project_dir = TempDir::new().map_err(|error| error.to_string())?;
    let test_cases = [test_types::DeepExpressionTestCase {
        description: "deep valid expression remains within the parser budget",
        depth: 55,
        expected_code: "SQBRCONTRACT101",
    }];

    for test_case in test_cases {
        let config = json!({"select": ["SQBRCONTRACT101"], "cache": {"enabled": false}});
        let mut request: Value = serde_json::from_str(&helpers::request(&project_dir, &config))
            .map_err(|error| error.to_string())?;
        let expression = format!(
            "{}1{}",
            "COALESCE(".repeat(test_case.depth),
            ", 0)".repeat(test_case.depth)
        );
        request["models"][0]["query_sql"] = json!(format!("SELECT {expression} AS value"));
        let result: Value = serde_json::from_str(&evaluate_json(&request.to_string())?)
            .map_err(|error| error.to_string())?;
        assert_eq!(
            result["faults"][0]["code"], test_case.expected_code,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_path_threshold_overrides_when_evaluating_then_matches_in_authored_order()
-> Result<(), String> {
    let project_dir = TempDir::new().map_err(|error| error.to_string())?;
    let test_cases = [
        test_types::ThresholdEvaluationTestCase {
            description: "matching override raises both minima",
            config: json!({
                "select": ["SQBRTEST201", "SQBRTEST202"],
                "thresholds": {"min_audits_per_model": 1, "min_tests_per_model": 1},
                "threshold_overrides": [{
                    "paths": ["models/mart/**"],
                    "thresholds": {"min_audits_per_model": 2, "min_tests_per_model": 2},
                    "reason": "marts require stronger evidence"
                }],
                "cache": {"enabled": false}
            }),
            query_sql: "SELECT id + 1 AS id FROM orders",
            references: json!([]),
            expected_codes: &["SQBRTEST201", "SQBRTEST202"],
        },
        test_types::ThresholdEvaluationTestCase {
            description: "near miss keeps global minima",
            config: json!({
                "select": ["SQBRTEST201", "SQBRTEST202"],
                "thresholds": {"min_audits_per_model": 1, "min_tests_per_model": 1},
                "threshold_overrides": [{
                    "paths": ["models/staging/**"],
                    "thresholds": {"min_audits_per_model": 2, "min_tests_per_model": 2},
                    "reason": "staging requires stronger evidence"
                }],
                "cache": {"enabled": false}
            }),
            query_sql: "SELECT id + 1 AS id FROM orders",
            references: json!([]),
            expected_codes: &[],
        },
        test_types::ThresholdEvaluationTestCase {
            description: "last matching override wins",
            config: json!({
                "select": ["SQBRTEST201", "SQBRTEST202"],
                "thresholds": {"min_audits_per_model": 1, "min_tests_per_model": 1},
                "threshold_overrides": [
                    {
                        "paths": ["models/**"],
                        "thresholds": {"min_audits_per_model": 2, "min_tests_per_model": 2},
                        "reason": "all models require stronger evidence"
                    },
                    {
                        "paths": ["models/mart/**"],
                        "thresholds": {"min_audits_per_model": 1, "min_tests_per_model": 1},
                        "reason": "mart migration temporarily uses global minima"
                    }
                ],
                "cache": {"enabled": false}
            }),
            query_sql: "SELECT id + 1 AS id FROM orders",
            references: json!([]),
            expected_codes: &[],
        },
        test_types::ThresholdEvaluationTestCase {
            description: "audit and test overrides resolve independently",
            config: json!({
                "select": ["SQBRTEST201", "SQBRTEST202"],
                "thresholds": {"min_audits_per_model": 1, "min_tests_per_model": 1},
                "threshold_overrides": [{
                    "paths": ["models/mart/**"],
                    "thresholds": {"min_audits_per_model": 2},
                    "reason": "marts require an additional audit"
                }],
                "cache": {"enabled": false}
            }),
            query_sql: "SELECT id + 1 AS id FROM orders",
            references: json!([]),
            expected_codes: &["SQBRTEST201"],
        },
        test_types::ThresholdEvaluationTestCase {
            description: "matching override preserves passthrough exemption",
            config: json!({
                "select": ["SQBRTEST201", "SQBRTEST202"],
                "threshold_overrides": [{
                    "paths": ["models/mart/**"],
                    "thresholds": {"min_audits_per_model": 10, "min_tests_per_model": 10},
                    "reason": "marts require strong evidence"
                }],
                "cache": {"enabled": false}
            }),
            query_sql: "WITH upstream AS (SELECT * FROM __ref(\"commerce__stg__orders\")) SELECT id FROM upstream",
            references: json!([{"ref_kind": "ref", "ref_name": "commerce__stg__orders"}]),
            expected_codes: &[],
        },
    ];

    for test_case in &test_cases {
        let request_json = helpers::threshold_request(
            &project_dir,
            &test_case.config,
            test_case.query_sql,
            &test_case.references,
        );
        let result: Value = serde_json::from_str(&evaluate_json(&request_json)?)
            .map_err(|error| error.to_string())?;
        let codes: Vec<&str> = result["faults"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|fault| fault["code"].as_str())
            .collect();
        assert_eq!(codes, test_case.expected_codes, "{}", test_case.description);
    }
    Ok(())
}

#[test]
fn given_threshold_override_change_when_evaluating_then_ruleset_fingerprint_changes()
-> Result<(), String> {
    let project_dir = TempDir::new().map_err(|error| error.to_string())?;
    let test_cases = [test_types::ThresholdFingerprintTestCase {
        description: "path threshold changes the ruleset fingerprint",
        base_config: json!({
            "select": ["SQBRTEST202"],
            "cache": {"enabled": false}
        }),
        overridden_config: json!({
            "select": ["SQBRTEST202"],
            "threshold_overrides": [{
                "paths": ["models/mart/**"],
                "thresholds": {"min_tests_per_model": 2},
                "reason": "marts require two focused tests"
            }],
            "cache": {"enabled": false}
        }),
        expected_different: true,
    }];

    for test_case in &test_cases {
        let references = json!([]);
        let base_request = helpers::threshold_request(
            &project_dir,
            &test_case.base_config,
            "SELECT id + 1 AS id FROM orders",
            &references,
        );
        let overridden_request = helpers::threshold_request(
            &project_dir,
            &test_case.overridden_config,
            "SELECT id + 1 AS id FROM orders",
            &references,
        );
        let base_result: Value = serde_json::from_str(&evaluate_json(&base_request)?)
            .map_err(|error| error.to_string())?;
        let overridden_result: Value = serde_json::from_str(&evaluate_json(&overridden_request)?)
            .map_err(|error| error.to_string())?;
        let different =
            base_result["ruleset_fingerprint"] != overridden_result["ruleset_fingerprint"];

        assert_eq!(
            different, test_case.expected_different,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
