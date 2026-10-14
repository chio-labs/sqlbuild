//! A named output and its expression proof.

use crate::planner_migrations::_helpers::proofs::ast::{canonical, identifier, references};
use crate::planner_migrations::_helpers::proofs::encoding::encode;
use crate::planner_migrations::models::QueryProjection;
use serde_json::Value;
use std::collections::BTreeSet;

pub(crate) fn named_projections(select: &Value) -> Result<Option<Vec<QueryProjection>>, String> {
    let Some(expressions) = select["expressions"].as_array() else {
        return Ok(None);
    };
    let mut projections: Vec<QueryProjection> = Vec::new();
    let mut keys: BTreeSet<String> = BTreeSet::new();
    for expression in expressions {
        let Some(projection) = projection(expression)? else {
            return Ok(None);
        };
        if !keys.insert(projection.name.to_lowercase()) {
            return Ok(None);
        }
        projections.push(projection);
    }
    Ok(Some(projections))
}

pub(crate) fn projection(expression: &Value) -> Result<Option<QueryProjection>, String> {
    let Some(object) = expression.as_object().filter(|object| object.len() == 1) else {
        return Ok(None);
    };
    let (name, body) = if let Some(alias) = object.get("alias") {
        (identifier(&alias["alias"]), &alias["this"])
    } else if let Some(column) = object.get("column") {
        (identifier(&column["name"]), expression)
    } else {
        return Ok(None);
    };
    let Some(name) = name.filter(|_| !body.is_null()) else {
        return Ok(None);
    };
    let mut canonical_body = body.clone();
    canonical(&mut canonical_body);
    let column = &body["column"];
    Ok(Some(QueryProjection {
        name: name.to_owned(),
        expression: encode(&canonical_body)?,
        references: references(body, false),
        passthrough: column.is_object()
            && column["table"].is_null()
            && identifier(&column["name"])
                .is_some_and(|reference| reference.to_lowercase() == name.to_lowercase()),
    }))
}
