use crate::header_strings::constants::{
    DOUBLE_QUOTE_INSIDE_MESSAGE, TRIPLE_QUOTE_INSIDE_MESSAGE, UNCLOSED_TRIPLE_QUOTE_MESSAGE,
};
use crate::header_strings::main::closes_inside_text::closes_inside_text;
use crate::header_strings::main::fold_prose::fold_prose;
use crate::header_strings::main::header_quoted_end::header_quoted_end;
use crate::header_strings::main::prose_string::prose_string;
use crate::header_strings::main::quote_failure::quote_failure;
use crate::header_strings::main::triple_quoted_end::triple_quoted_end;
use crate::header_strings::models::{HeaderQuote, TripleQuoteError};
use crate::header_strings::tests::test_types::{
    FoldTestCase, ProseTestCase, QuoteFailureTestCase, QuotedEndTestCase, TripleEndTestCase,
};

fn chars(text: &str) -> Vec<char> {
    text.chars().collect()
}

#[test]
fn given_written_prose_when_folding_then_line_breaks_are_spaces_and_blank_lines_paragraphs() {
    let test_cases = [
        FoldTestCase {
            description: "one line is kept exactly, outer and inner spaces included",
            written: "  Orders  by day ",
            expected: "  Orders  by day ",
        },
        FoldTestCase {
            description: "a break and the indentation after it is one space",
            written: "Orders placed\n    by day.",
            expected: "Orders placed by day.",
        },
        FoldTestCase {
            description: "continuation at column zero folds the same as indented",
            written: "Orders placed\nby day.",
            expected: "Orders placed by day.",
        },
        FoldTestCase {
            description: "trailing spaces before a break fold into the one space",
            written: "Orders placed   \n  by day.",
            expected: "Orders placed by day.",
        },
        FoldTestCase {
            description: "a blank line starts a paragraph",
            written: "First paragraph\ncontinues.\n   \n  Second.",
            expected: "First paragraph continues.\n\nSecond.",
        },
        FoldTestCase {
            description: "a block's leading and closing line breaks are dropped",
            written: "\n    Orders by day.\n  ",
            expected: "Orders by day.",
        },
        FoldTestCase {
            description: "spaces inside a line are kept",
            written: "a  b\nc",
            expected: "a  b c",
        },
        FoldTestCase {
            description: "Windows line endings fold like line feeds",
            written: "a\r\n  b\r\n\r\nc",
            expected: "a b\n\nc",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            fold_prose(test_case.written),
            test_case.expected,
            "{}",
            test_case.description
        );
        assert_eq!(
            fold_prose(&fold_prose(test_case.written)),
            fold_prose(test_case.written),
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
            expected: Ok((6, 9)),
        },
        TripleEndTestCase {
            description: "inner quotes and apostrophes need no escaping",
            text: r#""""say "hi", it's"""x"#,
            expected: Ok((17, 20)),
        },
        TripleEndTestCase {
            description: "up to two quotes before the delimiter end the text",
            text: r#""""say "hi"""""#,
            expected: Ok((11, 14)),
        },
        TripleEndTestCase {
            description: "a run of six quotes is a delimiter inside the text",
            text: r#""""a""""""b"""#,
            expected: Err(TripleQuoteError::Inside(4)),
        },
        TripleEndTestCase {
            description: "never closed",
            text: r#""""abc "" def"#,
            expected: Err(TripleQuoteError::Unclosed),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            triple_quoted_end(&chars(test_case.text), 0),
            test_case.expected,
            "{}",
            test_case.description
        );
        assert_eq!(
            triple_quoted_end(test_case.text.as_bytes(), 0),
            test_case.expected,
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
            expected: Some(6),
        },
        QuotedEndTestCase {
            description: "an apostrophe inside double quotes",
            text: r#""it's" rest"#,
            expected: Some(6),
        },
        QuotedEndTestCase {
            description: "a triple-quoted string with parentheses and one quote",
            text: r#""""5" pipe (x);""") rest"#,
            expected: Some(18),
        },
        QuotedEndTestCase {
            description: "an unclosed triple-quoted string",
            text: r#""""never"#,
            expected: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            header_quoted_end(&chars(test_case.text), 0),
            test_case.expected,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_closing_triple_quote_when_text_follows_then_it_was_inside_the_text() {
    let text: Vec<char> = chars(r#"a """b""" c""" d"#);
    let separated: Vec<char> = chars("a \"\"\"b\"\"\", tags x");
    let glued: Vec<char> = chars("\"\"\"b\"\"\"c");

    assert!(closes_inside_text(&text, 9));
    assert!(!closes_inside_text(&separated, 9));
    assert!(closes_inside_text(&glued, 7));
}

#[test]
fn given_prose_string_when_reading_then_text_is_folded_and_escaped_quotes_rejected() {
    let test_cases = [
        ProseTestCase {
            description: "a one-line double-quoted string keeps its text",
            text: r#""Orders by day.""#,
            expected: Ok((HeaderQuote::Double, "Orders by day.")),
        },
        ProseTestCase {
            description: "a wrapped double-quoted string is folded",
            text: "\"Orders placed\n  by day.\"",
            expected: Ok((HeaderQuote::Double, "Orders placed by day.")),
        },
        ProseTestCase {
            description: "a triple-quoted string on one line keeps its quotes",
            text: r#""""Matches "Miss".""""#,
            expected: Ok((HeaderQuote::Triple, r#"Matches "Miss"."#)),
        },
        ProseTestCase {
            description: "a triple-quoted block is folded",
            text: "\"\"\"\n    True for \"Mrs. C. O'Leary\",\n    any case.\n  \"\"\"",
            expected: Ok((
                HeaderQuote::Triple,
                r#"True for "Mrs. C. O'Leary", any case."#,
            )),
        },
        ProseTestCase {
            description: "backslashes are ordinary characters",
            text: r#""C:\data\ and \\ stay""#,
            expected: Ok((HeaderQuote::Double, r"C:\data\ and \\ stay")),
        },
        ProseTestCase {
            description: "an escaped double quote is rejected at the quote",
            text: r#""Matches \"Miss\".""#,
            expected: Err(r#"double quote inside a "..." string at position 10"#),
        },
        ProseTestCase {
            description: "an unclosed triple-quoted string reports where it starts",
            text: r#""""never closed"#,
            expected: Err(r#"unclosed """ string starting at position 0"#),
        },
    ];

    for test_case in test_cases {
        let actual =
            prose_string(&chars(test_case.text), 0).map(|prose| (prose.quote, prose.value));
        let expected = test_case
            .expected
            .map(|(quote, value)| (quote, value.to_owned()))
            .map_err(str::to_owned);
        assert_eq!(actual, expected, "{}", test_case.description);
    }
}

#[test]
fn given_quote_error_when_locating_then_line_and_column_are_in_the_file() {
    let test_cases = [
        QuoteFailureTestCase {
            description: "on the header's first line, after its opening column",
            error: r#"double quote inside a "..." string at position 18"#,
            header: r#"description "Say \"hi\"""#,
            expected: Some((3, 26, DOUBLE_QUOTE_INSIDE_MESSAGE)),
        },
        QuoteFailureTestCase {
            description: "a message that only ends like a quote error is not one",
            error: r#""""...""" string at position 0"#,
            header: "x",
            expected: None,
        },
        QuoteFailureTestCase {
            description: "an unclosed triple quote on the second line",
            error: r#"unclosed """ string starting at position 15"#,
            header: "\n  description \"\"\"never",
            expected: Some((4, 15, UNCLOSED_TRIPLE_QUOTE_MESSAGE)),
        },
        QuoteFailureTestCase {
            description: "a triple quote inside the text",
            error: r#"""" inside a """...""" string at position 2"#,
            header: "ab",
            expected: Some((3, 10, TRIPLE_QUOTE_INSIDE_MESSAGE)),
        },
        QuoteFailureTestCase {
            description: "any other header error is not a quote failure",
            error: "expected key at position 3",
            header: "abcd",
            expected: None,
        },
    ];

    for test_case in test_cases {
        let actual = quote_failure(test_case.error, test_case.header, (3, 8))
            .map(|failure| (failure.line, failure.column, failure.message));
        let expected = test_case
            .expected
            .map(|(line, column, message)| (line, column, message.to_owned()));
        assert_eq!(actual, expected, "{}", test_case.description);
    }
}
