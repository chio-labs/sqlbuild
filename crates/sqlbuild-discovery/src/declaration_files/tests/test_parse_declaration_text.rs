use crate::declaration_files::models::CollectionKind;
use crate::declaration_files::tests::helpers::{nesting_failure_debug, parsed_debug};
use crate::declaration_files::tests::test_types::{
    DeclarationTextTestCase, DeepDeclarationTestCase,
};

#[test]
fn given_declaration_files_when_parsing_then_values_and_failures_match_python() {
    let test_cases = [
        DeclarationTextTestCase {
            description: "shorthand and explicit enums",
            kind: CollectionKind::Enums,
            contents: "ENUM (name status, members [PLACED, SHIPPED]);\n\u{a0}ENUM(name rank, members (LOW 1, HIGH -2)) ;",
            expected_fragments: &[
                "Parsed(Enum(",
                "name: \"status\", members: [(\"PLACED\", String(\"PLACED\")), (\"SHIPPED\", String(\"SHIPPED\"))], scalar_type: \"VARCHAR\"",
                "(\"HIGH\", BareWord(\"-2\"))], scalar_type: \"INTEGER\"",
            ],
        },
        DeclarationTextTestCase {
            description: "lowercase enum members",
            kind: CollectionKind::Enums,
            contents: "ENUM (name status, members [placed]);",
            expected_fragments: &[
                "Failed(",
                "Declaration",
                "/project/declarations/orders.sql enum 'status' member identifiers must be uppercase: 'placed'",
            ],
        },
        DeclarationTextTestCase {
            description: "mixed enum member types",
            kind: CollectionKind::Enums,
            contents: "ENUM (name status, members (A 'x', B 1));",
            expected_fragments: &[
                "/project/declarations/orders.sql enum 'status' members must use one consistent scalar type",
            ],
        },
        DeclarationTextTestCase {
            description: "a float member value",
            kind: CollectionKind::Enums,
            contents: "ENUM (name status, members (A 1.5));",
            expected_fragments: &[
                "/project/declarations/orders.sql enum 'status' member 'A' value must be a string or integer",
            ],
        },
        DeclarationTextTestCase {
            description: "a bare number in non-ASCII digits is rejected with help",
            kind: CollectionKind::Enums,
            contents: "ENUM (name status, members (A \u{661}));",
            expected_fragments: &[
                "/project/declarations/orders.sql has the bare number '\u{661}', written with non-ASCII digits",
                "Quote it to keep it as text",
            ],
        },
        DeclarationTextTestCase {
            description: "a constant bare number in non-ASCII digits is rejected, nested too",
            kind: CollectionKind::Constants,
            contents: "CONSTANT (name limits, value [1, \u{663}]);",
            expected_fragments: &[
                "/project/declarations/orders.sql has the bare number '\u{663}', written with non-ASCII digits",
                "Quote it to keep it as text",
            ],
        },
        DeclarationTextTestCase {
            description: "a non-ASCII bare word that is not a number is text",
            kind: CollectionKind::Enums,
            contents: "ENUM (name status, members (A münchen, B \u{2167}));",
            expected_fragments: &["Parsed", "münchen"],
        },
        DeclarationTextTestCase {
            description: "a camel-case name suggests snake case",
            kind: CollectionKind::Enums,
            contents: "ENUM (name HTTPStatusCode, members [A]);",
            expected_fragments: &[
                "ResourceIdentity",
                "Invalid public enum identity 'HTTPStatusCode' in /project/declarations/orders.sql; use snake_case 'http_status_code'",
                "Double underscores remain valid.",
            ],
        },
        DeclarationTextTestCase {
            description: "another declaration kind under the enums root",
            kind: CollectionKind::Enums,
            contents: "ENUM (name a, members [A]);\nCONSTANT (name b, value 1);",
            expected_fragments: &[
                "/project/declarations/orders.sql contains CONSTANT(...) under the enums root",
            ],
        },
        DeclarationTextTestCase {
            description: "a quoted parenthesis does not close the header",
            kind: CollectionKind::Enums,
            contents: "ENUM (name a, members ['x)']",
            expected_fragments: &[
                "/project/declarations/orders.sql has an unterminated declaration header",
            ],
        },
        DeclarationTextTestCase {
            description: "constants keep their options and stop at the first failure",
            kind: CollectionKind::Constants,
            contents: "CONSTANT (name a, value [1], render_as array);\nCONSTANT (name b, value constant(value 1, type integer));\nCONSTANT (name c);",
            expected_fragments: &[
                "name: \"a\", value: List([BareWord(\"1\")]), explicit_type: None, render_as: Some(\"array\")",
                "name: \"b\", value: BareWord(\"1\"), explicit_type: Some(\"integer\"), render_as: None",
                "/project/declarations/orders.sql constant 'c' is missing required value",
            ],
        },
        DeclarationTextTestCase {
            description: "a wrapped constant with outer options",
            kind: CollectionKind::Constants,
            contents: "CONSTANT (name a, value constant(value 1), type integer);",
            expected_fragments: &[
                "declarations: []",
                "/project/declarations/orders.sql constant 'a' cannot combine wrapper and outer options",
            ],
        },
        DeclarationTextTestCase {
            description: "an unknown render_as",
            kind: CollectionKind::Constants,
            contents: "CONSTANT (name a, value [1], render_as list);",
            expected_fragments: &[
                "/project/declarations/orders.sql constant 'a' render_as must be value_list or array",
            ],
        },
        DeclarationTextTestCase {
            description: "schema column locations over CRLF lines",
            kind: CollectionKind::ModelSchemas,
            contents: "SCHEMA (\r\n  name shape,\r\n  columns (\r\n    id (type INT),\r\n  ),\r\n);",
            expected_fragments: &[
                "(\"id\", LineColumnSpan { line: 4, column: 5, end_line: 4, end_column: 7 })",
                "failure: None",
            ],
        },
        DeclarationTextTestCase {
            description: "a schema extending a non-identifier",
            kind: CollectionKind::ModelSchemas,
            contents: "SCHEMA (name shape, extends 'a b', columns (id (type INT)));",
            expected_fragments: &[
                "/project/declarations/orders.sql schema 'shape' extends must be an identifier",
            ],
        },
        DeclarationTextTestCase {
            description: "a SQL function",
            kind: CollectionKind::SqlFunctions,
            contents: " FUNCTION (returns INT);\n  SELECT 1 \n",
            expected_fragments: &["body_sql: \"SELECT 1\""],
        },
        DeclarationTextTestCase {
            description: "a SQL function with an unsupported key",
            kind: CollectionKind::SqlFunctions,
            contents: "FUNCTION (\n  returns INT,\n  retuns INT\n);\nSELECT 1",
            expected_fragments: &[
                "ModelSql",
                "FUNCTION() in '/project/declarations/orders.sql:3' has unsupported keys: retuns",
                "did you mean 'returns'?",
            ],
        },
        DeclarationTextTestCase {
            description: "a hook body is dedented",
            kind: CollectionKind::SqlHooks,
            contents: "HOOK (description 'Refresh');\n    SELECT 1\n    FROM t\n",
            expected_fragments: &[
                "sql_body: \"SELECT 1\\nFROM t\", name: \"orders\", description: Some(\"Refresh\")",
            ],
        },
        DeclarationTextTestCase {
            description: "a hook header without a terminator",
            kind: CollectionKind::SqlHooks,
            contents: "HOOK () SELECT 1",
            expected_fragments: &[
                "SqlHook",
                "SQL hook '/project/declarations/orders.sql' HOOK(...) header must end with ';'",
            ],
        },
        DeclarationTextTestCase {
            description: "violation and measurement audit blocks",
            kind: CollectionKind::Audits,
            contents: "audit (name a);\nSELECT 1\nAUDIT (name b, evaluation measurement, value v);\nMEASURE (SELECT 1 AS v);\nEVIDENCE (SELECT 2);\n",
            expected_fragments: &[
                "audit_index: 1",
                "sql_body: \"SELECT 1\", name: Some(\"a\"), evaluation_mode: \"violations\"",
                "evaluation_mode: \"measurement\", measure_sql: Some(\"SELECT 1 AS v\"), evidence_sql: Some(\"SELECT 2\")",
            ],
        },
        DeclarationTextTestCase {
            description: "a dotless i spells AUDIT for Python's upper()",
            kind: CollectionKind::Audits,
            contents: "AUD\u{131}T ();\nSELECT 1",
            expected_fragments: &["Parsed(Audit(", "sql_body: \"SELECT 1\""],
        },
        DeclarationTextTestCase {
            description: "unnamed blocks in a multi-block audit file",
            kind: CollectionKind::Audits,
            contents: "AUDIT ();\nSELECT 1\nAUDIT (name b);\nSELECT 2\n",
            expected_fragments: &[
                "SqlAudit",
                "contains multiple AUDIT blocks; every block must define a unique `name`. Missing names for blocks: 1",
            ],
        },
        DeclarationTextTestCase {
            description: "a violation audit written as a measurement",
            kind: CollectionKind::Audits,
            contents: "AUDIT ();\n-- note\nMEASURE (SELECT 1);",
            expected_fragments: &[
                "Violation audit '/project/declarations/orders.sql' must use a bare SELECT body, not MEASURE/EVIDENCE",
            ],
        },
        DeclarationTextTestCase {
            description: "two statements in a MEASURE block",
            kind: CollectionKind::Audits,
            contents: "AUDIT (evaluation measurement, value v);\nMEASURE (SELECT 1; SELECT 2);",
            expected_fragments: &[
                "MEASURE(...) in '/project/declarations/orders.sql' must contain exactly one query",
            ],
        },
        DeclarationTextTestCase {
            description: "seeds have no authored text",
            kind: CollectionKind::Seeds,
            contents: "id\n1\n",
            expected_fragments: &["None"],
        },
    ];
    for test_case in test_cases {
        let debug: String = parsed_debug(test_case.kind, test_case.contents);
        let found: Vec<&str> = test_case
            .expected_fragments
            .iter()
            .copied()
            .filter(|fragment| debug.contains(fragment))
            .collect();
        assert_eq!(
            found, test_case.expected_fragments,
            "{}: {debug}",
            test_case.description
        );
    }
}

