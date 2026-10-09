//! The generated `str.isalnum()` and `str.isalpha()` tables, one per supported Unicode version.

/// `(unicodedata.unidata_version, ranges)` for every table native text helpers can select.
pub(crate) const ALNUM_TABLES: [(&str, &[(u32, u32)]); 3] = [
    ("15.0.0", include!("../alnum_ranges/unicode_15_0_0.in")),
    ("15.1.0", include!("../alnum_ranges/unicode_15_1_0.in")),
    ("16.0.0", include!("../alnum_ranges/unicode_16_0_0.in")),
];

/// `(unicodedata.unidata_version, ranges)` of `str.isalpha()`, in the order of `ALNUM_TABLES`.
pub(crate) const ALPHA_TABLES: [(&str, &[(u32, u32)]); 3] = [
    ("15.0.0", include!("../alpha_ranges/unicode_15_0_0.in")),
    ("15.1.0", include!("../alpha_ranges/unicode_15_1_0.in")),
    ("16.0.0", include!("../alpha_ranges/unicode_16_0_0.in")),
];
