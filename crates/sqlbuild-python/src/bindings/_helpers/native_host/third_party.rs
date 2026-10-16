//! Glue around Python-only third-party integrations: dbt, dlt, ingestr, Dagster and rivers.

use crate::bindings::_helpers::native_host::models::{HostEdge, HostEntry, HostId, HostKind};

/// One third-party entry of `sqlbuild._native_host`, indexing `ENTRIES`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ThirdPartyHost {
    AssetSelectionCommands,
    CheckMetadataExcludedKeys,
    CloneCommand,
    CompletedExecutionStatuses,
    DagsterAssetEnabledField,
    DagsterAssetNodeKinds,
    DagsterCheckEnabledField,
    DagsterCheckNameField,
    DagsterDirectKindNodeKinds,
    DefaultSelectableNodeKinds,
    ExplicitSelectionFlags,
    InsufficientCheckStatus,
    LiveEventCommands,
    LoaderNodeKind,
    LoadSelectableNodeKinds,
    MaterializableNodeKinds,
    ModelNodeKind,
    ScenarioCheckKind,
    SourceNodeKind,
    StandaloneCheckCommands,
    SuccessExecutionStatus,
    ViewMaterializationType,
    WarningCheckSeverity,
    DagsterDagInputError,
    LoadDbtYaml,
    RenderSelectedDbtProfileOutput,
    DbtProfileError,
    DltIntegrationKind,
    DltIntegrationError,
    DltLoaderFunction,
    DltResourceConfig,
    DltSourceConfig,
    IngestrIntegrationKind,
    IngestrIntegrationError,
    IngestrLoaderFunction,
    IngestrSourceConfig,
    RiversAssetNodeKinds,
}

/// Every third-party entry, in `ThirdPartyHost` order.
pub(crate) const ENTRIES: &[HostEntry] = &[
    HostEntry {
        name: "ASSET_SELECTION_COMMANDS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "CHECK_METADATA_EXCLUDED_KEYS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "CLONE_COMMAND",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "COMPLETED_EXECUTION_STATUSES",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "DAGSTER_ASSET_ENABLED_FIELD",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "DAGSTER_ASSET_NODE_KINDS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "DAGSTER_CHECK_ENABLED_FIELD",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "DAGSTER_CHECK_NAME_FIELD",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "DAGSTER_DIRECT_KIND_NODE_KINDS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "DEFAULT_SELECTABLE_NODE_KINDS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "EXPLICIT_SELECTION_FLAGS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "INSUFFICIENT_CHECK_STATUS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "LIVE_EVENT_COMMANDS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "LOADER_NODE_KIND",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "LOAD_SELECTABLE_NODE_KINDS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "MATERIALIZABLE_NODE_KINDS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "MODEL_NODE_KIND",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "SCENARIO_CHECK_KIND",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "SOURCE_NODE_KIND",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "STANDALONE_CHECK_COMMANDS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "SUCCESS_EXECUTION_STATUS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "VIEW_MATERIALIZATION_TYPE",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "WARNING_CHECK_SEVERITY",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "DagsterDagInputError",
        kind: HostKind::Exception,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "load_dbt_yaml",
        kind: HostKind::Function,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "render_selected_dbt_profile_output",
        kind: HostKind::Function,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "DbtProfileError",
        kind: HostKind::Exception,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "DLT_INTEGRATION_KIND",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "DltIntegrationError",
        kind: HostKind::Exception,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "dlt_loader_function",
        kind: HostKind::Function,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "DltResourceConfig",
        kind: HostKind::Class,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "DltSourceConfig",
        kind: HostKind::Class,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "INGESTR_INTEGRATION_KIND",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "IngestrIntegrationError",
        kind: HostKind::Exception,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "ingestr_loader_function",
        kind: HostKind::Function,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "IngestrSourceConfig",
        kind: HostKind::Class,
        edge: HostEdge::ThirdParty,
    },
    HostEntry {
        name: "RIVERS_ASSET_NODE_KINDS",
        kind: HostKind::Value,
        edge: HostEdge::ThirdParty,
    },
];

impl ThirdPartyHost {
    /// The entry's position in `HOST_ENTRIES`, usable in constant tables.
    pub(crate) const fn id(self) -> HostId {
        HostId {
            edge: HostEdge::ThirdParty,
            index: self as usize,
        }
    }
}

impl From<ThirdPartyHost> for HostId {
    fn from(entry: ThirdPartyHost) -> Self {
        entry.id()
    }
}
