//! Custom-rule results that contradict the rules that produced them.

/// A host returned a finding outside the rule or subject it evaluated.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CustomFindingError(pub String);
