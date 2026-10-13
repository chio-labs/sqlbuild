use crate::cli_text::models::{CliStyle, CompileTextReport, DiagnosticText};

pub(super) struct DiagnosticsTextTestCase {
    pub(super) description: &'static str,
    pub(super) diagnostics: Vec<DiagnosticText>,
    pub(super) style: CliStyle,
    pub(super) expected_text: &'static str,
}

pub(super) struct NoticeTestCase {
    pub(super) description: &'static str,
    pub(super) reasons: Vec<(String, Vec<String>)>,
    pub(super) expected_notice: Option<&'static str>,
}

pub(super) struct CompileTextTestCase {
    pub(super) description: &'static str,
    pub(super) report: CompileTextReport,
    pub(super) expected_text: &'static str,
}
