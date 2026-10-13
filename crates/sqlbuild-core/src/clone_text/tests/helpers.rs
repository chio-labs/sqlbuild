use crate::clone_text::models::{CloneItemText, CloneStatusKind};

/// An item with an action and status and no relations or message.
pub(super) fn item(name: &str, action: &str, status: CloneStatusKind) -> CloneItemText {
    CloneItemText {
        name: name.to_owned(),
        action: action.to_owned(),
        status,
        message: None,
        origin_relation: None,
        destination_relation: None,
        duration_seconds: None,
    }
}

/// An item with a message.
pub(super) fn with_message(item: CloneItemText, message: &str) -> CloneItemText {
    CloneItemText {
        message: Some(message.to_owned()),
        ..item
    }
}

/// Twelve pending model identities.
pub(super) fn pending_identities() -> Vec<String> {
    (0..12)
        .map(|index| format!("model:orders_{index}"))
        .collect()
}
