//! The errors argument parsing reports, each with its help.

const LITERALS_HELP: &str = "Macro arguments are Python literals (strings, numbers, True, False, \
    None, lists, tuples and dicts), nested macro calls, and __ref(), __source() or __seed() \
    references; compute anything else inside the macro";
const BYTES_HELP: &str =
    "Pass text as a string without the b prefix, for example 'orders' instead of b'orders'";
const COMPLEX_HELP: &str =
    "Pass int or float numbers; give a complex value's real and imaginary parts as two arguments";
const ELLIPSIS_HELP: &str = "Pass None, or a string the macro understands, instead of '...'";
const FORMATTED_HELP: &str = "Pass the parts as separate arguments and format them in the macro";
const REFERENCE_HELP: &str = "Write one quoted resource name, for example __ref(\"orders\")";
const UNPACKING_HELP: &str = "Write each argument or key out explicitly";
const KEYWORD_HELP: &str = "Pass each keyword argument once, after every positional argument";
const SURROGATE_HELP: &str = "Lone surrogates are not valid Unicode text and cannot be sent to a \
    warehouse; write the character itself or the escape of a valid code point";

/// One argument error at a code point position of the argument text.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Failure {
    pub(crate) detail: String,
    pub(crate) help: &'static str,
    pub(crate) position: usize,
}

fn failure(detail: &str, help: &'static str, position: usize) -> Failure {
    Failure {
        detail: detail.to_owned(),
        help,
        position,
    }
}

/// Text Python cannot tokenize or parse.
pub(crate) fn syntax(detail: &str, position: usize) -> Failure {
    failure(
        &format!("could not be parsed: {detail}"),
        LITERALS_HELP,
        position,
    )
}

/// Valid Python that is not a supported argument value.
pub(crate) fn unsupported(position: usize) -> Failure {
    failure(
        "must use only Python literals, nested macro calls, and __ref(), __source(), or __seed() \
         references",
        LITERALS_HELP,
        position,
    )
}

pub(crate) fn bytes_literal(position: usize) -> Failure {
    failure("use a bytes literal", BYTES_HELP, position)
}

pub(crate) fn complex_literal(position: usize) -> Failure {
    failure("use a complex number literal", COMPLEX_HELP, position)
}

pub(crate) fn ellipsis(position: usize) -> Failure {
    failure("use '...' (Ellipsis)", ELLIPSIS_HELP, position)
}

pub(crate) fn formatted_string(position: usize) -> Failure {
    failure("use an f-string", FORMATTED_HELP, position)
}

pub(crate) fn typed_reference(function: &str, position: usize) -> Failure {
    failure(
        &format!("must give {function}() exactly one quoted resource name"),
        REFERENCE_HELP,
        position,
    )
}

pub(crate) fn unary(position: usize) -> Failure {
    failure(
        "use unary + or - on a value that is not a number",
        LITERALS_HELP,
        position,
    )
}

pub(crate) fn keyword_expansion(position: usize) -> Failure {
    failure(
        "must not use **kwargs expansion syntax",
        UNPACKING_HELP,
        position,
    )
}

pub(crate) fn dict_unpacking(position: usize) -> Failure {
    failure("must not use dict unpacking", UNPACKING_HELP, position)
}

pub(crate) fn keyword_order(detail: &str, position: usize) -> Failure {
    failure(detail, KEYWORD_HELP, position)
}

pub(crate) fn surrogate(escape: &str, position: usize) -> Failure {
    failure(
        &format!("contain the lone surrogate escape '{escape}'"),
        SURROGATE_HELP,
        position,
    )
}
