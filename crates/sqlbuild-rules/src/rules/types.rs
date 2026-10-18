use crate::query_facts::models::QueryFacts;
use std::sync::{Arc, OnceLock};

/// One stubbed query shape's parsed facts, computed once by whichever worker reaches it first.
pub(crate) type ShapeFacts = Arc<OnceLock<Result<QueryFacts, String>>>;
