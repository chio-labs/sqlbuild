//! `validate_filter`: reject contradictory or malformed `EventFilter` and `RunFilter` fields.

use crate::execution_history::_helpers::filters::{
    bounds_ordered, filled_text, filter_error, utc_bound,
};
use crate::execution_history::errors::HistoryError;
use crate::execution_history::models::{EventFilterSpec, FilterSpec, RunFilterSpec};

/// Text fields non-blank, `event_types` exclusive with `family`, UTC ordered bounds.
fn validate_event_filter(event_filter: &EventFilterSpec) -> Result<(), HistoryError> {
    filled_text(event_filter.invocation_id.as_deref(), "invocation_id")?;
    filled_text(event_filter.run_id.as_deref(), "run_id")?;
    filled_text(event_filter.producer.as_deref(), "producer")?;
    if !event_filter.event_types.is_empty() && event_filter.family.is_some() {
        return Err(filter_error(
            "event_types and family are mutually exclusive",
        ));
    }
    for event_type in &event_filter.event_types {
        filled_text(Some(event_type), "event_types")
            .map_err(|_| filter_error("event_types must contain only non-empty values"))?;
    }
    utc_bound(event_filter.occurred_at_start.as_ref(), "occurred_at_start")?;
    utc_bound(event_filter.occurred_at_end.as_ref(), "occurred_at_end")?;
    bounds_ordered(
        (
            event_filter.occurred_at_start.as_ref(),
            event_filter.occurred_at_end.as_ref(),
        ),
        "occurred_at_start must not be after occurred_at_end",
    )
}

/// A non-blank `invocation_id` and UTC ordered creation bounds.
fn validate_run_filter(run_filter: &RunFilterSpec) -> Result<(), HistoryError> {
    filled_text(run_filter.invocation_id.as_deref(), "invocation_id")?;
    utc_bound(run_filter.created_at_start.as_ref(), "created_at_start")?;
    utc_bound(run_filter.created_at_end.as_ref(), "created_at_end")?;
    bounds_ordered(
        (
            run_filter.created_at_start.as_ref(),
            run_filter.created_at_end.as_ref(),
        ),
        "created_at_start must not be after created_at_end",
    )
}

/// Reject the first invalid field of an event or run filter, in Python's check order.
pub fn validate_filter(filter: FilterSpec<'_>) -> Result<(), HistoryError> {
    match filter {
        FilterSpec::Event(event_filter) => validate_event_filter(event_filter),
        FilterSpec::Run(run_filter) => validate_run_filter(run_filter),
    }
}