#[test]
fn given_deeply_nested_declaration_headers_when_parsing_then_each_reports_its_file_line() {
    let test_cases = [
        DeepDeclarationTestCase {
            description: "a constant value",
            kind: CollectionKind::Constants,
            prefix: "CONSTANT (\n  name limits,\n  value ",
            suffix: ",\n);\n",
            expected_location: ("CONSTANT", 3),
        },
        DeepDeclarationTestCase {
            description: "a hook description",
            kind: CollectionKind::SqlHooks,
            prefix: "HOOK (\n  description ",
            suffix: ",\n);\n\nSELECT 1\n",
            expected_location: ("HOOK", 2),
        },
        DeepDeclarationTestCase {
            description: "a function return type",
            kind: CollectionKind::SqlFunctions,
            prefix: "FUNCTION (\n  description \"Whether placed\",\n  returns ",
            suffix: ",\n);\n\norder_status = 'placed'\n",
            expected_location: ("FUNCTION", 3),
        },
        DeepDeclarationTestCase {
            description: "an audit value on a later block",
            kind: CollectionKind::Audits,
            prefix: "AUDIT (name a);\nSELECT 1\nAUDIT (\n  name b,\n  value ",
            suffix: ",\n);\nSELECT 2\n",
            expected_location: ("AUDIT", 5),
        },
    ];

    for test_case in test_cases {
        let contents: String = format!(
            "{}{}1{}{}",
            test_case.prefix,
            "[".repeat(20_000),
            "]".repeat(20_000),
            test_case.suffix
        );

        let debug: String = parsed_debug(test_case.kind, &contents);

        assert_eq!(
            debug,
            nesting_failure_debug(test_case.expected_location),
            "{}",
            test_case.description
        );
    }
}
