//! Shapes shared by the reference scan.

/// A call prefix such as `__ref(` and its Python reference kind.
pub(crate) type ReferencePrefix = (&'static [u8], &'static str);
