use crate::cli_text::models::{CliStyle, PreBuildWorkText};
use crate::plan_display::models::{ModelLabelFacts, ParsedBound, TimestampGrainFacts};

pub(super) struct LabelTestCase {
    pub(super) description: &'static str,
    pub(super) entry: ModelLabelFacts,
    pub(super) expected_label: &'static str,
    pub(super) expected_resource_type: &'static str,
    pub(super) expected_annotation: &'static str,
}

pub(super) struct BoundTestCase {
    pub(super) description: &'static str,
    pub(super) value: &'static str,
    pub(super) typing: (Option<&'static str>, Option<&'static str>),
    pub(super) parsed: Option<ParsedBound>,
    pub(super) expected_text: &'static str,
}

pub(super) struct NamesTestCase {
    pub(super) description: &'static str,
    pub(super) names: Vec<String>,
    pub(super) expected_no_rows: &'static str,
    pub(super) expected_waiting: &'static str,
}

pub(super) struct BatchSizeTestCase {
    pub(super) description: &'static str,
    pub(super) batch_size: &'static str,
    pub(super) grain: &'static str,
    pub(super) expected_size: Result<&'static str, &'static str>,
}

pub(super) struct TimestampGrainTestCase {
    pub(super) description: &'static str,
    pub(super) facts: TimestampGrainFacts,
    pub(super) expected_grain: Result<Option<&'static str>, &'static str>,
}

pub(super) struct PreBuildWorkTestCase {
    pub(super) description: &'static str,
    pub(super) work: PreBuildWorkText,
    pub(super) expected_lines: Vec<&'static str>,
}

pub(super) struct QueryDiffTestCase {
    pub(super) description: &'static str,
    pub(super) style: CliStyle,
    pub(super) expected_lines: Vec<&'static str>,
}
