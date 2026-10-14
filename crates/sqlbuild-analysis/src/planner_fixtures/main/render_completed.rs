//! Adapter-independent completion SQL with identifier callbacks.

use crate::planner_fixtures::models::FixtureSqlInput;

/// Render completion SQL while preserving identifier callback order.
pub fn render_completed<E>(
    input: FixtureSqlInput<'_>,
    mut render: impl FnMut(&str, bool) -> Result<String, E>,
) -> Result<String, E> {
    let alias = render("__sqlbuild_partial_fixture", false)?;
    let mut projections: Vec<String> = Vec::new();
    if input.typed_nulls {
        for column in input.supplied {
            let name = if column.quoted {
                render(&column.name, true)?
            } else {
                column.name.clone()
            };
            let source = format!("{alias}.{name}");
            projections.push(match &column.expected_type {
                Some(sql_type) => format!("CAST({source} AS {sql_type}) AS {name}"),
                None => source,
            });
        }
    } else {
        projections.push(format!("{alias}.*"));
    }
    for column in input.completed {
        let name = render(&column.name, false)?;
        projections.push(format!(
            "CAST(NULL AS {}) AS {name}",
            column.sql_type.as_deref().unwrap_or("None")
        ));
    }
    Ok(format!(
        "SELECT\n  {}\nFROM (\n{}\n) AS {alias}",
        projections.join(",\n  "),
        input.sql
    ))
}
