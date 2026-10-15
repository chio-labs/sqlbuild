//! `old_name_histories`: one history per recorded move whose old name needs a compatibility view.

use std::collections::HashMap;

use crate::events::models::{EventOrder, OldNameFactKey, OldNameHistoryIndexes, OldNameStep};

/// Histories in move order, keeping the earliest fact of each step; moves without a requirement are skipped.
#[must_use]
pub fn old_name_histories(
    moves: &[EventOrder],
    facts: &[OldNameFactKey],
) -> Vec<OldNameHistoryIndexes> {
    let mut fact_order: Vec<usize> = (0..facts.len()).collect();
    fact_order.sort_by(|left, right| facts[*left].order.cmp(&facts[*right].order));
    let mut by_move: HashMap<(&str, OldNameStep), usize> = HashMap::new();
    for index in fact_order {
        let fact: &OldNameFactKey = &facts[index];
        by_move
            .entry((fact.migration_event_id.as_str(), fact.step))
            .or_insert(index);
    }
    let mut move_order: Vec<usize> = (0..moves.len()).collect();
    move_order.sort_by(|left, right| moves[*left].cmp(&moves[*right]));
    move_order
        .into_iter()
        .filter_map(|moved| {
            let step = |step: OldNameStep| {
                by_move
                    .get(&(moves[moved].event_id.as_str(), step))
                    .copied()
            };
            Some(OldNameHistoryIndexes {
                moved,
                required: step(OldNameStep::Required)?,
                archived: step(OldNameStep::OriginArchived),
                created: step(OldNameStep::ViewCreated),
                dropped: step(OldNameStep::ViewDropped),
            })
        })
        .collect()
}
