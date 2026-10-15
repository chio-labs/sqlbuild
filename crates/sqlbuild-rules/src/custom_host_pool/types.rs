//! Host plans and invocations.

use std::collections::BTreeMap;

/// Subjects to evaluate per rule code; `None` evaluates every subject.
pub type HostPlan = BTreeMap<String, Option<Vec<String>>>;
/// One `(rule code, subject)` evaluation.
pub type HostInvocation = (String, String);
/// One recorded fact read.
pub type FactKey = Vec<String>;
