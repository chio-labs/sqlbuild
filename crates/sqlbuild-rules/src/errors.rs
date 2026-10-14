/// Why a natively built rules request produced no evaluation.
#[derive(Debug)]
pub enum RowsError {
    Rules(String),
    Io(std::io::Error),
}

/// Why generated skills were not installed, with rollback notes for the raised error.
#[derive(Debug)]
pub struct SkillInstallError {
    pub kind: SkillInstallErrorKind,
    pub message: String,
    pub notes: Vec<String>,
}

/// Whether a skill installation failure is a policy refusal or a filesystem error.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SkillInstallErrorKind {
    Refused,
    Io,
}
