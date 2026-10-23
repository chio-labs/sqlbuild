use crate::janitor_text::models::{
    ArchiveCandidateText, ArchivedRelationText, JanitorItemText, JanitorPhase, JanitorPlanText,
    OldNameViewText, RelationUsageText, UsageCheckText,
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

/// Reads by `readers` of `count` queries, last on 2026-10-21.
fn usage(readers: &[&str], query_count: i64) -> RelationUsageText {
    RelationUsageText {
        last_read_at: "2026-10-21 09:30:00".to_owned(),
        readers: readers.iter().map(|reader| (*reader).to_owned()).collect(),
        query_count,
    }
}

/// Three candidates checked over `7d`: an in-use view, an in-use table read by five users,
/// and an unread table; `keep_in_use` moves the in-use two to `kept_in_use`.
pub(super) fn usage_plan(keep_in_use: bool) -> JanitorPlanText {
    let view: ArchiveCandidateText = ArchiveCandidateText {
        name: "dev.orders_daily".to_owned(),
        archive_name: "dev._sqb_archive__20261022t101500z__orders_daily".to_owned(),
        usage: Some(usage(&["svc_reporting"], 14)),
        ..ArchiveCandidateText::default()
    };
    let table: ArchiveCandidateText = ArchiveCandidateText {
        name: "dev.old_orders".to_owned(),
        archive_name: "dev._sqb_archive__20261022t101500z__old_orders".to_owned(),
        is_table: true,
        changed_on: Some("2026-09-01".to_owned()),
        usage: Some(usage(
            &["svc_reporting", "alice", "bob", "carol", "dave"],
            40,
        )),
        ..ArchiveCandidateText::default()
    };
    let unread: ArchiveCandidateText = ArchiveCandidateText {
        name: "dev.old_customers".to_owned(),
        archive_name: "dev._sqb_archive__20261022t101500z__old_customers".to_owned(),
        is_table: true,
        ..ArchiveCandidateText::default()
    };
    let (archive_candidates, kept_in_use) = if keep_in_use {
        (vec![unread], vec![view, table])
    } else {
        (vec![view, table, unread], Vec::new())
    };
    JanitorPlanText {
        target_name: Some("dev".to_owned()),
        retention_days: 14,
        direct_mode: true,
        archive_retention_days: 14,
        archive_candidates,
        kept_in_use,
        usage_check: Some(UsageCheckText {
            checked: true,
            reason: None,
            window: "7d".to_owned(),
            keep_in_use,
        }),
        ..JanitorPlanText::default()
    }
}

/// A plan whose usage could not be checked, for `reason`.
pub(super) fn unchecked_plan(keep_in_use: bool) -> JanitorPlanText {
    JanitorPlanText {
        usage_check: Some(UsageCheckText {
            checked: false,
            reason: Some("unsupported adapter".to_owned()),
            window: "7d".to_owned(),
            keep_in_use,
        }),
        ..direct_archive_plan()
    }
}
