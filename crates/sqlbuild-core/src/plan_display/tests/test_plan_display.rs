use crate::cli_text::models::{
    CliStyle, DisplayLimit, PreBuildWorkText, RetentionText, TableTypeText,
};
use crate::plan_display::main::cursor_bound_display::cursor_bound_display;
use crate::plan_display::main::effective_microbatch_batch_size::effective_microbatch_batch_size;
use crate::plan_display::main::effective_timestamp_grain::effective_timestamp_grain;
use crate::plan_display::main::format_no_input_rows::format_no_input_rows;
use crate::plan_display::main::format_pre_build_work::format_pre_build_work;
use crate::plan_display::main::format_query_diff::format_query_diff;
use crate::plan_display::main::format_waiting_on_empty_inputs::format_waiting_on_empty_inputs;
use crate::plan_display::main::model_execution_annotation::model_execution_annotation;
use crate::plan_display::main::model_materialization_label::model_materialization_label;
use crate::plan_display::main::model_resource_type::model_resource_type;
use crate::plan_display::models::{ModelLabelFacts, ParsedBound, TimestampGrainFacts};
use crate::plan_display::tests::helpers::{facts, timestamp_grains};
use crate::plan_display::tests::test_types::{
    BatchSizeTestCase, BoundTestCase, LabelTestCase, NamesTestCase, PreBuildWorkTestCase,
    QueryDiffTestCase, TimestampGrainTestCase,
};

