use crate::janitor_text::models::{
    ArchiveCandidateText, ArchivedRelationText, JanitorItemText, JanitorPhase, JanitorPlanText,
    OldNameViewText,
};

/// A direct-mode plan for `dev` that archives one relation and deletes one archive.
pub(super) fn direct_archive_plan() -> JanitorPlanText {
    JanitorPlanText {
        target_name: Some("dev".to_owned()),
        retention_days: 14,
        direct_mode: true,
        archive_retention_days: 14,
        archive_candidates: vec![ArchiveCandidateText {
            name: "dev.old_orders".to_owned(),
            ..ArchiveCandidateText::default()
        }],
        archive_deletions: vec![ArchivedRelationText {
            name: "dev.old_products".to_owned(),
            ..ArchivedRelationText::default()
        }],
        ..JanitorPlanText::default()
    }
}

/// A finished action of `phase`, failed when `error` is given.
pub(super) fn item(
    phase: JanitorPhase,
    (action, name, destination): (&str, &str, Option<&str>),
    error: Option<&str>,
) -> JanitorItemText {
    JanitorItemText {
        phase,
        action: action.to_owned(),
        name: name.to_owned(),
        destination: destination.map(str::to_owned),
        error: error.map(str::to_owned),
        duration_seconds: Some(0.5),
    }
}

/// A direct-mode plan archiving `count` relations, with `skipped` objects for two reasons.
pub(super) fn large_plan(count: usize, skipped: usize) -> JanitorPlanText {
    JanitorPlanText {
        target_name: Some("dev".to_owned()),
        retention_days: 14,
        direct_mode: true,
        archive_retention_days: 14,
        archive_candidates: (0..count)
            .map(|index| ArchiveCandidateText {
                name: format!("dev.old_orders_{index:03}"),
                archive_name: format!("dev._sqb_archive__20260924t101500z__old_orders_{index:03}"),
                ..ArchiveCandidateText::default()
            })
            .collect(),
        skipped_relations: (0..skipped)
            .map(|index| {
                let reasons: [&str; 2] =
                    ["relation is newer than 14 days", "not tracked by SQLBuild"];
                let reason: &str = reasons[usize::from(index % 3 != 0)];
                (format!("dev.recent_{index:03}"), reason.to_owned())
            })
            .collect(),
        ..JanitorPlanText::default()
    }
}

/// A plan with `count` live old-name views expiring on one day.
pub(super) fn old_name_plan(count: usize) -> JanitorPlanText {
    JanitorPlanText {
        old_name_live: (0..count)
            .map(|index| OldNameViewText {
                name: format!("dev.orders_v{index:02}"),
                destination_model: format!("orders_{index:02}"),
                expires_on: Some("2026-11-05".to_owned()),
                ..OldNameViewText::default()
            })
            .collect(),
        ..JanitorPlanText::default()
    }
}
