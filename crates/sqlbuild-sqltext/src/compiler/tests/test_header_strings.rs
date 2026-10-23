use crate::compiler::tests::helpers::parsed_string;
use crate::compiler::tests::test_types::HeaderStringTestCase;

#[test]
fn given_header_strings_when_parsing_then_prose_is_folded_and_other_text_kept_as_written() {
    let test_cases = [
        HeaderStringTestCase {
            description: "a wrapped description is folded",
            header: "description \"Orders placed\nby day, one row each.\"",
            path: &["description"],
            expected_value: Ok("Orders placed by day, one row each."),
        },
        HeaderStringTestCase {
            description: "a triple-quoted description on one line keeps its quotes",
            header: r#"description """Matches "Miss".""", materialized table"#,
            path: &["description"],
            expected_value: Ok(r#"Matches "Miss"."#),
        },
        HeaderStringTestCase {
            description: "a triple-quoted block is folded with paragraphs",
            header: "description \"\"\"\n    A \"quoted\" word,\n    it's fine.\n\n    Second.\n  \"\"\",\n  materialized table",
            path: &["description"],
            expected_value: Ok("A \"quoted\" word, it's fine.\n\nSecond."),
        },
        HeaderStringTestCase {
            description: "the same text on one line or wrapped stores the same",
            header: "description \"True for a woman's title: Mme, Mlle,\n  Miss (any case).\"",
            path: &["description"],
            expected_value: Ok("True for a woman's title: Mme, Mlle, Miss (any case)."),
        },
        HeaderStringTestCase {
            description: "a column description is prose",
            header: "columns (order_id (type BIGINT, description \"The order\n  key.\"))",
            path: &["columns", "order_id", "description"],
            expected_value: Ok("The order key."),
        },
        HeaderStringTestCase {
            description: "an audit's description option is prose",
            header: "audits [not_null(column 'id', description \"Every row\n  has one.\")]",
            path: &["audits", "[0]", "not_null", "description"],
            expected_value: Ok("Every row has one."),
        },
        HeaderStringTestCase {
            description: "a description may end in a backslash",
            header: "description \"ends in C:\\\",\n  materialized table",
            path: &["description"],
            expected_value: Ok("ends in C:\\"),
        },
        HeaderStringTestCase {
            description: "a one-line description keeps doubled backslashes",
            header: r#"description "Path C:\\temp""#,
            path: &["description"],
            expected_value: Ok(r"Path C:\\temp"),
        },
        HeaderStringTestCase {
            description: "a backslash escapes a quote in a single-quoted description",
            header: r"description 'it\'s fine', materialized table",
            path: &["description"],
            expected_value: Ok("it's fine"),
        },
        HeaderStringTestCase {
            description: "a doubled quote is one quote in a single-quoted description",
            header: "description 'it''s fine', materialized table",
            path: &["description"],
            expected_value: Ok("it's fine"),
        },
        HeaderStringTestCase {
            description: "doubled double quotes in a description fail at the second quote",
            header: r#"description "say ""hi"" now""#,
            path: &["description"],
            expected_value: Err(r#"double quote inside a "..." string at position 17"#),
        },
        HeaderStringTestCase {
            description: "a single quote inside a single-quoted description fails",
            header: "description 'it's fine'",
            path: &["description"],
            expected_value: Err("single quote inside a '...' string at position 15"),
        },
        HeaderStringTestCase {
            description: "adjacent list strings outside descriptions read as before",
            header: r#"description "x", tags ["a""b"]"#,
            path: &["tags", "[1]"],
            expected_value: Ok("b"),
        },
        HeaderStringTestCase {
            description: "a string followed by another kind of quote reads as before",
            header: r#"description "x", tags ["x"'y']"#,
            path: &["tags", "[1]"],
            expected_value: Ok("y"),
        },
        HeaderStringTestCase {
            description: "a meta value keeps its line breaks",
            header: "meta (description \"kept\n  as written\")",
            path: &["meta", "description"],
            expected_value: Ok("kept\n  as written"),
        },
        HeaderStringTestCase {
            description: "an audit predicate keeps its line breaks",
            header: "audits [expression(predicate \"a > 0\n  AND b > 0\")]",
            path: &["audits", "[0]", "expression", "predicate"],
            expected_value: Ok("a > 0\n  AND b > 0"),
        },
        HeaderStringTestCase {
            description: "a triple-quoted SQL string keeps backslashes and quotes",
            header: r#"name_pattern """^"x"\d+$""""#,
            path: &["name_pattern"],
            expected_value: Ok(r#"^"x"\d+$"#),
        },
        HeaderStringTestCase {
            description: "a non-prose string still reads backslash escapes",
            header: r#"name_pattern "a\"b""#,
            path: &["name_pattern"],
            expected_value: Ok("a\"b"),
        },
        HeaderStringTestCase {
            description: "an escaped double quote in a description fails at the quote",
            header: r#"description "Matches a title (\"Miss\").""#,
            path: &["description"],
            expected_value: Err(r#"double quote inside a "..." string at position 31"#),
        },
        HeaderStringTestCase {
            description: "a wrapped escaped quote with apostrophes fails the same way",
            header: "description \"A woman's title, with or without a dot\n(\\\"MISS ANNA PARKER\\\", \\\"Mrs. C. O'Brien\\\").\"",
            path: &["description"],
            expected_value: Err(r#"double quote inside a "..." string at position 54"#),
        },
        HeaderStringTestCase {
            description: "a bare double quote ends the string where text runs on",
            header: r#"description "Matches "Miss" here""#,
            path: &["description"],
            expected_value: Err(r#"double quote inside a "..." string at position 21"#),
        },
        HeaderStringTestCase {
            description: "a triple quote inside a triple-quoted string",
            header: r#"description """He said """hi""" then""""#,
            path: &["description"],
            expected_value: Err(r#"""" inside a """...""" string at position 23"#),
        },
        HeaderStringTestCase {
            description: "a triple quote inside, followed by more text on the line",
            header: r#"description """a """ b""""#,
            path: &["description"],
            expected_value: Err(r#"""" inside a """...""" string at position 17"#),
        },
        HeaderStringTestCase {
            description: "an unclosed triple-quoted string reports where it started",
            header: "description \"\"\"\n  never closed\n",
            path: &["description"],
            expected_value: Err(r#"unclosed """ string starting at position 12"#),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            parsed_string(test_case.header, test_case.path),
            test_case
                .expected_value
                .map(str::to_owned)
                .map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
