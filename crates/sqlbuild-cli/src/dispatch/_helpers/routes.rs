//! Builders the route table is written with.

use crate::dispatch::models::{CallShape, ClassRef, Field, Route, Source};

const DBT_IMPLEMENTATION: &str = "run_dbt_command";

pub(crate) const fn class(name: &'static str) -> ClassRef {
    ClassRef { name }
}

pub(crate) const fn field(name: &'static str, source: Source) -> Field {
    Field { name, source }
}

pub(crate) const fn attr(name: &'static str, attribute: &'static str) -> Field {
    field(name, Source::Attr(attribute))
}

pub(crate) const fn same(name: &'static str) -> Field {
    attr(name, name)
}

pub(crate) const fn request(class_ref: ClassRef, fields: &'static [Field]) -> Field {
    field("request", Source::Nested(class_ref, fields))
}

pub(crate) const fn routed(
    slot: &'static str,
    implementation: &'static str,
    arguments: &'static [Field],
    shape: CallShape,
) -> Route {
    Route {
        slot,
        implementation,
        arguments,
        shape,
        implementation_extra: None,
        unavailable_code: None,
    }
}

/// A dbt interop route: the shared implementation, called with its dbt command.
pub(crate) const fn dbt_route(
    slot: &'static str,
    command: &'static str,
    arguments: &'static [Field],
    command_class: ClassRef,
) -> Route {
    Route {
        implementation_extra: Some(field("command", Source::Constant(command_class, command))),
        ..routed(
            slot,
            DBT_IMPLEMENTATION,
            arguments,
            CallShape {
                slot_positional: 3,
                implementation_keywords: true,
            },
        )
    }
}
