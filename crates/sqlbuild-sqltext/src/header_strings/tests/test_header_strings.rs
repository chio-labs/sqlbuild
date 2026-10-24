use crate::header_strings::constants::{
    DOUBLE_QUOTE_INSIDE_MESSAGE, TRIPLE_QUOTE_INSIDE_MESSAGE, UNCLOSED_TRIPLE_QUOTE_MESSAGE,
};
use crate::header_strings::errors::TripleQuoteError;
use crate::header_strings::main::closes_inside_text::closes_inside_text;
use crate::header_strings::main::fold_prose::fold_prose;
use crate::header_strings::main::header_quoted_end::header_quoted_end;
use crate::header_strings::main::prose_string::prose_string;
use crate::header_strings::main::quote_failure::quote_failure;
use crate::header_strings::main::triple_quoted_end::triple_quoted_end;
use crate::header_strings::models::HeaderQuote;
use crate::header_strings::tests::helpers::chars;
use crate::header_strings::tests::test_types::{
    ClosesInsideTestCase, DescriptionEndTestCase, FoldTestCase, ProseTestCase,
    QuoteFailureTestCase, QuotedEndTestCase, TripleEndTestCase,
};

#[test]
fn given_written_prose_when_folding_then_line_breaks_are_spaces_and_blank_lines_paragraphs() {
    let test_cases = [
        FoldTestCase {
            description: "one line is kept exactly, outer and inner spaces included",
            written: "  Orders  by day ",
            expected_folded: "  Orders  by day ",
        },
        FoldTestCase {
            description: "a break and the indentation after it is one space",
            written: "Orders placed\n    by day.",
            expected_folded: "Orders placed by day.",
        },
        FoldTestCase {
            description: "continuation at column zero folds the same as indented",
            written: "Orders placed\nby day.",
            expected_folded: "Orders placed by day.",
        },
        FoldTestCase {
            description: "trailing spaces before a break fold into the one space",
            written: "Orders placed   \n  by day.",
            expected_folded: "Orders placed by day.",
        },
        FoldTestCase {
            description: "a blank line starts a paragraph",
            written: "First paragraph\ncontinues.\n   \n  Second.",
            expected_folded: "First paragraph continues.\n\nSecond.",
        },
        FoldTestCase {
            description: "a block's leading and closing line breaks are dropped",
            written: "\n    Orders by day.\n  ",
            expected_folded: "Orders by day.",
        },
        FoldTestCase {
            description: "spaces inside a line are kept",
            written: "a  b\nc",
            expected_folded: "a  b c",
        },
        FoldTestCase {
            description: "Windows line endings fold like line feeds",
            written: "a\r\n  b\r\n\r\nc",
            expected_folded: "a b\n\nc",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            fold_prose(test_case.written),
            test_case.expected_folded,
            "{}",
            test_case.description
        );
        assert_eq!(
            fold_prose(test_case.expected_folded),
            test_case.expected_folded,
            "folding is stable: {}",
            test_case.description
        );
    }
}

#[test]
fn given_triple_quoted_text_when_finding_its_end_then_quotes_inside_belong_to_the_text() {
    let test_cases = [
        TripleEndTestCase {
            description: "plain text",
            text: r#""""abc""""#,
            expected_end: Ok((6, 9)),
        },
        TripleEndTestCase {
            description: "inner quotes and apostrophes need no escaping",
            text: r#""""say "hi", it's"""x"#,
            expected_end: Ok((17, 20)),
        },
        TripleEndTestCase {
            description: "up to two quotes before the delimiter end the text",
            text: r#""""say "hi"""""#,
            expected_end: Ok((11, 14)),
        },
        TripleEndTestCase {
            description: "a run of six quotes is a delimiter inside the text",
            text: r#""""a""""""b"""#,
            expected_end: Err(TripleQuoteError::Inside(4)),
        },
        TripleEndTestCase {
            description: "never closed",
            text: r#""""abc "" def"#,
            expected_end: Err(TripleQuoteError::Unclosed),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            triple_quoted_end(&chars(test_case.text), 0),
            test_case.expected_end,
            "{}",
            test_case.description
        );
        assert_eq!(
            triple_quoted_end(test_case.text.as_bytes(), 0),
            test_case.expected_end,
            "bytes: {}",
            test_case.description
        );
    }
}

