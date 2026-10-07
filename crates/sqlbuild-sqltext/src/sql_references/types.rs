//! Shapes shared by the reference scan.

/// A call prefix such as `__ref(`, its Python reference kind and the name its errors use.
pub(crate) type ReferencePrefix = (&'static [u8], &'static str, &'static str);
