//! Python's `promotion_conflict_diagnostics`: K011 for enforced contracts under immediate promotion.

use crate::contracts::_helpers::promotion::promotion_conflicts as conflicts;
use crate::contracts::models::{PromotionConflict, PromotionRequest};

/// One conflict per enforced-contract table model, in model order.
#[must_use]
pub fn promotion_conflicts(request: &PromotionRequest) -> Vec<PromotionConflict> {
    conflicts(request)
}
