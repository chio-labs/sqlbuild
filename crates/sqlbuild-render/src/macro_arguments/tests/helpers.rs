use crate::macro_arguments::main::parse_macro_arguments::parse_macro_arguments;
use crate::macro_arguments::models::ArgumentValue;
use crate::macro_arguments::types::ArgumentHost;

/// A host knowing one character name and NFKC-folding the `ﬁ` ligature, rejecting `€`.
struct TestHost;

impl ArgumentHost for TestHost {
    fn character_named(&self, name: &str) -> Option<char> {
        (name == "LATIN SMALL LETTER E WITH ACUTE").then_some('é')
    }

    fn identifier(&self, text: &str) -> Option<String> {
        (!text.contains('€')).then(|| text.replace('ﬁ', "fi"))
    }
}

/// Spell the plan as `positional | keywords | references`, or the error and its location.
pub(crate) fn spelled_arguments(text: &str, nested: &[(usize, usize)]) -> String {
    match parse_macro_arguments(&TestHost, text, nested) {
        Ok(arguments) => format!(
            "{} | {} | {}",
            spelled_list(&arguments.positional),
            arguments
                .keywords
                .iter()
                .map(|(name, value)| format!("{name}={}", spelled(value)))
                .collect::<Vec<_>>()
                .join(", "),
            arguments
                .typed_references
                .iter()
                .map(|(function, name)| format!("{function}:{name}"))
                .collect::<Vec<_>>()
                .join(", "),
        ),
        Err(error) => format!("error: {} @{}:{}", error.detail, error.line, error.column),
    }
}

fn spelled_list(values: &[ArgumentValue]) -> String {
    values.iter().map(spelled).collect::<Vec<_>>().join(", ")
}

fn spelled(value: &ArgumentValue) -> String {
    match value {
        ArgumentValue::Str(text) => format!("{text:?}"),
        ArgumentValue::Int { radix: 10, digits } => digits.clone(),
        ArgumentValue::Int { radix, digits } => format!("{digits}/{radix}"),
        ArgumentValue::Float(text) => format!("f{text}"),
        ArgumentValue::Bool(flag) => if *flag { "True" } else { "False" }.to_owned(),
        ArgumentValue::None => "None".to_owned(),
        ArgumentValue::NestedCall(call) => format!("@{call}"),
        ArgumentValue::TypedReference { function, name } => format!("{function}({name})"),
        ArgumentValue::List(items) => format!("[{}]", spelled_list(items)),
        ArgumentValue::Tuple(items) => format!("({})", spelled_list(items)),
        ArgumentValue::Dict(pairs) => format!(
            "{{{}}}",
            pairs
                .iter()
                .map(|(key, value)| format!("{}: {}", spelled(key), spelled(value)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        ArgumentValue::Negative(inner) => format!("-{}", spelled(inner)),
        ArgumentValue::Positive(inner) => format!("+{}", spelled(inner)),
    }
}
