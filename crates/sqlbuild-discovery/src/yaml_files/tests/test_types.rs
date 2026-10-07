use crate::yaml_files::models::YamlFileOutcome;

pub(super) struct YamlFileTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static [u8],
    /// Only the variant is compared.
    pub(super) expected_outcome: YamlFileOutcome,
}
