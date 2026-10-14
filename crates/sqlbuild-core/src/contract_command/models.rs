//! Contract comparison results as the command reports them.

/// One difference between a declared and a physical contract.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ContractFindingText {
    pub kind: String,
    pub column: Option<String>,
    pub declared_type: Option<String>,
    pub physical_type: Option<String>,
    pub message: String,
}

/// One compared model or source.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ContractResourceText {
    pub resource_type: String,
    pub resource_name: String,
    /// The dotted relation of its non-empty database, schema and name.
    pub relation: String,
    pub findings: Vec<ContractFindingText>,
}

/// The whole comparison, with any repository files written.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ContractReport {
    pub from_target: String,
    pub resources: Vec<ContractResourceText>,
    pub written_paths: Vec<String>,
}

impl ContractReport {
    /// How many differences all resources hold.
    #[must_use]
    pub fn difference_count(&self) -> usize {
        self.resources
            .iter()
            .map(|resource| resource.findings.len())
            .sum()
    }
}

/// One contract lifecycle event and what its status line reports.
#[derive(Clone, Debug, PartialEq)]
pub enum ContractProgress {
    InspectionStart {
        count: usize,
        target: String,
    },
    InspectionComplete {
        count: usize,
        target: String,
        seconds: f64,
    },
    InspectionFailed {
        seconds: f64,
    },
    WriteComplete {
        count: usize,
        seconds: f64,
    },
    WriteFailed {
        seconds: f64,
    },
}
