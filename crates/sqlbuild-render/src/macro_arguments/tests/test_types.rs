pub(crate) struct ParseMacroArgumentsTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) nested: &'static [(usize, usize)],
    /// The spelled plan, or `error: <detail> @line:column`.
    pub(crate) expected: &'static str,
}
