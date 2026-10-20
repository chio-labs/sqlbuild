use crate::integration_results::main::encode_integration_value::encode_integration_value;
use crate::integration_results::main::normalize_integration_record::normalize_integration_record;
use crate::integration_results::main::strip_optional_enrichment::strip_optional_enrichment;
use crate::integration_results::tests::helpers::{
    audit_check_record, integer, object, orders_asset, record, text,
};
use crate::integration_results::tests::test_types::{AttachmentKindTestCase, NormalizeTestCase};
use crate::json::models::JsonValue;

#[test]
fn given_integration_records_when_normalizing_then_contract_is_enforced() {
    let test_cases = [
        NormalizeTestCase {
            description: "a minimal asset record gains every default in field order",
            record: record(orders_asset("success"), "2026-09-02T12:00:00.123456+00:00"),
            expected_error: None,
            expected_encoded: Some(
                "{\"schema_version\":1,\"record_kind\":\"integration_result\",\"event_id\":\"e1\",\"event_sequence\":0,\"event_type\":\"resource_attempt_completed\",\"occurred_at\":\"2026-09-02T12:00:00.123456+00:00\",\"invocation_id\":\"i1\",\"run_id\":\"r1\",\"resource_id\":\"model:orders\",\"resource_attempt_id\":\"a1\",\"operation_id\":null,\"statement_id\":null,\"resource_kind\":\"model\",\"resource_name\":\"orders\",\"attempt_number\":1,\"duration_ms\":3,\"output_kind\":\"asset\",\"command\":\"build\",\"error_code\":null,\"error_type\":null,\"skip_code\":null,\"skip_mode\":null,\"projection_degraded\":false,\"asset\":{\"kind\":\"model\",\"name\":\"orders\",\"status\":\"success\",\"action\":null,\"target\":null,\"origin_relation\":null,\"staging_relation\":null,\"failed_phase\":null,\"loader\":null,\"rows_loaded\":null,\"materialized\":null,\"future_cursor_safety\":{},\"maximum_start_safety\":{},\"microbatch\":{\"run_type\":\"normal\"}},\"checks\":[]}",
            ),
        },
        NormalizeTestCase {
            description: "a naive occurrence time is rejected",
            record: record(orders_asset("success"), "2026-09-02T12:00:00"),
            expected_error: Some("integration result occurred_at must include a timezone"),
            expected_encoded: None,
        },
        NormalizeTestCase {
            description: "an unknown asset status is rejected",
            record: record(orders_asset("pending"), "2026-09-02T12:00:00Z"),
            expected_error: Some("integration asset status is unsupported"),
            expected_encoded: None,
        },
        NormalizeTestCase {
            description: "an unknown asset field makes the envelope invalid",
            record: record(
                object(vec![
                    ("kind", text("model")),
                    ("name", text("orders")),
                    ("status", text("success")),
                    ("colour", text("blue")),
                ]),
                "2026-09-02T12:00:00Z",
            ),
            expected_error: Some("invalid integration result envelope"),
            expected_encoded: None,
        },
    ];

    for test_case in test_cases {
        let normalized = normalize_integration_record(test_case.record);
        let error: Option<String> = normalized.as_ref().err().map(|error| error.message.clone());
        let encoded: Option<String> = normalized
            .ok()
            .and_then(|record| encode_integration_value(&JsonValue::Object(record), true).ok());
        assert_eq!(
            (error.as_deref(), encoded.as_deref()),
            (test_case.expected_error, test_case.expected_encoded),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_newer_enrichment_when_stripping_then_record_keeps_core_fields() {
    let test_cases = [NormalizeTestCase {
        description: "optional asset and microbatch enum enrichment is dropped",
        record: record(
            object(vec![
                ("kind", text("model")),
                ("name", text("orders")),
                ("status", text("success")),
                ("failed_phase", text("future_phase")),
                (
                    "microbatch",
                    object(vec![("run_type", text("new")), ("batch_count", integer(2))]),
                ),
            ]),
            "2026-09-02T12:00:00Z",
        ),
        expected_error: None,
        expected_encoded: Some("{\"batch_count\":2}"),
    }];

    for test_case in test_cases {
        let normalized = normalize_integration_record(strip_optional_enrichment(test_case.record));
        let error: Option<String> = normalized.as_ref().err().map(|error| error.message.clone());
        let microbatch: Option<String> = normalized.ok().and_then(|record| {
            let asset: JsonValue = record.into_iter().find(|(key, _)| key == "asset")?.1;
            let JsonValue::Object(asset) = asset else {
                return None;
            };
            let microbatch: JsonValue = asset.into_iter().find(|(key, _)| key == "microbatch")?.1;
            encode_integration_value(&microbatch, false).ok()
        });
        assert_eq!(
            (error.as_deref(), microbatch.as_deref()),
            (test_case.expected_error, test_case.expected_encoded),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_every_audit_attachment_kind_when_normalizing_check_then_it_is_supported() {
    let test_cases = [
        AttachmentKindTestCase {
            description: "a model audit check is supported",
            attachment_kind: "model",
            expected_error: None,
        },
        AttachmentKindTestCase {
            description: "a source audit check is supported",
            attachment_kind: "source",
            expected_error: None,
        },
        AttachmentKindTestCase {
            description: "a seed audit check is supported",
            attachment_kind: "seed",
            expected_error: None,
        },
        AttachmentKindTestCase {
            description: "an end-of-run audit check is supported",
            attachment_kind: "end",
            expected_error: None,
        },
        AttachmentKindTestCase {
            description: "an unknown attachment kind is rejected",
            attachment_kind: "warehouse",
            expected_error: Some("integration check attachment_kind is unsupported"),
        },
    ];

    for test_case in test_cases {
        let normalized =
            normalize_integration_record(audit_check_record(test_case.attachment_kind));
        let error: Option<String> = normalized.as_ref().err().map(|error| error.message.clone());
        assert_eq!(
            error.as_deref(),
            test_case.expected_error,
            "{}",
            test_case.description
        );
    }
}
