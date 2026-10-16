pub(crate) struct StartupStampsTestCase {
    pub(crate) description: &'static str,
    /// Import-path entries, relative to the temporary root unless absolute-looking.
    pub(crate) directories: Vec<&'static str>,
    /// Stamped paths under the root and whether each exists, in order.
    pub(crate) expected_stamps: Vec<(&'static str, bool)>,
}
