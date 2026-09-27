//! Lexically scoped AST renaming before model CTEs are lifted into a shared WITH.

use std::cell::RefCell;
use std::collections::{HashMap, HashSet};

use polyglot_sql::expressions::{Identifier, Null};
use polyglot_sql::traversal::transform_map;
use polyglot_sql::{DialectType, Expression};

const CTE_NAME_PREFIX: &str = "__sqb_cte_";

/// Allocate bounded, collision-free ordinal names within one rendered query.
#[derive(Default)]
pub(crate) struct CteNamespace {
    occupied: HashSet<String>,
    next: usize,
}

impl CteNamespace {
    /// Reserve generated-prefix names from all steps; no other token can collide.
    pub(crate) fn reserve(&mut self, sql: &str) {
        self.occupied.extend(
            sql.split(|c: char| !c.is_alphanumeric() && c != '_')
                .filter(|token| {
                    token
                        .as_bytes()
                        .get(..CTE_NAME_PREFIX.len())
                        .is_some_and(|head| head.eq_ignore_ascii_case(CTE_NAME_PREFIX.as_bytes()))
                })
                .map(str::to_ascii_lowercase),
        );
    }

    fn allocate(&mut self) -> String {
        loop {
            let name = format!("{CTE_NAME_PREFIX}{:x}", self.next);
            self.next += 1;
            if self.occupied.insert(name.clone()) {
                return name;
            }
        }
    }

    pub(crate) fn rewrite(
        &mut self,
        expression: Expression,
        dialect: DialectType,
    ) -> polyglot_sql::Result<Expression> {
        let allocator = RefCell::new(self);
        transform_map(expression, &|mut expression| {
            let Expression::Select(select) = &mut expression else {
                return Ok(expression);
            };
            let Some(mut with) = select.with.take() else {
                return Ok(expression);
            };
            let mut names: HashMap<String, String> = HashMap::new();
            for cte in &mut with.ctes {
                let original = identifier_key(&cte.alias, dialect);
                let replacement = allocator.borrow_mut().allocate();
                if with.recursive {
                    names.insert(original.clone(), replacement.clone());
                }
                let body = std::mem::replace(&mut cte.this, Expression::Null(Null));
                cte.this = rewrite_relations(body, &names, dialect)?;
                names.insert(original, replacement.clone());
                cte.alias = Identifier::new(replacement);
            }
            expression = rewrite_relations(expression, &names, dialect)?;
            if let Expression::Select(select) = &mut expression {
                select.with = Some(with);
            }
            Ok(expression)
        })
    }
}

fn rewrite_relations(
    expression: Expression,
    names: &HashMap<String, String>,
    dialect: DialectType,
) -> polyglot_sql::Result<Expression> {
    transform_map(expression, &|mut expression| {
        if let Expression::Table(table) = &mut expression
            && table.schema.is_none()
            && table.catalog.is_none()
            && let Some(name) = names.get(&identifier_key(&table.name, dialect))
        {
            if table.alias.is_none() {
                table.alias = Some(table.name.clone());
            }
            table.name = Identifier::new(name);
        }
        Ok(expression)
    })
}

fn identifier_key(identifier: &Identifier, dialect: DialectType) -> String {
    match dialect {
        DialectType::Snowflake if !identifier.quoted => identifier.name.to_uppercase(),
        DialectType::Snowflake | DialectType::PostgreSQL if identifier.quoted => {
            identifier.name.clone()
        }
        _ => identifier.name.to_lowercase(),
    }
}
