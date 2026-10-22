use crate::sql_macros::constants::{DECLARATION_GROUP, INHERITED_ROLES, LOCAL_ROLES};
use crate::sql_macros::models::Placement;

fn placement(path: &str) -> Placement {
    let parts: Vec<&str> = path.split('/').collect();
    for (index, part) in parts.iter().enumerate() {
        let inherited: bool = INHERITED_ROLES.contains(part);
        if !inherited && !LOCAL_ROLES.contains(part) {
            continue;
        }
        if index == 0 {
            return Placement::Project;
        }
        let mut owner: &[&str] = &parts[..index];
        if owner.last() == Some(&DECLARATION_GROUP) {
            owner = &owner[..owner.len() - 1];
        }
        let owner: String = owner.join("/");
        return if inherited {
            Placement::Inherited(owner)
        } else {
            Placement::Local(owner)
        };
    }
    Placement::Project
}

/// Whether the declaration at `declaration_path` is visible from the macro file at `macro_path`.
pub fn declaration_visible_from_macro(declaration_path: &str, macro_path: &str) -> bool {
    let owner: Option<String> = match placement(macro_path) {
        Placement::Project => None,
        Placement::Inherited(owner) | Placement::Local(owner) => Some(owner),
    };
    match (placement(declaration_path), owner) {
        (Placement::Project, _) => true,
        (_, None) => false,
        (Placement::Inherited(declared), Some(owner)) => {
            owner == declared || owner.starts_with(&format!("{declared}/"))
        }
        (Placement::Local(declared), Some(owner)) => owner == declared,
    }
}
