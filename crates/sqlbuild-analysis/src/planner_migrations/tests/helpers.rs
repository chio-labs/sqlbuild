//! Synthetic projection facts.

use crate::planner_migrations::models::Projection;

pub(super) fn projection(name: &str) -> Projection {
    Projection {
        name: name.to_owned(),
        key: name.to_lowercase(),
        expression: "amount".to_owned(),
        references: ["amount".to_owned()].into(),
    }
}
