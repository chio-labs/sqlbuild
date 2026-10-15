//! Decode one host's JSON response.

use serde_json::Value;

use crate::custom_host_pool::_helpers::decoding::decoded_slice;
use crate::custom_host_pool::models::HostSlice;

/// The slice a host response describes, or the `RulesError` message of a malformed one.
pub fn decode_host_response(response: &Value) -> Result<HostSlice, String> {
    decoded_slice(response)
}
