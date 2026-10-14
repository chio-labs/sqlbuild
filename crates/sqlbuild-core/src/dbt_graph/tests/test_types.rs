use crate::dbt_graph::errors::DbtSelectionError;
use crate::dbt_graph::models::DbtSelection;

pub(super) struct GraphTestCase {
    pub(super) description: &'static str,
    pub(super) edges: Vec<(String, Vec<String>)>,
    pub(super) expected_edges: Vec<(&'static str, Vec<&'static str>)>,
}

pub(super) struct SelectionTestCase {
    pub(super) description: &'static str,
    pub(super) select: Vec<&'static str>,
    pub(super) exclude: Vec<&'static str>,
    pub(super) anchors: Vec<(&'static str, Vec<&'static str>)>,
    pub(super) expected_selection: Result<DbtSelection, DbtSelectionError<String>>,
}

pub(super) struct TextTestCase {
    pub(super) description: &'static str,
    pub(super) rendered: Vec<String>,
    pub(super) expected_text: Vec<&'static str>,
}

pub(super) struct NameResolver {
    pub(super) names: Vec<&'static str>,
}
