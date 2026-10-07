use crate::scope_index::tests::helpers::{
    built_index, declaration_locations, diagnostic_texts, index_outcome, index_with_dependencies,
    resource_names, usage_texts,
};
use crate::scope_index::tests::test_types::{DeferralTestCase, IndexFactsTestCase, IndexTestCase};

#[test]
fn given_authored_projects_when_building_then_orders_and_diagnostics_match_python() {
    let test_cases = [
        IndexTestCase {
            description: "builder sorts resources by path, the lookup by identity",
            resources: &[
                ("model", "zeta", "models/a/zeta.sql"),
                ("model", "alpha", "models/b/./alpha.sql"),
                ("test", "alpha", "tests/unit/alpha.sql"),
                ("seed", "lookup", "seeds/lookup.csv"),
            ],
            declarations: &[
                ("macro", "pick", "macros/b.py", 10, "global", None),
                ("macro", "pick_more", "macros/a.py", 9, "global", None),
                ("constant", "limit", "constants/a.sql", 1, "global", None),
            ],
            expected_resource_order: &["model:zeta", "model:alpha", "seed:lookup", "test:alpha"],
            expected_canonical_resources: &[
                "model:alpha",
                "model:zeta",
                "seed:lookup",
                "test:alpha",
            ],
            expected_declaration_order: &["constants/a.sql:1", "macros/b.py:10", "macros/a.py:9"],
            expected_canonical_declarations: &[
                "constants/a.sql:1",
                "macros/b.py:10",
                "macros/a.py:9",
            ],
            expected_diagnostics: &[],
        },
        IndexTestCase {
            description: "duplicates and naming problems keep Python's messages and order",
            resources: &[
                ("model", "orders", "models/b/orders.sql"),
                ("model", "orders", "models/a/orders.sql"),
            ],
            declarations: &[
                (
                    "constant",
                    "rate",
                    "models/a/_constants/x.sql",
                    1,
                    "local",
                    Some("models/a"),
                ),
                ("constant", "rate", "constants/rates.sql", 1, "global", None),
                ("enum", "__status", "enums/status.sql", 1, "global", None),
                ("enum", "_status", "enums/other.sql", 1, "global", None),
                (
                    "constant",
                    "bad",
                    "models/a/orders.sql",
                    1,
                    "private",
                    Some("models/a"),
                ),
            ],
            expected_resource_order: &["model:orders", "model:orders"],
            expected_canonical_resources: &["model:orders", "model:orders"],
            expected_declaration_order: &[
                "models/a/orders.sql:1",
                "constants/rates.sql:1",
                "models/a/_constants/x.sql:1",
                "enums/status.sql:1",
                "enums/other.sql:1",
            ],
            expected_canonical_declarations: &[
                "models/a/orders.sql:1",
                "constants/rates.sql:1",
                "models/a/_constants/x.sql:1",
                "enums/status.sql:1",
                "enums/other.sql:1",
            ],
            expected_diagnostics: &[
                "S003 Duplicate declaration 'constant:rate' at constants/rates.sql:1:1, \
                 models/a/_constants/x.sql:1:1",
                "S004 Public declaration name '_status' must not start with underscore",
                "S005 Declaration name '__status' uses reserved '__' prefix",
                "S003 Duplicate declaration 'constant:rate' at constants/rates.sql:1:1, \
                 models/a/_constants/x.sql:1:1",
                "S004 Private declaration name 'bad' must have exactly one leading underscore",
                "S018 Duplicate resource 'model:orders' at models/a/orders.sql, models/b/orders.sql",
                "S018 Duplicate resource 'model:orders' at models/a/orders.sql, models/b/orders.sql",
            ],
        },
        IndexTestCase {
            description: "duplicate lines sort as integers in the builder and as text in the lookup",
            resources: &[],
            declarations: &[
                ("macro", "pick", "macros/a.py", 10, "global", None),
                ("macro", "pick", "macros/a.py", 9, "global", None),
            ],
            expected_resource_order: &[],
            expected_canonical_resources: &[],
            expected_declaration_order: &["macros/a.py:9", "macros/a.py:10"],
            expected_canonical_declarations: &["macros/a.py:10", "macros/a.py:9"],
            expected_diagnostics: &[
                "S003 Duplicate declaration 'macro:pick' at macros/a.py:9:1, macros/a.py:10:1",
                "S003 Duplicate declaration 'macro:pick' at macros/a.py:9:1, macros/a.py:10:1",
            ],
        },
    ];

    for test_case in test_cases {
        let index = built_index(test_case.resources, test_case.declarations);

        assert_eq!(
            resource_names(&index, &index.resource_order),
            test_case.expected_resource_order,
            "{}",
            test_case.description
        );
        assert_eq!(
            resource_names(&index, &index.canonical_resources),
            test_case.expected_canonical_resources,
            "{}",
            test_case.description
        );
        assert_eq!(
            declaration_locations(&index, &index.declaration_order),
            test_case.expected_declaration_order,
            "{}",
            test_case.description
        );
        assert_eq!(
            declaration_locations(&index, &index.canonical_declarations),
            test_case.expected_canonical_declarations,
            "{}",
            test_case.description
        );
        assert_eq!(
            diagnostic_texts(&index),
            test_case.expected_diagnostics,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_paths_python_rejects_when_building_then_the_stage_defers() {
    let test_cases = [
        DeferralTestCase {
            description: "absolute resource path",
            resources: &[("model", "a", "/models/a.sql")],
            declarations: &[],
            expected_deferral: true,
        },
        DeferralTestCase {
            description: "drive-qualified resource path",
            resources: &[("model", "a", "C:/models/a.sql")],
            declarations: &[],
            expected_deferral: true,
        },
        DeferralTestCase {
            description: "resource path escaping the project",
            resources: &[("model", "a", "../models/a.sql")],
            declarations: &[],
            expected_deferral: true,
        },
        DeferralTestCase {
            description: "owning path escaping the project",
            resources: &[],
            declarations: &[(
                "macro",
                "pick",
                "models/_macros/a.py",
                1,
                "local",
                Some("models/../.."),
            )],
            expected_deferral: true,
        },
        DeferralTestCase {
            description: "dot segments normalize like Python",
            resources: &[("model", "a", "models/./b/../a.sql")],
            declarations: &[],
            expected_deferral: false,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            index_outcome(test_case.resources, test_case.declarations).is_err(),
            test_case.expected_deferral,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_declarations_when_building_then_relationship_flag_and_usages_match_python() {
    let test_cases = [
        IndexFactsTestCase {
            description: "global declarations never need relationship grants",
            declarations: &[("macro", "pick", "macros/a.py", 1, "global", None)],
            dependencies: &[],
            expected_scoped_relationships: false,
            expected_usages: &[],
        },
        IndexFactsTestCase {
            description: "a scoped macro needs relationship grants",
            declarations: &[(
                "macro",
                "pick",
                "models/a/_macros/a.py",
                1,
                "local",
                Some("models/a"),
            )],
            dependencies: &[],
            expected_scoped_relationships: true,
            expected_usages: &[],
        },
        IndexFactsTestCase {
            description: "repeated dependencies become one usage each, in order",
            declarations: &[
                ("macro", "outer", "macros/a.py", 1, "global", None),
                ("macro", "inner", "macros/a.py", 5, "global", None),
            ],
            dependencies: &["inner", "first", "inner"],
            expected_scoped_relationships: false,
            expected_usages: &["macro:outer -> macro:inner", "macro:outer -> macro:first"],
        },
    ];

    for test_case in test_cases {
        let index = index_with_dependencies(&test_case);

        assert_eq!(
            index.has_scoped_relationship_declarations, test_case.expected_scoped_relationships,
            "{}",
            test_case.description
        );
        assert_eq!(
            usage_texts(&index),
            test_case.expected_usages,
            "{}",
            test_case.description
        );
    }
}
