use std::collections::BTreeSet;

/// Column sets that are unique for one relation, by lower-cased output column name.
pub(crate) type Keys = Vec<Vec<String>>;
/// A unique column set over a select's joined input, as `(source alias, column)` pairs.
pub(crate) type InputKey = BTreeSet<(String, String)>;
