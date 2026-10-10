//! Add model `migrate_from` to a staged rename whenever its relation moves.

use crate::refactoring::_helpers::chars::chars;
use crate::refactoring::_helpers::header_edits::insert_header_entry_edit;
use crate::refactoring::_helpers::model_planning::decide_model_migration;
use crate::refactoring::_helpers::workspace::Originals;
use crate::refactoring::constants::MIGRATE_FROM_KEY;
use crate::refactoring::models::{ManualLocation, MigrationDeclaration, ModelFacts, RefactorPlan};

/// The plan with `migrate_from <old>` on the model whenever its relation moves.
pub fn with_model_migration(
    plan: &RefactorPlan,
    before: &[ModelFacts],
    after: Option<&[ModelFacts]>,
    originals: &Originals,
) -> RefactorPlan {
    let old = plan.request.model_name.as_str();
    let new = plan.request.new_name.as_str();
    let decision = decide_model_migration(before, after, (old, new));
    let destination = plan.request.destination.clone();
    let mut migrated = plan.clone();
    if decision.blocked {
        migrated.blocking.push(ManualLocation {
            path: destination.unwrap_or_default(),
            line: None,
            column: None,
            reason: decision.reason,
        });
        return migrated;
    }
    let Some(index) = plan
        .changes
        .iter()
        .position(|change| Some(&change.path) == destination.as_ref())
    else {
        return migrated;
    };
    if !decision.needed {
        return migrated;
    }
    let declaration = format!("{MIGRATE_FROM_KEY} {old}");
    let change = &plan.changes[index];
    let contents = originals
        .iter()
        .find(|(path, _)| *path == change.original_path)
        .map(|(_, text)| text.as_str())
        .unwrap_or_default();
    match insert_header_entry_edit(contents, &chars(contents), &declaration, &declaration) {
        None => migrated.blocking.push(ManualLocation {
            path: change.path.clone(),
            line: Some(1),
            column: Some(1),
            reason: format!("add {declaration} to the MODEL header to keep history"),
        }),
        Some(edit) => {
            migrated.changes[index].edits.push(edit);
            migrated.migrations.push(MigrationDeclaration {
                model_name: new.to_owned(),
                declaration,
                reason: decision.reason,
            });
        }
    }
    migrated
}
