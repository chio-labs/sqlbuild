use crate::macro_arguments::main::parse_macro_arguments::parse_macro_arguments;
use crate::macro_arguments::tests::test_types::TestHost;

/// The parse result of `text` spelled with `{:?}`.
pub(crate) fn spelled_arguments(text: &str, nested: &[(usize, usize)]) -> String {
    format!("{:?}", parse_macro_arguments(&TestHost, text, nested))
}
