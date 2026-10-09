use crate::macro_arguments::tests::helpers::spelled_arguments;
use crate::macro_arguments::tests::test_types::ParseMacroArgumentsTestCase;

#[test]
fn given_argument_text_when_parsing_then_values_match_python_literals() {
    let test_cases = [
        ParseMacroArgumentsTestCase {
            description: "scalars, containers and keywords",
            text: "'a', 1, 2.5, True, None, [1, (2,)], {'k': -3}, (), x=+1.0, y=[]",
            nested: &[],
            expected: "\"a\", 1, f2.5, True, None, [1, (2)], {\"k\": -3}, () | x=+f1.0, y=[] | ",
        },
        ParseMacroArgumentsTestCase {
            description: "adjacent, raw, escaped and triple-quoted strings",
            text: "'it''s', \"a\" 'b', r'\\d', '\\x41\\u00e9\\N{LATIN SMALL LETTER E WITH ACUTE}\\101\\q', '''x\\ny'''",
            nested: &[],
            expected: "\"its\", \"ab\", \"\\\\d\", \"AééA\\\\q\", \"x\\ny\" |  | ",
        },
        ParseMacroArgumentsTestCase {
            description: "integer radixes, underscores and float forms",
            text: "0x_ff, 0o17, 0b1_0, 1_000, 00, .5, 5., 1e-3, 1_0.0_1E+2",
            nested: &[],
            expected: "ff/16, 17/8, 10/2, 1000, 00, f.5, f5., f1e-3, f10.01e+2 |  | ",
        },
        ParseMacroArgumentsTestCase {
            description: "typed references in ast.walk order",
            text: "[__ref('a')], __source(\"b\",), k=__seed('c')",
            nested: &[],
            expected: "[__ref(a)], __source(b) | k=__seed(c) | __source:b, __ref:a, __seed:c",
        },
        ParseMacroArgumentsTestCase {
            description: "nested calls fill their spans, even under unary minus",
            text: "@m(1), -@n()",
            nested: &[(0, 5), (8, 12)],
            expected: "@0, -@1 |  | ",
        },
        ParseMacroArgumentsTestCase {
            description: "a keyword name is NFKC-normalized",
            text: "ﬁeld=1",
            nested: &[],
            expected: " | field=1 | ",
        },
        ParseMacroArgumentsTestCase {
            description: "comments and line continuations",
            text: "1, # note\n 2, \\\n 3",
            nested: &[],
            expected: "1, 2, 3 |  | ",
        },
        ParseMacroArgumentsTestCase {
            description: "unary signs over booleans and other signs",
            text: "-True, +-1",
            nested: &[],
            expected: "-True, +-1 |  | ",
        },
        ParseMacroArgumentsTestCase {
            description: "a bytes literal is rejected",
            text: "b'x'",
            nested: &[],
            expected: "error: use a bytes literal @1:1",
        },
        ParseMacroArgumentsTestCase {
            description: "a complex literal is rejected",
            text: "1, 2j",
            nested: &[],
            expected: "error: use a complex number literal @1:4",
        },
        ParseMacroArgumentsTestCase {
            description: "an Ellipsis is rejected",
            text: "...",
            nested: &[],
            expected: "error: use '...' (Ellipsis) @1:1",
        },
        ParseMacroArgumentsTestCase {
            description: "an f-string is rejected",
            text: "f'{x}'",
            nested: &[],
            expected: "error: use an f-string @1:1",
        },
        ParseMacroArgumentsTestCase {
            description: "bytes joined to a string are rejected",
            text: "'a' b'c'",
            nested: &[],
            expected: "error: use a bytes literal @1:1",
        },
        ParseMacroArgumentsTestCase {
            description: "an empty typed reference name",
            text: "__ref('')",
            nested: &[],
            expected: "error: must give __ref() exactly one quoted resource name @1:1",
        },
        ParseMacroArgumentsTestCase {
            description: "a bare name",
            text: "x",
            nested: &[],
            expected: "error: must use only Python literals, nested macro calls, and __ref(), __source(), or __seed() references @1:1",
        },
        ParseMacroArgumentsTestCase {
            description: "a binary operation",
            text: "1 + 2",
            nested: &[],
            expected: "error: must use only Python literals, nested macro calls, and __ref(), __source(), or __seed() references @1:3",
        },
        ParseMacroArgumentsTestCase {
            description: "a set",
            text: "{1, 2}",
            nested: &[],
            expected: "error: must use only Python literals, nested macro calls, and __ref(), __source(), or __seed() references @1:1",
        },
        ParseMacroArgumentsTestCase {
            description: "keyword expansion",
            text: "**k",
            nested: &[],
            expected: "error: must not use **kwargs expansion syntax @1:3",
        },
        ParseMacroArgumentsTestCase {
            description: "dict unpacking",
            text: "{**d}",
            nested: &[],
            expected: "error: must not use dict unpacking @1:4",
        },
        ParseMacroArgumentsTestCase {
            description: "unary minus on text",
            text: "-'a'",
            nested: &[],
            expected: "error: use unary + or - on a value that is not a number @1:1",
        },
        ParseMacroArgumentsTestCase {
            description: "a positional argument after a keyword",
            text: "x=1, 2",
            nested: &[],
            expected: "error: could not be parsed: a positional argument follows a keyword argument @1:6",
        },
        ParseMacroArgumentsTestCase {
            description: "a repeated keyword",
            text: "x=1, x=2",
            nested: &[],
            expected: "error: could not be parsed: keyword argument 'x' is repeated @1:6",
        },
        ParseMacroArgumentsTestCase {
            description: "a doubled comma",
            text: "'amount',,",
            nested: &[],
            expected: "error: could not be parsed: a value is missing here @1:10",
        },
        ParseMacroArgumentsTestCase {
            description: "an unclosed string",
            text: "'abc",
            nested: &[],
            expected: "error: could not be parsed: a string is not closed @1:1",
        },
        ParseMacroArgumentsTestCase {
            description: "an unclosed bracket on a later line",
            text: "[1,\n 2",
            nested: &[],
            expected: "error: could not be parsed: a bracket is not closed with ']' @1:1",
        },
        ParseMacroArgumentsTestCase {
            description: "an error on a later line",
            text: "1,\n  x",
            nested: &[],
            expected: "error: must use only Python literals, nested macro calls, and __ref(), __source(), or __seed() references @2:3",
        },
        ParseMacroArgumentsTestCase {
            description: "a lone surrogate escape",
            text: "'\\ud800'",
            nested: &[],
            expected: "error: contain the lone surrogate escape '\\ud800' @1:2",
        },
        ParseMacroArgumentsTestCase {
            description: "leading zeros in a decimal integer",
            text: "007",
            nested: &[],
            expected: "error: could not be parsed: leading zeros in a decimal integer are not allowed; use 0o for octal @1:1",
        },
        ParseMacroArgumentsTestCase {
            description: "a character Python rejects in a name",
            text: "1, é€",
            nested: &[],
            expected: "error: could not be parsed: the character '€' (U+20AC) is not valid in a name @1:4",
        },
        ParseMacroArgumentsTestCase {
            description: "a keyword used as an argument name",
            text: "True=1",
            nested: &[],
            expected: "error: could not be parsed: 'True' is a Python keyword, not an argument name @1:1",
        },
        ParseMacroArgumentsTestCase {
            description: "an unknown character name",
            text: "'\\N{NOPE}'",
            nested: &[],
            expected: "error: could not be parsed: \\N{NOPE} names no Unicode character @1:2",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            spelled_arguments(test_case.text, test_case.nested),
            test_case.expected,
            "{}",
            test_case.description
        );
    }
}
