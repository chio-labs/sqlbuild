pub(super) struct SeedPairingTestCase {
    pub(super) description: &'static str,
    pub(super) declarations: &'static [&'static str],
    pub(super) stems: &'static [&'static str],
    pub(super) expected_pairs: Result<Vec<usize>, usize>,
}
