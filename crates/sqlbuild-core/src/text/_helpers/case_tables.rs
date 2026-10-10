//! The generated `str.casefold()` and `str.upper()` mappings, per Unicode version.

/// `(unicodedata.unidata_version, mappings)` of every character `str.casefold()` changes.
pub(crate) const CASEFOLD_TABLES: [(&str, &[(u32, &str)]); 3] = [
    ("15.0.0", include!("../casefold_mappings/unicode_15_0_0.in")),
    ("15.1.0", include!("../casefold_mappings/unicode_15_1_0.in")),
    ("16.0.0", include!("../casefold_mappings/unicode_16_0_0.in")),
];

/// `(unicodedata.unidata_version, mappings)` of every character `str.upper()` changes.
pub(crate) const UPPER_TABLES: [(&str, &[(u32, &str)]); 3] = [
    ("15.0.0", include!("../upper_mappings/unicode_15_0_0.in")),
    ("15.1.0", include!("../upper_mappings/unicode_15_1_0.in")),
    ("16.0.0", include!("../upper_mappings/unicode_16_0_0.in")),
];

/// One string with each character replaced by its `mappings` entry, if it has one.
pub(crate) fn mapped(mappings: &[(u32, &str)], text: &str) -> String {
    let mut result: String = String::with_capacity(text.len());
    for character in text.chars() {
        let code_point: u32 = u32::from(character);
        match mappings.binary_search_by_key(&code_point, |(key, _)| *key) {
            Ok(index) => result.push_str(mappings[index].1),
            Err(_) => result.push(character),
        }
    }
    result
}
