//! A format run's outcome as its text and JSON reports show it.

/// One lint violation with the authored source line it points at.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct LintFinding {
    /// `str(file_path)`.
    pub file: String,
    /// The file relative to the project root as a POSIX path, or the whole POSIX path outside it.
    pub display_path: String,
    pub line: i64,
    pub column: i64,
    pub end_line: Option<i64>,
    pub end_column: Option<i64>,
    pub code: String,
    pub message: String,
    /// Fault severity; every other violation is a warning.
    pub fault: bool,
    pub engine: String,
    pub remediation: Option<String>,
    /// The authored text of `line`, when the run holds the file and the line exists.
    pub source_line: Option<String>,
}

/// One applied, refused or unavailable Rule fix.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct RuleFixLine {
    pub file: String,
    pub code: String,
    pub line: i64,
    pub status: String,
    pub reason: String,
}

/// Everything a format run reports.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct LintReport {
    pub files_checked: usize,
    pub formatted_files: Vec<String>,
    pub rule_fixes: Vec<RuleFixLine>,
    pub findings: Vec<LintFinding>,
}

impl LintReport {
    /// How many violations are faults.
    #[must_use]
    pub fn fault_count(&self) -> usize {
        self.findings.iter().filter(|finding| finding.fault).count()
    }

    /// How many violations are warnings.
    #[must_use]
    pub fn warning_count(&self) -> usize {
        self.findings.len() - self.fault_count()
    }
}
