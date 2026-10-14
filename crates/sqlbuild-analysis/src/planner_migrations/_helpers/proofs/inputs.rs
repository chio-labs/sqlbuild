//! Resolve only inputs whose columns can be proved from the query shape.

use crate::planner_migrations::_helpers::proofs::ast::{
    clause_items, identifier, identifiers, items,
};
use crate::planner_migrations::_helpers::proofs::projection::projection;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

type Columns = BTreeSet<String>;
type Input = (Option<(String, String)>, Option<Columns>);
type Inputs = (Option<Vec<(String, String)>>, Columns);

pub(crate) fn select_inputs(select: &Value) -> Result<Inputs, String> {
    if items(&select["lateral_views"]).iter().any(Value::is_object) {
        return Ok((None, Columns::new()));
    }
    let mut ctes: BTreeMap<String, Option<Columns>> = BTreeMap::new();
    for cte in items(&select["with"]["ctes"])
        .iter()
        .filter(|item| item.is_object())
    {
        if let Some(name) = identifier(&cte["alias"]) {
            let declared = identifiers(&cte["columns"]);
            ctes.insert(
                name.to_owned(),
                if declared.is_empty() {
                    output_names(&cte["this"])?
                } else {
                    Some(declared.into_iter().collect())
                },
            );
        }
    }
    let mut relations: Vec<(String, String)> = Vec::new();
    let mut local = Columns::new();
    for item in clause_items(&select["from"]).iter().chain(
        items(&select["joins"])
            .iter()
            .filter(|join| join.is_object())
            .map(|join| &join["this"]),
    ) {
        match input_item(item, &ctes)? {
            (Some(relation), _) => relations.push(relation),
            (_, Some(columns)) => local.extend(columns),
            _ => return Ok((None, Columns::new())),
        }
    }
    Ok((Some(relations), local))
}

fn input_item(item: &Value, ctes: &BTreeMap<String, Option<Columns>>) -> Result<Input, String> {
    let Some(object) = item.as_object().filter(|object| object.len() == 1) else {
        return Ok((None, None));
    };
    if let Some(alias) = object.get("alias") {
        if !alias.is_object() {
            return Ok((None, None));
        }
        let renamed = identifiers(&alias["column_aliases"]);
        let inner = input_item(&alias["this"], ctes)?;
        return Ok(
            if !renamed.is_empty() && (inner.0.is_some() || inner.1.is_some()) {
                (None, Some(renamed.into_iter().collect()))
            } else {
                inner
            },
        );
    }
    if let Some(function) = object.get("function").filter(|value| value.is_object()) {
        let kind = function["name"].as_str().unwrap_or_default().to_lowercase();
        let args = items(&function["args"]);
        if !["__source", "__ref"].contains(&kind.as_str()) || args.len() != 1 {
            return Ok((None, None));
        }
        return Ok((
            identifier(&args[0]["column"]["name"]).map(|name| (kind, name.to_owned())),
            None,
        ));
    }
    if let Some(table) = object.get("table").filter(|value| value.is_object()) {
        if !table["schema"].is_null() || !table["catalog"].is_null() {
            return Ok((None, None));
        }
        return Ok((
            None,
            identifier(&table["name"])
                .and_then(|name| ctes.get(name))
                .cloned()
                .flatten(),
        ));
    }
    if let Some(subquery) = object.get("subquery").filter(|value| value.is_object()) {
        return Ok((None, output_names(&subquery["this"])?));
    }
    Ok((None, None))
}

fn output_names(query: &Value) -> Result<Option<Columns>, String> {
    if !query
        .as_object()
        .is_some_and(|object| object.len() == 1 && object.contains_key("select"))
    {
        return Ok(None);
    }
    let Some(expressions) = query["select"]["expressions"].as_array() else {
        return Ok(None);
    };
    let mut names = Columns::new();
    for expression in expressions {
        let Some(projection) = projection(expression)? else {
            return Ok(None);
        };
        names.insert(projection.name.to_lowercase());
    }
    Ok(Some(names))
}
