//! What source, function and audit records answer without the host.

use crate::models::{
    AttachedAudit, AttachedFunction, AttachedSource, AuditRecord, FunctionRecord, SourceRecord,
};
use crate::types::{ObjectKeyRow, ProjectHost, SourceNamespace};

const TABLE_FUNCTION_TYPE: &str = "table_fn";
const SCALAR_FUNCTION_TYPE: &str = "udf";

impl<H: ProjectHost> SourceRecord<H> {
    /// The attached source.
    #[inline]
    pub fn attached(&self) -> &AttachedSource<H> {
        &self.attached
    }

    /// Keep the namespace native project assembly resolved for the source.
    pub fn set_namespace(&mut self, namespace: SourceNamespace) {
        self.namespace = Some(namespace);
    }
}

impl<H: ProjectHost> AttachedFunction<H> {
    /// `function_node_type`: a table function when it declares return columns.
    #[inline]
    pub fn node_type(&self) -> &'static str {
        if self.return_columns.is_empty() {
            SCALAR_FUNCTION_TYPE
        } else {
            TABLE_FUNCTION_TYPE
        }
    }
}

impl<H: ProjectHost> FunctionRecord<H> {
    /// Keep the dependency keys native project assembly resolved for the function.
    pub fn set_deps(&mut self, deps: Vec<ObjectKeyRow>) {
        self.deps = Some(deps);
    }
}

impl<H: ProjectHost> AttachedAudit<H> {
    /// `_resolve_audit_name`: the instance name, else the definition name.
    #[inline]
    pub fn compiled_name(&self) -> &str {
        self.name.as_deref().unwrap_or(&self.definition_name)
    }
}

impl<H: ProjectHost> AuditRecord<H> {
    /// Keep the scope dependency keys native project assembly resolved for the audit.
    pub fn set_scope_deps(&mut self, deps: Vec<ObjectKeyRow>) {
        self.scope_deps = Some(deps);
    }
}