#[test]
fn given_header_string_when_finding_its_end_then_triple_and_escaped_quotes_are_skipped() {
    let test_cases = [
        QuotedEndTestCase {
            description: "double quotes with a backslash escape",
            text: r#""a\"b" rest"#,
            expected_end: Some(6),
        },
        QuotedEndTestCase {
            description: "an apostrophe inside double quotes",
            text: r#""it's" rest"#,
            expected_end: Some(6),
        },
        QuotedEndTestCase {
            description: "a triple-quoted string with parentheses and one quote",
            text: r#""""5" pipe (x);""") rest"#,
            expected_end: Some(18),
        },
        QuotedEndTestCase {
            description: "an unclosed triple-quoted string",
            text: r#""""never"#,
            expected_end: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            header_quoted_end(&chars(test_case.text), 0),
            test_case.expected_end,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_description_string_when_finding_its_end_then_prose_rules_decide_it() {
    let test_cases = [
        DescriptionEndTestCase {
            description: "a description may end in a backslash",
            text: r#"description "C:\", tags x"#,
            start: 12,
            expected_end: Some(17),
        },
        DescriptionEndTestCase {
            description: "any other string reads the backslash as an escape",
            text: r#"name "C:\", tags x""#,
            start: 5,
            expected_end: Some(19),
        },
        DescriptionEndTestCase {
            description: "a misquoted description still ends where the escape reading ends",
            text: r#"description "say \"hi\"", x"#,
            start: 12,
            expected_end: Some(24),
        },
        DescriptionEndTestCase {
            description: "a doubled single quote stays inside the description",
            text: "DESCRIPTION 'it''s', x",
            start: 12,
            expected_end: Some(19),
        },
        DescriptionEndTestCase {
            description: "a description inside meta reads the backslash as an escape",
            text: r#"meta (owner "ops", description "say \", then"), x"#,
            start: 31,
            expected_end: Some(45),
        },
        DescriptionEndTestCase {
            description: "a description after a closed meta value is prose again",
            text: r#"meta (owner "ops"), description "C:\", x"#,
            start: 32,
            expected_end: Some(37),
        },
        DescriptionEndTestCase {
            description: "a key that only ends in description is not one",
            text: r#"redescription "C:\", x""#,
            start: 14,
            expected_end: Some(23),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            header_quoted_end(&chars(test_case.text), test_case.start),
            test_case.expected_end,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_closing_triple_quote_when_text_follows_then_it_was_inside_the_text() {
    let test_cases = [
        ClosesInsideTestCase {
            description: "more text and another triple quote follow on the line",
            text: r#"a """b""" c""" d"#,
            end: 9,
            expected_inside: true,
        },
        ClosesInsideTestCase {
            description: "a separator follows",
            text: "a \"\"\"b\"\"\", tags x",
            end: 9,
            expected_inside: false,
        },
        ClosesInsideTestCase {
            description: "text runs straight on",
            text: "\"\"\"b\"\"\"c",
            end: 7,
            expected_inside: true,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            closes_inside_text(&chars(test_case.text), test_case.end),
            test_case.expected_inside,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_prose_string_when_reading_then_text_is_folded_and_escaped_quotes_rejected() {
    let test_cases = [
        ProseTestCase {
            description: "a one-line double-quoted string keeps its text",
            text: r#""Orders by day.""#,
            expected_prose: Ok((HeaderQuote::Double, "Orders by day.")),
        },
        ProseTestCase {
            description: "a wrapped double-quoted string is folded",
            text: "\"Orders placed\n  by day.\"",
            expected_prose: Ok((HeaderQuote::Double, "Orders placed by day.")),
        },
        ProseTestCase {
            description: "a triple-quoted string on one line keeps its quotes",
            text: r#""""Matches "Miss".""""#,
            expected_prose: Ok((HeaderQuote::Triple, r#"Matches "Miss"."#)),
        },
        ProseTestCase {
            description: "a triple-quoted block is folded",
            text: "\"\"\"\n    True for \"Mrs. C. O'Brien\",\n    any case.\n  \"\"\"",
            expected_prose: Ok((
                HeaderQuote::Triple,
                r#"True for "Mrs. C. O'Brien", any case."#,
            )),
        },
        ProseTestCase {
            description: "backslashes are ordinary characters",
            text: r#""C:\data\ and \\ stay""#,
            expected_prose: Ok((HeaderQuote::Double, r"C:\data\ and \\ stay")),
        },
        ProseTestCase {
            description: "an escaped double quote is rejected at the quote",
            text: r#""Matches \"Miss\".""#,
            expected_prose: Err(r#"double quote inside a "..." string at position 10"#),
        },
        ProseTestCase {
            description: "a backslash may end a double-quoted description",
            text: r#""ends in C:\""#,
            expected_prose: Ok((HeaderQuote::Double, r"ends in C:\")),
        },
        ProseTestCase {
            description: "an escaped quote before more text is inside the text",
            text: r#""C:\" more""#,
            expected_prose: Err(r#"double quote inside a "..." string at position 4"#),
        },
        ProseTestCase {
            description: "doubled double quotes are rejected at the second quote",
            text: r#""say ""hi"" now""#,
            expected_prose: Err(r#"double quote inside a "..." string at position 5"#),
        },
        ProseTestCase {
            description: "a backslash escapes a single quote",
            text: r"'it\'s here'",
            expected_prose: Ok((HeaderQuote::Single, "it's here")),
        },
        ProseTestCase {
            description: "a doubled single quote is one quote",
            text: "'it''s a long one'",
            expected_prose: Ok((HeaderQuote::Single, "it's a long one")),
        },
        ProseTestCase {
            description: "a lone single quote ends the string inside the text",
            text: "'it's fine'",
            expected_prose: Err("single quote inside a '...' string at position 3"),
        },
        ProseTestCase {
            description: "an unclosed triple-quoted string reports where it starts",
            text: r#""""never closed"#,
            expected_prose: Err(r#"unclosed """ string starting at position 0"#),
        },
    ];

    for test_case in test_cases {
        let actual = prose_string(&chars(test_case.text), 0);
        assert_eq!(
            actual
                .as_ref()
                .map(|prose| (prose.quote, prose.value.as_str()))
                .map_err(String::as_str),
            test_case.expected_prose,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_quote_error_when_locating_then_line_and_column_are_in_the_file() {
    let test_cases = [
        QuoteFailureTestCase {
            description: "on the header's first line, after its opening column",
            error: r#"double quote inside a "..." string at position 18"#,
            header: r#"description "Say \"hi\"""#,
            expected_failure: Some((3, 26, DOUBLE_QUOTE_INSIDE_MESSAGE)),
        },
        QuoteFailureTestCase {
            description: "a message that only ends like a quote error is not one",
            error: r#""""...""" string at position 0"#,
            header: "x",
            expected_failure: None,
        },
        QuoteFailureTestCase {
            description: "an unclosed triple quote on the second line",
            error: r#"unclosed """ string starting at position 15"#,
            header: "\n  description \"\"\"never",
            expected_failure: Some((4, 15, UNCLOSED_TRIPLE_QUOTE_MESSAGE)),
        },
        QuoteFailureTestCase {
            description: "a triple quote inside the text",
            error: r#"""" inside a """...""" string at position 2"#,
            header: "ab",
            expected_failure: Some((3, 10, TRIPLE_QUOTE_INSIDE_MESSAGE)),
        },
        QuoteFailureTestCase {
            description: "any other header error is not a quote failure",
            error: "expected key at position 3",
            header: "abcd",
            expected_failure: None,
        },
    ];

    for test_case in test_cases {
        let actual = quote_failure(test_case.error, test_case.header, (3, 8));
        assert_eq!(
            actual
                .as_ref()
                .map(|failure| (failure.line, failure.column, failure.message.as_str())),
            test_case.expected_failure,
            "{}",
            test_case.description
        );
    }
}
