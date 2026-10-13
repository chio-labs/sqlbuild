use crate::graph::models::ProjectGraph;
use crate::manifest::errors::{ManifestEncodeError, ManifestError};
use crate::manifest::main::build_manifest_json::build_manifest_json;
use crate::manifest::models::ManifestPlanInput;
use crate::manifest::tests::helpers::{authored, config, meta, model, project, sql_hook, sql_test};
use crate::manifest::tests::test_types::{BuildManifestJsonTestCase, ManifestFailureTestCase};
use crate::python_values::models::{PythonKey, PythonValue};

#[test]
fn given_project_when_building_manifest_json_then_python_payload_agrees() {
    let hooked = || {
        let mut hooked = config();
        hooked.post_hooks = Some(vec![sql_hook()]);
        hooked
    };
    let test_cases = [
        BuildManifestJsonTestCase {
            description: "an empty project keeps metadata first and ends with a newline",
            input: project(Vec::new()),
            expected_fragments: vec![
                "{\n  \"metadata\": {\n    \"dbt_schema_version\": \"https://schemas.getdbt.com/dbt/manifest/v12.json\",\n    \"dbt_version\": \"1.12.0\",\n    \"generated_at\": \"2026-10-12T00:00:00+00:00\",\n    \"invocation_id\": \"run\",",
                "  \"unit_tests\": {}\n}\n",
            ],
        },
        BuildManifestJsonTestCase {
            description: "an authored sqlbuild scalar is kept beside lifecycle hooks",
            input: project(vec![model(
                meta(vec![authored(
                    "sqlbuild",
                    PythonValue::String("team".to_owned()),
                )]),
                hooked(),
            )]),
            expected_fragments: vec![
                "\"sqlbuild\": {\n          \"authored_value\": \"team\",\n          \"lifecycle_hooks\": {\n            \"post_hooks\": [",
                "\"type\": \"sql\",\n                \"statement\": \"select 1\",\n                \"name\": \"audit_orders\",\n                \"description\": \"\"\n",
                "\"post-hook\": [\n          {\n            \"sql\": \"select 1\",\n            \"transaction\": true,\n            \"index\": 0\n",
                "\"fqn\": [\n        \"shop\",\n        \"models\",\n        \"orders\"\n      ]",
                "\"created_at\": 0.0,",
            ],
        },
        BuildManifestJsonTestCase {
            description: "non-str keys of an authored sqlbuild dict are dropped",
            input: project(vec![model(
                meta(vec![authored(
                    "sqlbuild",
                    PythonValue::Object(vec![
                        (
                            PythonKey {
                                text: Ok("1".to_owned()),
                                is_str: false,
                            },
                            PythonValue::Null,
                        ),
                        authored("owner", PythonValue::String("ops".to_owned())),
                    ]),
                )]),
                hooked(),
            )]),
            expected_fragments: vec![
                "\"sqlbuild\": {\n          \"owner\": \"ops\",\n          \"lifecycle_hooks\"",
            ],
        },
    ];
    for test_case in test_cases {
        let json: String = build_manifest_json(&test_case.input, &ProjectGraph::default())
            .expect("manifest builds")
            .expect("manifest encodes");
        assert!(
            test_case
                .expected_fragments
                .iter()
                .all(|fragment| json.contains(fragment)),
            "{}: missing a fragment of\n{json}",
            test_case.description
        );
    }
}

#[test]
fn given_invalid_values_when_building_manifest_json_then_python_error_agrees() {
    let unencodable =
        PythonValue::Unencodable("Object of type set is not JSON serializable".to_owned());
    let test_cases = [
        ManifestFailureTestCase {
            description: "an unencodable meta value fails on encoding",
            input: project(vec![model(
                meta(vec![authored("owners", unencodable.clone())]),
                config(),
            )]),
            expected_error: Ok(Some(ManifestEncodeError::Unencodable(
                "Object of type set is not JSON serializable".to_owned(),
            ))),
        },
        ManifestFailureTestCase {
            description: "the first unencodable value in output order is reported",
            input: {
                let mut early = config();
                early.alias = PythonValue::Unencodable(
                    "Object of type frozenset is not JSON serializable".to_owned(),
                );
                project(vec![model(meta(vec![authored("owners", unencodable)]), early)])
            },
            expected_error: Ok(Some(ManifestEncodeError::Unencodable(
                "Object of type frozenset is not JSON serializable".to_owned(),
            ))),
        },
        ManifestFailureTestCase {
            description: "a bound parameter missing from the schema fails while building",
            input: {
                let mut input = project(Vec::new());
                input.plan = Some(ManifestPlanInput {
                    sql_tests: vec![sql_test("other")],
                    ..ManifestPlanInput::default()
                });
                input
            },
            expected_error: Err(ManifestError::MissingParameterType("other".to_owned())),
        },
        ManifestFailureTestCase {
            description: "a query that cannot be fingerprinted fails while building",
            input: {
                let mut broken = model(None, config());
                broken.query_sql = "SELECT 'unterminated".to_owned();
                project(vec![broken])
            },
            expected_error: Err(ManifestError::QueryFingerprint(
                "SQL tokenization failed: Tokenization error at line 1, column 21: Unterminated string".to_owned(),
            )),
        },
    ];
    for test_case in test_cases {
        let actual: Result<Option<ManifestEncodeError>, ManifestError> =
            build_manifest_json(&test_case.input, &ProjectGraph::default()).map(Result::err);
        assert_eq!(
            actual, test_case.expected_error,
            "{}",
            test_case.description
        );
    }
}
