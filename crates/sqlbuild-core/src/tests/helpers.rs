use crate::models::{
    DeclarationIdentity, DeclarationKind, Diagnostic, DiagnosticOrderKey, DiagnosticPhase,
    DiagnosticSeverity, ResourceIdentity, ResourceKind, SqlLogicalType, SqlValue, SqlValueKind,
};

pub(super) fn declaration(kind: DeclarationKind, name: &str) -> DeclarationIdentity {
    DeclarationIdentity {
        kind,
        name: name.to_owned(),
        owner: None,
    }
}

pub(super) fn private_constant(owner: &str, name: &str) -> DeclarationIdentity {
    DeclarationIdentity {
        owner: Some(ResourceIdentity {
            kind: ResourceKind::Model,
            name: owner.to_owned(),
        }),
        ..declaration(DeclarationKind::Constant, name)
    }
}

pub(super) fn diagnostic(code: &str, severity: DiagnosticSeverity, order: [u32; 3]) -> Diagnostic {
    Diagnostic {
        phase: DiagnosticPhase::Compile,
        severity,
        code: code.to_owned(),
        message: format!("{code} message"),
        resource_type: None,
        resource_name: None,
        column_name: None,
        location: None,
        related_locations: vec![],
        help: None,
        notes: vec![],
        affected_rules: vec![],
        order_key: DiagnosticOrderKey {
            resource_order: order[0],
            stage: order[1],
            sequence: order[2],
        },
    }
}

pub(super) fn scalar_type(kind: SqlValueKind) -> SqlLogicalType {
    SqlLogicalType {
        kind,
        element_type: None,
    }
}

pub(super) fn list_of_integer_sets() -> SqlValue {
    SqlValue::List {
        element_type: SqlLogicalType {
            kind: SqlValueKind::Set,
            element_type: Some(Box::new(scalar_type(SqlValueKind::Integer))),
        },
        values: vec![SqlValue::Set {
            element_type: scalar_type(SqlValueKind::Integer),
            values: vec![SqlValue::Integer(1), SqlValue::Integer(2)],
        }],
    }
}
