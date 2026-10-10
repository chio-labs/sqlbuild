use crate::refactoring::errors::{RefactorError, RefactorErrorKind};
use crate::refactoring::models::{FileChange, ModelFacts, RefactorRequest, TextEdit};

/// Plans edits for one file's contents.
pub(super) type PlanEdits = fn(&'static str) -> Result<Vec<TextEdit>, RefactorError>;

pub(super) struct ApplyEditsTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    /// `(start, end, replacement)` in authoring order.
    pub(super) edits: &'static [(usize, usize, &'static str)],
    /// The edited text, or the overlap error message.
    pub(super) expected_text: Result<&'static str, &'static str>,
}

pub(super) struct IdentifierSitesTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) names: &'static [&'static str],
    pub(super) expected_sites: &'static [(usize, usize, &'static str)],
}

pub(super) struct WholeWordTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) word: &'static str,
    pub(super) expected_offsets: &'static [usize],
}

pub(super) struct LineColumnTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) offset: usize,
    pub(super) expected_position: (usize, usize),
}

pub(super) struct FileChangesTestCase {
    pub(super) description: &'static str,
    /// Each path gets one edit, in this order.
    pub(super) edited_paths: &'static [&'static str],
    pub(super) moves: &'static [(&'static str, &'static str)],
    /// `(path, original path, edit count)`.
    pub(super) expected_changes: &'static [(&'static str, &'static str, usize)],
}

pub(super) struct InterpolationSitesTestCase {
    pub(super) description: &'static str,
    pub(super) dialect: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_sites: &'static [&'static str],
}

pub(super) struct ResourceSitesTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    /// `kind name call-text name-text`.
    pub(super) expected_sites: &'static [&'static str],
}

pub(super) struct AnalysisSqlTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_sql: &'static str,
    /// `kind name placeholder,placeholder`.
    pub(super) expected_tables: &'static [&'static str],
}

pub(super) struct EmbeddedRefsTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) name: &'static str,
    pub(super) expected_names: &'static [&'static str],
}

pub(super) struct AuthoredOffsetTestCase {
    pub(super) description: &'static str,
    pub(super) offset: usize,
    pub(super) expected_offset: (usize, bool),
}

pub(super) struct AuthoredSpanTestCase {
    pub(super) description: &'static str,
    pub(super) span: (usize, usize),
    pub(super) expected_span: Option<(usize, usize)>,
}

pub(super) struct HeaderEditsTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    pub(super) plan: PlanEdits,
    pub(super) expected_edits: &'static [&'static str],
    pub(super) expected_contents: &'static str,
}

pub(super) struct InsertEntryTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    pub(super) expected_contents: Option<&'static str>,
}

pub(super) struct YamlEditsTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    pub(super) plan: PlanEdits,
    pub(super) expected_contents: &'static str,
}

pub(super) struct YamlFallbackTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    /// The planned edit count, or the error kind.
    pub(super) expected_outcome: Result<usize, RefactorErrorKind>,
}

pub(super) struct CollisionTestCase {
    pub(super) description: &'static str,
    pub(super) request: RefactorRequest,
    pub(super) expected_reasons: &'static [&'static str],
}

pub(super) struct RefusedTargetTestCase {
    pub(super) description: &'static str,
    pub(super) request: RefactorRequest,
    /// `(code, message)`.
    pub(super) expected_error: (&'static str, &'static str),
}

pub(super) struct MigrationDecisionTestCase {
    pub(super) description: &'static str,
    pub(super) before: Vec<ModelFacts>,
    pub(super) after: Option<Vec<ModelFacts>>,
    /// `(needed, blocked, reason)`.
    pub(super) expected_decision: (bool, bool, &'static str),
}

pub(super) struct CommitTestCase {
    pub(super) description: &'static str,
    /// Files on disk before the commit.
    pub(super) on_disk: &'static [(&'static str, &'static str)],
    /// The texts the plan was made from.
    pub(super) originals: &'static [(&'static str, &'static str)],
    pub(super) changes: Vec<FileChange>,
    /// `(kind, code, message prefix)`.
    pub(super) expected_error: (RefactorErrorKind, &'static str, &'static str),
    /// Every on-disk file after the failed commit.
    pub(super) expected_files: &'static [(&'static str, &'static str)],
}