#[test]
fn given_planned_model_when_labelling_then_matches_plan_and_progress_text() {
    let test_cases = [
        LabelTestCase {
            description: "a view",
            entry: facts("view", "create_view"),
            expected_label: "view",
            expected_resource_type: "view",
            expected_annotation: "",
        },
        LabelTestCase {
            description: "a microbatch incremental with a cursor type",
            entry: ModelLabelFacts {
                incremental_strategy: Some("delete_insert".to_owned()),
                incremental_mode: Some("microbatch".to_owned()),
                cursor_type: Some("timestamp".to_owned()),
                ..facts("incremental", "incremental_delete_insert")
            },
            expected_label: "delete_insert (timestamp, microbatch)",
            expected_resource_type: "table",
            expected_annotation: "delete_insert",
        },
        LabelTestCase {
            description: "an incremental without a strategy",
            entry: ModelLabelFacts {
                incremental_strategy: Some(String::new()),
                ..facts("incremental", "full_build")
            },
            expected_label: "incremental",
            expected_resource_type: "table",
            expected_annotation: "",
        },
        LabelTestCase {
            description: "a historical snapshot",
            entry: ModelLabelFacts {
                snapshot_strategy: Some("timestamp".to_owned()),
                historical: true,
                ..facts("snapshot", "snapshot")
            },
            expected_label: "snapshot (timestamp, historical snapshot)",
            expected_resource_type: "snapshot",
            expected_annotation: "timestamp, historical snapshot",
        },
        LabelTestCase {
            description: "a bare snapshot",
            entry: facts("snapshot", "snapshot"),
            expected_label: "snapshot",
            expected_resource_type: "snapshot",
            expected_annotation: "",
        },
        LabelTestCase {
            description: "a custom materialization",
            entry: ModelLabelFacts {
                custom_materialization_name: Some("partition_tracked".to_owned()),
                ..facts("custom", "custom")
            },
            expected_label: "partition_tracked (custom)",
            expected_resource_type: "custom",
            expected_annotation: "",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            (
                model_materialization_label(&test_case.entry),
                model_resource_type(Some(&test_case.entry)),
                model_execution_annotation(Some(&test_case.entry)),
            ),
            (
                test_case.expected_label.to_owned(),
                test_case.expected_resource_type,
                test_case.expected_annotation.to_owned(),
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_cursor_bound_when_displaying_then_collapses_whole_day_midnights() {
    let midnight: ParsedBound = ParsedBound {
        date: "2026-01-02".to_owned(),
        midnight: true,
    };
    let test_cases = [
        BoundTestCase {
            description: "a day-grain midnight collapses to its date",
            value: "2026-01-02T00:00:00",
            typing: (Some("timestamp"), Some("day")),
            parsed: Some(midnight.clone()),
            expected_text: "2026-01-02",
        },
        BoundTestCase {
            description: "an hour grain keeps the time",
            value: "2026-01-02T00:00:00",
            typing: (Some("timestamp"), Some("hour")),
            parsed: Some(midnight.clone()),
            expected_text: "2026-01-02T00:00:00",
        },
        BoundTestCase {
            description: "an integer cursor is shown as is",
            value: "42",
            typing: (Some("integer"), Some("day")),
            parsed: Some(midnight),
            expected_text: "42",
        },
        BoundTestCase {
            description: "an unparsed value is shown as is",
            value: "later",
            typing: (None, Some("day")),
            parsed: None,
            expected_text: "later",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            cursor_bound_display(test_case.value, test_case.typing, test_case.parsed.as_ref()),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_empty_inputs_when_formatting_then_names_them() {
    let test_cases = [
        NamesTestCase {
            description: "one input",
            names: vec!["orders".to_owned()],
            expected_no_rows: "no input rows (orders)",
            expected_waiting: "waiting on empty input orders; other inputs have new rows",
        },
        NamesTestCase {
            description: "two inputs",
            names: vec!["orders".to_owned(), "returns".to_owned()],
            expected_no_rows: "no input rows (orders, returns)",
            expected_waiting: "waiting on empty inputs orders, returns; other inputs have new rows",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            (
                format_no_input_rows(&test_case.names),
                format_waiting_on_empty_inputs(&test_case.names)
            ),
            (
                test_case.expected_no_rows.to_owned(),
                test_case.expected_waiting.to_owned()
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_batch_size_when_resolving_effective_size_then_uses_grain_unit() {
    let test_cases = [
        BatchSizeTestCase {
            description: "a declared size is kept",
            batch_size: "2d",
            grain: "hour",
            expected_size: Ok("2d"),
        },
        BatchSizeTestCase {
            description: "effective follows the grain",
            batch_size: "effective",
            grain: "month",
            expected_size: Ok("1mo"),
        },
        BatchSizeTestCase {
            description: "an unknown grain is an error",
            batch_size: "effective",
            grain: "week",
            expected_size: Err("week"),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            effective_microbatch_batch_size(test_case.batch_size, test_case.grain)
                .map_err(|error| error.0),
            test_case
                .expected_size
                .map(str::to_owned)
                .map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_cursor_grains_when_resolving_replay_grain_then_coarsest_timestamp_grain_wins() {
    let test_cases = [
        TimestampGrainTestCase {
            description: "an integer cursor has no grain",
            facts: TimestampGrainFacts {
                cursor_type: Some("integer".to_owned()),
                downstream_grain: Some("day".to_owned()),
                ..TimestampGrainFacts::default()
            },
            expected_grain: Ok(None),
        },
        TimestampGrainTestCase {
            description: "no declared grain defaults to second",
            facts: timestamp_grains(None, None, &[]),
            expected_grain: Ok(Some("second")),
        },
        TimestampGrainTestCase {
            description: "a coarser input grain wins",
            facts: timestamp_grains(None, Some("day"), &[Some("month"), None, Some("hour")]),
            expected_grain: Ok(Some("month")),
        },
        TimestampGrainTestCase {
            description: "an empty declared grain counts as second",
            facts: timestamp_grains(None, Some(""), &[Some("minute")]),
            expected_grain: Ok(Some("minute")),
        },
        TimestampGrainTestCase {
            description: "watermark replay keeps the declared grain",
            facts: timestamp_grains(Some("watermark"), Some("hour"), &[Some("year")]),
            expected_grain: Ok(Some("hour")),
        },
        TimestampGrainTestCase {
            description: "an unknown input grain is an error",
            facts: timestamp_grains(None, Some("day"), &[Some("week")]),
            expected_grain: Err("week"),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            effective_timestamp_grain(&test_case.facts).map_err(|error| error.0),
            test_case
                .expected_grain
                .map(|grain| grain.map(str::to_owned))
                .map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_storage_work_when_formatting_pre_build_work_then_matches_python_text() {
    let table_type = TableTypeText {
        model_name: "orders".into(),
        desired_type: "transient".into(),
        actual_type: None,
        source: "model".into(),
        irreversible_warning: Some("drops history".into()),
    };
    let retention = RetentionText {
        scope: "analytics.orders".into(),
        desired_days: 7,
        actual_days: Some(1),
        effective_days: None,
        source: "project".into(),
        direction: "increase".into(),
        phase: "pre_build".into(),
        irreversible_warning: None,
    };
    let test_cases = [
        PreBuildWorkTestCase {
            description: "lists every entry without a limit",
            work: PreBuildWorkText {
                table_types: vec![table_type.clone()],
                retention: vec![retention],
                display: DisplayLimit {
                    max_entries: None,
                    overflow_flag: "--verbose".into(),
                },
            },
            expected_lines: vec![
                "Table type conversions",
                "  orders desired=transient actual=unknown source=model",
                "    WARNING: drops history",
                "Retention",
                "  analytics.orders desired=7d actual=1d effective=missing source=project direction=increase phase=pre_build",
            ],
        },
        PreBuildWorkTestCase {
            description: "limits table types with an overflow hint",
            work: PreBuildWorkText {
                table_types: vec![table_type.clone(), table_type],
                retention: vec![],
                display: DisplayLimit {
                    max_entries: Some(0),
                    overflow_flag: "--verbose".into(),
                },
            },
            expected_lines: vec![
                "Table type conversions",
                "\u{1b}[2m  ... and 2 more (use --verbose to show all)\u{1b}[0m",
            ],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            format_pre_build_work(Vec::new(), &test_case.work),
            test_case.expected_lines,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_unified_diff_when_formatting_query_diff_then_lines_are_indented_and_coloured() {
    let diff: Vec<String> = [
        "--- previous",
        "+++ current",
        "@@ -1 +1 @@",
        "-a",
        "+b",
        " c",
    ]
    .into_iter()
    .map(String::from)
    .collect();
    let test_cases = [
        QueryDiffTestCase {
            description: "plain diff is only indented",
            style: CliStyle { use_color: false },
            expected_lines: vec![
                "      --- previous",
                "      +++ current",
                "      @@ -1 +1 @@",
                "      -a",
                "      +b",
                "       c",
            ],
        },
        QueryDiffTestCase {
            description: "coloured diff marks additions, removals and headers",
            style: CliStyle { use_color: true },
            expected_lines: vec![
                "\x1b[2m      --- previous\x1b[0m",
                "\x1b[2m      +++ current\x1b[0m",
                "\x1b[2m      @@ -1 +1 @@\x1b[0m",
                "\x1b[38;5;167m      -a\x1b[0m",
                "\x1b[32m      +b\x1b[0m",
                "       c",
            ],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            format_query_diff(&diff, test_case.style),
            test_case.expected_lines,
            "{}",
            test_case.description
        );
    }
}
