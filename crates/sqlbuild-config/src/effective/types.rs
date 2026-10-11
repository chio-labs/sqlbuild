//! Ordered configuration mapping aliases.

/// `str`-keyed entries in insertion order, read and written with Python `dict` semantics.
pub type Entries<K, V> = Vec<(K, V)>;
