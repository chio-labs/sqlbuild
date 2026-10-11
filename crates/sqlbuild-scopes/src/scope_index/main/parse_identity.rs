//! Python's `parse_identity`: a `kind:name` or `kind:owner_kind:owner.name` identity.

use crate::scope_index::constants::{IDENTITY_SEPARATOR, OWNER_SEPARATOR};
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationKind, IdentityFailure, QualifiedIdentity, ResourceIdentity,
    ResourceKind,
};

/// The identity `value` names, or why Python rejects it.
pub fn parse_identity(value: &str) -> Result<QualifiedIdentity, IdentityFailure> {
    let parts: Vec<&str> = value.split(IDENTITY_SEPARATOR).collect();
    match parts.as_slice() {
        [raw_kind, name] => {
            if name.is_empty() {
                return Err(IdentityFailure::NoName);
            }
            if let Some(kind) = ResourceKind::parse(raw_kind) {
                return Ok(QualifiedIdentity::Resource(ResourceIdentity {
                    kind,
                    name: (*name).to_owned(),
                }));
            }
            DeclarationKind::parse(raw_kind)
                .map(|kind| {
                    QualifiedIdentity::Declaration(DeclarationIdentity {
                        kind,
                        name: (*name).to_owned(),
                        owner: None,
                    })
                })
                .ok_or_else(|| IdentityFailure::UnknownKind((*raw_kind).to_owned()))
        }
        [raw_kind, raw_owner_kind, owner_and_name] => {
            let (Some(kind), Some(owner_kind)) = (
                DeclarationKind::parse(raw_kind),
                ResourceKind::parse(raw_owner_kind),
            ) else {
                return Err(IdentityFailure::InvalidPrivate);
            };
            match owner_and_name.rsplit_once(OWNER_SEPARATOR) {
                Some((owner_name, name)) if !owner_name.is_empty() && !name.is_empty() => {
                    Ok(QualifiedIdentity::Declaration(DeclarationIdentity {
                        kind,
                        name: name.to_owned(),
                        owner: Some(ResourceIdentity {
                            kind: owner_kind,
                            name: owner_name.to_owned(),
                        }),
                    }))
                }
                _ => Err(IdentityFailure::InvalidPrivate),
            }
        }
        _ => Err(IdentityFailure::Unqualified),
    }
}
