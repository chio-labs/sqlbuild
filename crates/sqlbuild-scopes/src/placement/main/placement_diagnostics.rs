//! Unused-declaration and exact-placement diagnostics of a usage-complete scope index.

use crate::placement::_helpers::anchors::{
    AnchorSets, UsagesByDeclaration, anchor_sets, usages_by_declaration,
};
use crate::placement::_helpers::declaration_directory::declaration_file_directory;
use crate::placement::_helpers::required::{owner_uses_directly, required_placement};
use crate::placement::_helpers::roles::scope_label;
use crate::placement::models::{
    PlacementCode, PlacementDiagnostic, PlacementIndex, PlacementUsage, RequiredPlacement,
};
use crate::scope_index::main::format_identity::format_identity;
use crate::scope_index::models::{
    DeclarationKind, DeclarationRecord, QualifiedIdentity, ScopeKind,
};

/// Each declaration's diagnostic, in declaration order, as `build_placement_validated_index`.
#[must_use]
pub fn placement_diagnostics(index: &PlacementIndex) -> Vec<PlacementDiagnostic> {
    let usages: UsagesByDeclaration<'_> = usages_by_declaration(index);
    let anchors: AnchorSets = anchor_sets(index, &usages);
    let mut diagnostics: Vec<PlacementDiagnostic> = Vec::new();
    for (position, record) in index.declarations.iter().enumerate() {
        let declaration_usages: &[&PlacementUsage] = usages
            .get(&record.identity)
            .map(Vec::as_slice)
            .unwrap_or_default();
        let used: bool = if record.scope == ScopeKind::Private {
            declaration_usages
                .iter()
                .any(|usage| owner_uses_directly(record, usage))
        } else {
            !declaration_usages.is_empty()
        };
        if !used {
            if record.identity.kind != DeclarationKind::SingularAudit {
                diagnostics.push(PlacementDiagnostic {
                    declaration: position,
                    code: PlacementCode::UnusedDeclaration,
                    message: format!(
                        "Unused {} declaration '{}' at {}; remove it or add a genuine runtime use",
                        record.scope.as_str(),
                        format_identity(&QualifiedIdentity::Declaration(record.identity.clone())),
                        record.path
                    ),
                });
            }
            continue;
        }
        if record.scope == ScopeKind::Private {
            continue;
        }
        let Some(required) = required_placement(record, &usages, &anchors) else {
            continue;
        };
        if record.scope == required.scope && record.owning_path == required.path {
            continue;
        }
        let code: PlacementCode = match (required.scope, record.scope) {
            (ScopeKind::Global, _) => PlacementCode::RequiresGlobalPlacement,
            (_, ScopeKind::Local) => PlacementCode::LocalNeededByDescendant,
            (_, ScopeKind::Global) => PlacementCode::OverBroadGlobal,
            _ => PlacementCode::OverBroadInherited,
        };
        diagnostics.push(PlacementDiagnostic {
            declaration: position,
            code,
            message: placement_message(record, &required),
        });
    }
    diagnostics
}

/// `_message`: where the declaration is, where its consumers require it, and where to move it.
fn placement_message(record: &DeclarationRecord, required: &RequiredPlacement) -> String {
    let current_path: &str = record
        .owning_path
        .as_deref()
        .filter(|path| !path.is_empty())
        .unwrap_or(&record.ownership_root.path);
    let directory: String = declaration_file_directory(
        record.identity.kind,
        required.scope,
        required.path.as_deref(),
        &record.path,
    );
    let target: String = if required.scope == ScopeKind::Global {
        format!("top-level {directory}/")
    } else {
        format!("{directory}/")
    };
    let consumer_label: &str = if record.identity.kind == DeclarationKind::SingularAudit {
        "References"
    } else {
        "Consumers"
    };
    let required_path: &str = required
        .path
        .as_deref()
        .filter(|path| !path.is_empty())
        .unwrap_or("top-level root");
    format!(
        "Declaration '{}' is currently {} at '{current_path}' ({}); required {} at \
         '{required_path}'. {consumer_label}: {}. Move it to '{target}'",
        format_identity(&QualifiedIdentity::Declaration(record.identity.clone())),
        scope_label(record.scope),
        record.path,
        scope_label(required.scope),
        required.consumers.join(", ")
    )
}
