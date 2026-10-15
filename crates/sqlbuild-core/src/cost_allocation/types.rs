//! Grouping keys of run-cost allocation.

use crate::cost_allocation::models::WarehouseKey;

/// Resource type, resource name and warehouse of one priced resource.
pub(crate) type ResourceKey = (String, String, WarehouseKey);
