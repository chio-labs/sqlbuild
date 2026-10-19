use std::collections::BTreeMap;

use sqlbuild_rules::models::{EvaluateRequest, RetainedRows};

use crate::bindings::_helpers::compile_delta::context::{
    CapturedDiagnostic, CapturedModel, CapturedTest,
};
use crate::bindings::_helpers::compile_delta::image::{
    BaseRules, IMAGE_FORMAT, ImageGate, ImageRelations, ImageRules, PendingRules, ProjectImage,
};
use crate::bindings::_helpers::compile_delta::tests::test_types::DamagedImageTestCase;

fn pairs(values: &[(&str, &str)]) -> Vec<(String, String)> {
    values
        .iter()
        .map(|(left, right)| ((*left).to_owned(), (*right).to_owned()))
        .collect()
}

fn strings(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// An image holding at least one value of every kind it stores.
fn image() -> ProjectImage {
    let order_types: Vec<(String, String)> = pairs(&[("order_id", "BIGINT"), ("amount", "DOUBLE")]);
    let customer_types: Vec<(String, String)> = pairs(&[("customer_id", "BIGINT")]);
    let request: Vec<u8> = serde_json::to_vec(&EvaluateRequest::default()).expect("request");
    ProjectImage {
        format: String::new(),
        json_output: true,
        models: vec![
            CapturedModel {
                name: "orders".to_owned(),
                relative_path: "models/orders.sql".to_owned(),
                upstream: pairs(&[("source", "raw_orders"), ("model", "customers")]),
            },
            CapturedModel {
                name: "customers".to_owned(),
                relative_path: "models/customers.sql".to_owned(),
                upstream: Vec::new(),
            },
        ],
        usages: BTreeMap::from([("models/orders.sql".to_owned(), "digest-1".to_owned())]),
        tests: vec![CapturedTest {
            key: "orders_test".to_owned(),
            relative_path: "tests/unit/orders.sql".to_owned(),
            chain: strings(&["orders", "customers"]),
        }],
        relations: ImageRelations {
            types: vec![
                ("orders".to_owned(), order_types.clone()),
                ("customers".to_owned(), customer_types.clone()),
            ],
            nullability: vec![("orders".to_owned(), pairs(&[("order_id", "never")]))],
            complete: vec![("orders".to_owned(), order_types.clone())],
            schemas: vec![("customers".to_owned(), pairs(&[("customer_id", "INTEGER")]))],
            dependency_ordered: true,
            cyclic: false,
            legacy_models: strings(&["customers"]),
        },
        fact_digests: vec![(strings(&["model", "orders"]), "fact-digest".to_owned())],
        model_subjects: Some(vec![
            (
                "models/orders.sql".to_owned(),
                "orders".to_owned(),
                Some("table".to_owned()),
            ),
            (
                "models/customers.sql".to_owned(),
                "customers".to_owned(),
                None,
            ),
        ]),
        diagnostics: vec![CapturedDiagnostic {
            json: "{\"code\": \"W1\"}".to_owned(),
            resource_name: Some("orders".to_owned()),
            paths: strings(&["models/orders.sql"]),
            error: false,
        }],
        text_models: Some(vec![("orders".to_owned(), true, 3)]),
        environment_names: strings(&["SQLBUILD_TARGET"]),
        pinned_sources: strings(&["raw_customers"]),
        test_sources: BTreeMap::from([(
            "tests/unit/orders.sql".to_owned(),
            strings(&["raw_orders"]),
        )]),
        model_shapes: vec![
            ("orders".to_owned(), order_types),
            ("customers".to_owned(), pairs(&[("customer_id", "VARCHAR")])),
        ],
        lint_model_keys: Some(pairs(&[("models/orders.sql", "lint-key")])),
        lint_file_keys: Some(vec![
            ("models/orders.sql".to_owned(), Some("file-key".to_owned())),
            ("models/customers.sql".to_owned(), None),
        ]),
        header_keys: BTreeMap::from([(
            "models/orders.sql".to_owned(),
            pairs(&[("description", "0123")]),
        )]),
        rules: Some(ImageRules::Retained(RetainedRows {
            request_json: request,
            digests: Vec::new(),
        })),
    }
}

/// Every stored fact of `image` but its rules, in a comparable form.
fn facts(image: &ProjectImage) -> String {
    format!(
        "{:?}",
        (
            (
                &image.json_output,
                &image.models,
                &image.usages,
                &image.tests,
                &image.relations,
                &image.fact_digests,
                &image.model_subjects,
            ),
            (
                &image.diagnostics,
                &image.text_models,
                &image.environment_names,
                &image.pinned_sources,
                &image.test_sources,
                &image.model_shapes,
                &image.lint_model_keys,
                &image.lint_file_keys,
                &image.header_keys,
            ),
        )
    )
}

fn current_format() -> String {
    IMAGE_FORMAT.to_owned()
}

fn encoded() -> Vec<(String, Vec<u8>)> {
    let mut stored: ProjectImage = image();
    stored.format = current_format();
    stored.encode().expect("encoded")
}

#[test]
fn given_project_image_when_encoded_and_decoded_then_every_fact_and_the_rules_survive() {
    let mut sections = encoded();
    let gate: ImageGate = ImageGate::decode(&sections).expect("gate");
    assert!(gate.json_output);
    assert!(!gate.has_errors);
    assert!(gate.has_model_subjects);
    let decoded: ProjectImage = ProjectImage::decode(&mut sections, gate).expect("image");
    let mut expected: ProjectImage = image();
    expected.format = current_format();
    assert_eq!(decoded.format, expected.format);
    assert_eq!(facts(&decoded), facts(&expected));
    let Some(ImageRules::Decoding(rules)) = decoded.rules else {
        panic!("the rules request was not decoding");
    };
    let rules: BaseRules = PendingRules::resolved(rules).expect("rules");
    assert!(rules.request.models.is_empty());
    assert!(rules.digests.is_empty());
}

#[test]
fn given_damaged_image_when_decoded_then_it_is_never_read() {
    let test_cases = [
        DamagedImageTestCase {
            description: "intact",
            damage: |_| {},
            expected_gate: true,
            expected_image: true,
        },
        DamagedImageTestCase {
            description: "truncated facts",
            damage: |sections| {
                let facts = sections
                    .iter_mut()
                    .find(|(name, _)| name == "facts")
                    .expect("facts");
                facts.1.truncate(facts.1.len() / 2);
            },
            expected_gate: true,
            expected_image: false,
        },
        DamagedImageTestCase {
            description: "rules request without its digests",
            damage: |sections| sections.retain(|(name, _)| name != "rule-digests"),
            expected_gate: true,
            expected_image: false,
        },
        DamagedImageTestCase {
            description: "gate of another format",
            damage: |sections| {
                let other: ProjectImage = ProjectImage {
                    format: "sqlbuild-project-image-v0".to_owned(),
                    ..ProjectImage::default()
                };
                let gate = other
                    .encode()
                    .expect("encoded")
                    .into_iter()
                    .find(|(name, _)| name == "gate")
                    .expect("gate");
                for section in sections.iter_mut() {
                    if section.0 == "gate" {
                        section.1 = gate.1.clone();
                    }
                }
            },
            expected_gate: false,
            expected_image: false,
        },
    ];
    for test_case in test_cases {
        let mut sections = encoded();
        (test_case.damage)(&mut sections);
        let gate: Option<ImageGate> = ImageGate::decode(&sections);
        assert_eq!(
            gate.is_some(),
            test_case.expected_gate,
            "{}",
            test_case.description
        );
        let decoded: Option<ProjectImage> =
            gate.and_then(|gate| ProjectImage::decode(&mut sections, gate));
        assert_eq!(
            decoded.is_some(),
            test_case.expected_image,
            "{}",
            test_case.description
        );
    }
}
