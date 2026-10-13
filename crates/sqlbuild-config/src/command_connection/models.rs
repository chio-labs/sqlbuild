//! A target's authored command-group warehouse.

/// One target's authored, unexpanded warehouse for a command group and the file setting it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AuthoredWarehouse {
    pub warehouse: String,
    pub target_name: String,
    /// The `WarehouseGroup` value, `build` or `query`.
    pub group: String,
    pub file_name: String,
}

impl AuthoredWarehouse {
    /// `<file> [targets.<target>.warehouses] <group>`.
    #[must_use]
    pub fn source(&self) -> String {
        format!(
            "{} [targets.{}.warehouses] {}",
            self.file_name, self.target_name, self.group
        )
    }

    /// The template label of the authored value.
    #[must_use]
    pub fn context_label(&self) -> String {
        format!("targets.{}.warehouses.{}", self.target_name, self.group)
    }
}
