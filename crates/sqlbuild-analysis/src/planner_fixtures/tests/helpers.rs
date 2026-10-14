use crate::planner_fixtures::models::FixtureColumn;

pub(super) fn column(name: &str, sql_type: &str, nullable: bool) -> FixtureColumn {
    FixtureColumn {
        name: name.into(),
        folded_name: name.into(),
        sql_type: Some(sql_type.into()),
        nullable: Some(nullable),
    }
}
