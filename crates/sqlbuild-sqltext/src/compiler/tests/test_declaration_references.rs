use crate::compiler::tests::helpers::scanned_references;
use crate::compiler::tests::test_types::DeclarationReferenceScanTestCase;

#[test]
fn given_sql_when_scanning_declaration_references_then_python_offsets_are_returned() {
    let test_cases = [
        DeclarationReferenceScanTestCase {
            description: "enum members and constants in order with code-point offsets",
            sql: "SELECT 'é', @enum(\"order_status\").PLACED, @const( 'sales_cap' ) FROM t",
            expected_references: Some("enum:order_status.PLACED@12..40, const:sales_cap@42..63"),
        },
        DeclarationReferenceScanTestCase {
            description: "references inside quotes, comments and dollar literals are text",
            sql: "SELECT '@const(\"a\")', `@const(\"b\")`, $tag$@const(\"c\")$tag$ -- @const(\"d\")\n/* @enum(\"e\").X */ @const(\"f\")",
            expected_references: Some("const:f@93..104"),
        },
        DeclarationReferenceScanTestCase {
            description: "a word after the keyword is not a reference and a $ inside a word is code",
            sql: "SELECT @constant, price$1, @const(\"cap\")",
            expected_references: Some("const:cap@27..40"),
        },
        DeclarationReferenceScanTestCase {
            description: "doubled single quotes stay inside the string",
            sql: "SELECT 'it''s @const(\"a\")', @const(\"b\")",
            expected_references: Some("const:b@28..39"),
        },
        DeclarationReferenceScanTestCase {
            description: "doubled backticks close and reopen quoted text, leaving it unclosed",
            sql: "SELECT 'it''s @const(\"a\")', `x``@const(\"b\")",
            expected_references: Some(" | stop:quote"),
        },
        DeclarationReferenceScanTestCase {
            description: "SQL without references is not scanned for unclosed quotes",
            sql: "SELECT 'unterminated",
            expected_references: Some(""),
        },
        DeclarationReferenceScanTestCase {
            description: "an unclosed quote before a reference stops the walk",
            sql: "SELECT @const(\"a\"), 'unterminated @const(\"b\")",
            expected_references: Some("const:a@7..18 | stop:quote"),
        },
        DeclarationReferenceScanTestCase {
            description: "a malformed enum reference stops the walk after earlier references",
            sql: "SELECT @const(\"a\"), @enum(\"order_status\"), @const(\"b\")",
            expected_references: Some("const:a@7..18 | stop:invalid enum"),
        },
        DeclarationReferenceScanTestCase {
            description: "a malformed constant reference at the end of the text stops the walk",
            sql: "SELECT @const",
            expected_references: Some(" | stop:invalid const"),
        },
        DeclarationReferenceScanTestCase {
            description: "Unicode whitespace inside and after the keyword matches Python's \\s",
            sql: "SELECT @enum\u{a0}(\u{2003}'order_status'\u{1c}) .\u{3000}PLACED",
            expected_references: Some("enum:order_status.PLACED@7..40"),
        },
        DeclarationReferenceScanTestCase {
            description: "a non-ASCII character after the keyword defers its word boundary to Python",
            sql: "SELECT @consté",
            expected_references: None,
        },
        DeclarationReferenceScanTestCase {
            description: "an unclosed block comment before a reference stops the walk",
            sql: "SELECT /* open @const(\"a\")",
            expected_references: Some(" | stop:comment"),
        },
        DeclarationReferenceScanTestCase {
            description: "an unclosed dollar literal before a reference stops the walk",
            sql: "SELECT $tag$ @const(\"a\")",
            expected_references: Some(" | stop:quote"),
        },
    ];

    for test_case in test_cases {
        let scanned = scanned_references(test_case.sql);

        assert_eq!(
            scanned.as_deref(),
            test_case.expected_references,
            "{}",
            test_case.description
        );
    }
}
