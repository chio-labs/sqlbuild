//! Attached audit inputs and the rendering Python's attachment produces from them.

/// One audit argument value as Python holds it; numbers keep Python's own `str()` text.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ArgumentValue {
    Null,
    Boolean(bool),
    Number(String),
    Text(String),
    List(Vec<ArgumentValue>),
    /// A value Python cannot render, such as a mapping; rendering it is Python's error.
    Opaque,
}

/// Where a resolved run scope came from, so Python keeps its own value object.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PolicySource {
    Instance,
    Default,
    Fallback,
}

/// One generic audit attachment: definition SQL, arguments and authored policies.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AuditAttachment {
    /// Python's `str(owner_file)` and the generic audit name, which its error messages quote.
    pub owner_label: String,
    pub definition_name: String,
    pub sql_body: String,
    pub evidence_sql: Option<String>,
    pub implicit_arguments: Vec<(String, ArgumentValue)>,
    pub explicit_arguments: Vec<(String, ArgumentValue)>,
    pub measurement: bool,
    pub has_thresholds: bool,
    pub has_minimum_samples: bool,
    pub threshold_error: bool,
    pub instance_severity: Option<String>,
    pub default_severity: Option<String>,
    pub instance_run_scope: Option<String>,
    pub default_run_scope: Option<String>,
}

/// The rendered SQL and the policies one attachment resolves to; severity is `warn` or `error`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RenderedAudit {
    pub sql_body: String,
    pub evidence_sql: Option<String>,
    /// `(severity, run scope source)`, or the error Python raises once the SQL is expanded.
    pub policies: Result<(&'static str, PolicySource), String>,
}

/// Python's rendering of one attachment: its SQL and policies, or the error rendering raises.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum AuditRendering {
    Rendered(RenderedAudit),
    Failed(String),
}
