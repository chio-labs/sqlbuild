use crate::janitor_text::models::{ArchiveCandidateText, ArchivedRelationText, JanitorPlanText};

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
