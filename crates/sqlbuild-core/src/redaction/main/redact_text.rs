//! `redact_text`: obvious named secrets and URI passwords removed from diagnostic text.

use crate::redaction::_helpers::patterns::{
    AUTHORIZATION, BEARER, SECRET_VALUE, URI_CREDENTIAL, substituted,
};
use crate::redaction::constants::{BEARER_REPLACEMENT, PAIR_REPLACEMENT, URI_REPLACEMENT};

/// Authorization headers, bearer tokens, `name=value` secrets, then URI passwords redacted.
#[must_use]
pub fn redact_text(value: &str) -> String {
    let authorization: String = substituted(&AUTHORIZATION, value, PAIR_REPLACEMENT);
    let bearer: String = substituted(&BEARER, &authorization, BEARER_REPLACEMENT);
    let named: String = substituted(&SECRET_VALUE, &bearer, PAIR_REPLACEMENT);
    substituted(&URI_CREDENTIAL, &named, URI_REPLACEMENT)
}
