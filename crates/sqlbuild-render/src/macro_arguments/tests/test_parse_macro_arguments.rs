use crate::macro_arguments::tests::helpers::spelled_arguments;
use crate::macro_arguments::tests::test_types::ParseMacroArgumentsTestCase;

#[test]
fn given_argument_text_when_parsing_then_values_match_python_literals() {
    let test_cases = [
        ParseMacroArgumentsTestCase {
            description: "scalars, containers and keywords",
            text: "'a', 1, 2.5, True, None, [1, (2,)], {'k': -3}, (), x=+1.0, y=[]",
            nested: &[],
            expected_plan: "Ok(MacroArguments { positional: [Str(\"a\"), Int { radix: 10, digits: \"1\" }, Float(\"2.5\"), Bool(true), None, List([Int { radix: 10, digits: \"1\" }, Tuple([Int { radix: 10, digits: \"2\" }])]), Dict([(Str(\"k\"), Negative(Int { radix: 10, digits: \"3\" }))]), Tuple([])], keywords: [(\"x\", Positive(Float(\"1.0\"))), (\"y\", List([]))], typed_references: [] })",
        },
        ParseMacroArgumentsTestCase {
            description: "adjacent, raw, escaped and triple-quoted strings",
            text: "'it''s', \"a\" 'b', r'\\d', '\\x41\\u00e9\\N{LATIN SMALL LETTER E WITH ACUTE}\\101\\q', '''x\\ny'''",
            nested: &[],
            expected_plan: "Ok(MacroArguments { positional: [Str(\"its\"), Str(\"ab\"), Str(\"\\\\d\"), Str(\"A\u{e9}\u{e9}A\\\\q\"), Str(\"x\\ny\")], keywords: [], typed_references: [] })",
        },
        ParseMacroArgumentsTestCase {
            description: "integer radixes, underscores and float forms",
            text: "0x_ff, 0o17, 0b1_0, 1_000, 00, .5, 5., 1e-3, 1_0.0_1E+2",
            nested: &[],
            expected_plan: "Ok(MacroArguments { positional: [Int { radix: 16, digits: \"ff\" }, Int { radix: 8, digits: \"17\" }, Int { radix: 2, digits: \"10\" }, Int { radix: 10, digits: \"1000\" }, Int { radix: 10, digits: \"00\" }, Float(\".5\"), Float(\"5.\"), Float(\"1e-3\"), Float(\"10.01e+2\")], keywords: [], typed_references: [] })",
        },
        ParseMacroArgumentsTestCase {
            description: "typed references in ast.walk order",
            text: "[__ref('a')], __source(\"b\",), k=__seed('c')",
            nested: &[],
            expected_plan: "Ok(MacroArguments { positional: [List([TypedReference { function: \"__ref\", name: \"a\" }]), TypedReference { function: \"__source\", name: \"b\" }], keywords: [(\"k\", TypedReference { function: \"__seed\", name: \"c\" })], typed_references: [(\"__source\", \"b\"), (\"__ref\", \"a\"), (\"__seed\", \"c\")] })",
        },
        ParseMacroArgumentsTestCase {
            description: "nested calls fill their spans, even under unary minus",
            text: "@m(1), -@n()",
            nested: &[(0, 5), (8, 12)],
            expected_plan: "Ok(MacroArguments { positional: [NestedCall(0), Negative(NestedCall(1))], keywords: [], typed_references: [] })",
        },
        ParseMacroArgumentsTestCase {
            description: "a keyword name is NFKC-normalized",
            text: "ﬁeld=1",
            nested: &[],
            expected_plan: "Ok(MacroArguments { positional: [], keywords: [(\"field\", Int { radix: 10, digits: \"1\" })], typed_references: [] })",
        },
        ParseMacroArgumentsTestCase {
            description: "comments and line continuations",
            text: "1, # note\n 2, \\\n 3",
            nested: &[],
            expected_plan: "Ok(MacroArguments { positional: [Int { radix: 10, digits: \"1\" }, Int { radix: 10, digits: \"2\" }, Int { radix: 10, digits: \"3\" }], keywords: [], typed_references: [] })",
        },
        ParseMacroArgumentsTestCase {
            description: "unary signs over booleans and other signs",
            text: "-True, +-1",
            nested: &[],
            expected_plan: "Ok(MacroArguments { positional: [Negative(Bool(true)), Positive(Negative(Int { radix: 10, digits: \"1\" }))], keywords: [], typed_references: [] })",
        },
        ParseMacroArgumentsTestCase {
            description: "a bytes literal is rejected",
            text: "b'x'",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"use a bytes literal\", help: \"Pass text as a string without the b prefix, for example \'orders\' instead of b\'orders\'\", line: 1, column: 1 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a complex literal is rejected",
            text: "1, 2j",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"use a complex number literal\", help: \"Pass int or float numbers; give a complex value\'s real and imaginary parts as two arguments\", line: 1, column: 4 })",
        },
        ParseMacroArgumentsTestCase {
            description: "an Ellipsis is rejected",
            text: "...",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"use \'...\' (Ellipsis)\", help: \"Pass None, or a string the macro understands, instead of \'...\'\", line: 1, column: 1 })",
        },
        ParseMacroArgumentsTestCase {
            description: "an f-string is rejected",
            text: "f'{x}'",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"use an f-string\", help: \"Pass the parts as separate arguments and format them in the macro\", line: 1, column: 1 })",
        },
        ParseMacroArgumentsTestCase {
            description: "bytes joined to a string are rejected",
            text: "'a' b'c'",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"use a bytes literal\", help: \"Pass text as a string without the b prefix, for example \'orders\' instead of b\'orders\'\", line: 1, column: 1 })",
        },
        ParseMacroArgumentsTestCase {
            description: "an empty typed reference name",
            text: "__ref('')",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"must give __ref() exactly one quoted resource name\", help: \"Write one quoted resource name, for example __ref(\\\"orders\\\")\", line: 1, column: 1 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a bare name",
            text: "x",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"must use only Python literals, nested macro calls, and __ref(), __source(), or __seed() references\", help: \"Macro arguments are Python literals (strings, numbers, True, False, None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() references; compute anything else inside the macro\", line: 1, column: 1 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a binary operation",
            text: "1 + 2",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"must use only Python literals, nested macro calls, and __ref(), __source(), or __seed() references\", help: \"Macro arguments are Python literals (strings, numbers, True, False, None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() references; compute anything else inside the macro\", line: 1, column: 3 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a set",
            text: "{1, 2}",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"must use only Python literals, nested macro calls, and __ref(), __source(), or __seed() references\", help: \"Macro arguments are Python literals (strings, numbers, True, False, None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() references; compute anything else inside the macro\", line: 1, column: 1 })",
        },
        ParseMacroArgumentsTestCase {
            description: "keyword expansion",
            text: "**k",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"must not use **kwargs expansion syntax\", help: \"Write each argument or key out explicitly\", line: 1, column: 3 })",
        },
        ParseMacroArgumentsTestCase {
            description: "dict unpacking",
            text: "{**d}",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"must not use dict unpacking\", help: \"Write each argument or key out explicitly\", line: 1, column: 4 })",
        },
        ParseMacroArgumentsTestCase {
            description: "unary minus on text",
            text: "-'a'",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"use unary + or - on a value that is not a number\", help: \"Macro arguments are Python literals (strings, numbers, True, False, None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() references; compute anything else inside the macro\", line: 1, column: 1 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a positional argument after a keyword",
            text: "x=1, 2",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: a positional argument follows a keyword argument\", help: \"Pass each keyword argument once, after every positional argument\", line: 1, column: 6 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a repeated keyword",
            text: "x=1, x=2",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: keyword argument \'x\' is repeated\", help: \"Pass each keyword argument once, after every positional argument\", line: 1, column: 6 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a missing comma between numbers",
            text: "1 2",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: a comma is missing between arguments\", help: \"Separate arguments, and the items of lists, tuples and dicts, with commas, for example @cents(\'amount\', 2)\", line: 1, column: 3 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a missing comma between list items",
            text: "[1 'a']",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: a comma is missing between arguments\", help: \"Separate arguments, and the items of lists, tuples and dicts, with commas, for example @cents(\'amount\', 2)\", line: 1, column: 4 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a missing comma between nested calls",
            text: "@inner(1) @inner(2)",
            nested: &[(0, 9), (10, 19)],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: a comma is missing between arguments\", help: \"Separate arguments, and the items of lists, tuples and dicts, with commas, for example @cents(\'amount\', 2)\", line: 1, column: 11 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a doubled comma",
            text: "'amount',,",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: a value is missing here\", help: \"Macro arguments are Python literals (strings, numbers, True, False, None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() references; compute anything else inside the macro\", line: 1, column: 10 })",
        },
        ParseMacroArgumentsTestCase {
            description: "an unclosed string",
            text: "'abc",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: a string is not closed\", help: \"Macro arguments are Python literals (strings, numbers, True, False, None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() references; compute anything else inside the macro\", line: 1, column: 1 })",
        },
        ParseMacroArgumentsTestCase {
            description: "an unclosed bracket on a later line",
            text: "[1,\n 2",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: a bracket is not closed with \']\'\", help: \"Macro arguments are Python literals (strings, numbers, True, False, None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() references; compute anything else inside the macro\", line: 1, column: 1 })",
        },
        ParseMacroArgumentsTestCase {
            description: "an error on a later line",
            text: "1,\n  x",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"must use only Python literals, nested macro calls, and __ref(), __source(), or __seed() references\", help: \"Macro arguments are Python literals (strings, numbers, True, False, None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() references; compute anything else inside the macro\", line: 2, column: 3 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a surrogate pair escape suggests the code point escape",
            text: "'\\ud83d\\ude00'",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"contain the lone surrogate escape \'\\\\ud83d\'\", help: \"Python strings hold code points, not UTF-16 surrogate pairs; write the character as one escape: \\\\U0001F600 instead of the surrogate pair, or write the character itself\", line: 1, column: 2 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a named sequence is not one character",
            text: "'\\N{LATIN CAPITAL LETTER A WITH MACRON AND GRAVE}'",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: \\\\N{LATIN CAPITAL LETTER A WITH MACRON AND GRAVE} names a sequence of 2 characters, and \\\\N escapes name one character\", help: \"Write each character of the sequence with its own \\\\N{...} escape, or write the characters themselves\", line: 1, column: 2 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a lone surrogate escape",
            text: "'\\ud800'",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"contain the lone surrogate escape \'\\\\ud800\'\", help: \"Lone surrogates are not valid Unicode text and cannot be sent to a warehouse; write the character itself or the escape of a valid code point\", line: 1, column: 2 })",
        },
        ParseMacroArgumentsTestCase {
            description: "leading zeros in a decimal integer",
            text: "007",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: leading zeros in a decimal integer are not allowed; use 0o for octal\", help: \"Macro arguments are Python literals (strings, numbers, True, False, None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() references; compute anything else inside the macro\", line: 1, column: 1 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a character Python rejects in a name",
            text: "1, é€",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: the character \'\u{20ac}\' (U+20AC) is not valid in a name\", help: \"Macro arguments are Python literals (strings, numbers, True, False, None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() references; compute anything else inside the macro\", line: 1, column: 4 })",
        },
        ParseMacroArgumentsTestCase {
            description: "a keyword used as an argument name",
            text: "True=1",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: \'True\' is a Python keyword, not an argument name\", help: \"Macro arguments are Python literals (strings, numbers, True, False, None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() references; compute anything else inside the macro\", line: 1, column: 1 })",
        },
        ParseMacroArgumentsTestCase {
            description: "an unknown character name",
            text: "'\\N{NOPE}'",
            nested: &[],
            expected_plan: "Err(ArgumentError { detail: \"could not be parsed: \\\\N{NOPE} names no Unicode character\", help: \"Macro arguments are Python literals (strings, numbers, True, False, None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() references; compute anything else inside the macro\", line: 1, column: 2 })",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            spelled_arguments(test_case.text, test_case.nested),
            test_case.expected_plan,
            "{}",
            test_case.description
        );
    }
}
