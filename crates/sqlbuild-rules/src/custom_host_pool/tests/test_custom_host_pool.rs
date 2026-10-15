use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

use serde_json::json;

use crate::custom_host_pool::constants::MIN_INVOCATIONS_PER_HOST;
use crate::custom_host_pool::main::available_cores::available_cores;
use crate::custom_host_pool::main::decode_host_response::decode_host_response;
use crate::custom_host_pool::main::host_count::host_count;
use crate::custom_host_pool::main::merge_host_slices::merge_host_slices;
use crate::custom_host_pool::main::partition_host_plan::partition_host_plan;
use crate::custom_host_pool::models::HostSlice;
use crate::custom_host_pool::tests::helpers::{evaluation, invocations, plan, write_cgroup_files};
use crate::custom_host_pool::tests::test_types::{
    DecodeTestCase, HostCapacityTestCase, HostCountTestCase, HostPlanTestCase, MergeTestCase,
};

const NODE_CPUS: usize = 64;

#[test]
fn given_cgroup_quota_when_counting_cores_then_quota_caps_process_cpus() {
    let test_cases = [
        HostCapacityTestCase {
            description: "cgroup v2 quota on the process cgroup",
            proc_cgroup: b"0::/kubepods/orders\n",
            files: &[("kubepods/orders/cpu.max", b"400000 100000\n")],
            expected_cores: 4,
        },
        HostCapacityTestCase {
            description: "cgroup v2 fractional quota rounds up",
            proc_cgroup: b"0::/kubepods/orders\n",
            files: &[("kubepods/orders/cpu.max", b"150000 100000\n")],
            expected_cores: 2,
        },
        HostCapacityTestCase {
            description: "cgroup v2 ancestor quota is tighter",
            proc_cgroup: b"0::/kubepods/orders\n",
            files: &[
                ("kubepods/cpu.max", b"200000 100000\n"),
                ("kubepods/orders/cpu.max", b"800000 100000\n"),
            ],
            expected_cores: 2,
        },
        HostCapacityTestCase {
            description: "cgroup v2 without a quota",
            proc_cgroup: b"0::/\n",
            files: &[("cpu.max", b"max 100000\n")],
            expected_cores: NODE_CPUS,
        },
        HostCapacityTestCase {
            description: "cgroup v1 CFS quota",
            proc_cgroup: b"4:cpu,cpuacct:/docker/orders\n",
            files: &[
                ("cpu,cpuacct/docker/orders/cpu.cfs_quota_us", b"300000\n"),
                ("cpu,cpuacct/docker/orders/cpu.cfs_period_us", b"100000\n"),
            ],
            expected_cores: 3,
        },
        HostCapacityTestCase {
            description: "cgroup v1 unlimited CFS quota",
            proc_cgroup: b"4:cpu,cpuacct:/\n",
            files: &[
                ("cpu,cpuacct/cpu.cfs_quota_us", b"-1\n"),
                ("cpu,cpuacct/cpu.cfs_period_us", b"100000\n"),
            ],
            expected_cores: NODE_CPUS,
        },
        HostCapacityTestCase {
            description: "no cgroup files",
            proc_cgroup: b"",
            files: &[],
            expected_cores: NODE_CPUS,
        },
        HostCapacityTestCase {
            description: "non-UTF-8 cgroup v2 quota is ignored",
            proc_cgroup: b"0::/kubepods/orders\n",
            files: &[("kubepods/orders/cpu.max", b"\xff\xfe 100000\n")],
            expected_cores: NODE_CPUS,
        },
        HostCapacityTestCase {
            description: "non-UTF-8 process cgroup is ignored",
            proc_cgroup: b"0::/kubepods/\xff\n",
            files: &[("kubepods/cpu.max", b"200000 100000\n")],
            expected_cores: NODE_CPUS,
        },
    ];
    for test_case in test_cases {
        let directory = tempfile::tempdir().expect("a temporary folder");
        let proc: PathBuf =
            write_cgroup_files(directory.path(), (test_case.proc_cgroup, test_case.files));

        let cores: usize = available_cores(NODE_CPUS, (&directory.path().join("cgroup"), &proc));

        assert_eq!(cores, test_case.expected_cores, "{}", test_case.description);
    }
}

#[test]
fn given_planned_invocations_when_partitioning_then_split_is_deterministic() {
    let test_cases = [
        HostPlanTestCase {
            description: "project rules and whole subjects are dealt round-robin",
            plan: plan(&[
                ("XSQBRT101", None),
                ("XSQBRT102", None),
                ("XSQBRT103", Some(&["models/b.sql"])),
            ]),
            invocations: invocations(&[
                ("XSQBRT102", ""),
                ("XSQBRT101", "models/a.sql"),
                ("XSQBRT101", "models/b.sql"),
                ("XSQBRT103", "models/b.sql"),
                ("XSQBRT101", "models/c.sql"),
            ]),
            hosts: 2,
            expected_plans: vec![
                plan(&[
                    ("XSQBRT101", Some(&["models/b.sql"])),
                    ("XSQBRT102", Some(&[""])),
                    ("XSQBRT103", Some(&["models/b.sql"])),
                ]),
                plan(&[
                    ("XSQBRT101", Some(&["models/a.sql", "models/c.sql"])),
                    ("XSQBRT102", Some(&[])),
                    ("XSQBRT103", Some(&[])),
                ]),
            ],
        },
        HostPlanTestCase {
            description: "one subject keeps the original plan",
            plan: plan(&[("XSQBRT101", None)]),
            invocations: invocations(&[("XSQBRT101", "models/a.sql")]),
            hosts: 4,
            expected_plans: vec![plan(&[("XSQBRT101", None)])],
        },
    ];
    for test_case in test_cases {
        let plans = partition_host_plan(&test_case.plan, &test_case.invocations, test_case.hosts);

        assert_eq!(plans, test_case.expected_plans, "{}", test_case.description);
    }
}

#[test]
fn given_invocation_count_when_sizing_hosts_then_hosts_follow_work_and_cores() {
    let test_cases = [
        HostCountTestCase {
            description: "hosts are capped on a large node",
            invocations: 10_000,
            cores: NODE_CPUS,
            min_invocations_per_host: MIN_INVOCATIONS_PER_HOST,
            expected_hosts: 8,
        },
        HostCountTestCase {
            description: "few invocations run on one host",
            invocations: 63,
            cores: NODE_CPUS,
            min_invocations_per_host: MIN_INVOCATIONS_PER_HOST,
            expected_hosts: 1,
        },
        HostCountTestCase {
            description: "cores cap the hosts",
            invocations: 1_000,
            cores: 2,
            min_invocations_per_host: MIN_INVOCATIONS_PER_HOST,
            expected_hosts: 2,
        },
        HostCountTestCase {
            description: "one invocation per host splits up to the cores",
            invocations: 7,
            cores: 3,
            min_invocations_per_host: 1,
            expected_hosts: 3,
        },
        HostCountTestCase {
            description: "more cores than invocations runs one host per invocation",
            invocations: 3,
            cores: 8,
            min_invocations_per_host: 1,
            expected_hosts: 3,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            host_count(
                test_case.invocations,
                (test_case.cores, test_case.min_invocations_per_host)
            ),
            test_case.expected_hosts,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_host_response_when_decoding_then_slice_or_rules_error_is_returned() {
    let test_cases = [
        DecodeTestCase {
            description: "tracked reads come from the read set table",
            response: json!({
                "readsets": [[["project.models"]]],
                "evaluations": [
                    {"code": "R1", "subject": null, "findings": [{"message": "m"}], "reads": 0},
                    {"code": "R2", "subject": "models/a.sql", "findings": [], "reads": 0},
                ],
                "untracked": {"R2": [["tree.paths"]]},
                "uncacheable": ["R3"],
                "observed": [[["tree.paths"], "abc"], [["tree.glob", "*.sql"], null]],
                "bounded": true,
                "stateful": ["R1"],
            }),
            expected_slice: Ok(HostSlice {
                evaluations: vec![
                    crate::custom_host_pool::models::HostEvaluation {
                        findings: vec![json!({"message": "m"})],
                        ..evaluation("R1", "", Some(&[&["project.models"]]))
                    },
                    evaluation("R2", "models/a.sql", None),
                ],
                untracked_reads: BTreeMap::from([(
                    "R2".to_owned(),
                    vec![vec!["tree.paths".to_owned()]],
                )]),
                uncacheable: BTreeSet::from(["R3".to_owned()]),
                observed: BTreeMap::from([
                    (vec!["tree.glob".to_owned(), "*.sql".to_owned()], None),
                    (vec!["tree.paths".to_owned()], Some("abc".to_owned())),
                ]),
                bounded: true,
                stateful: BTreeSet::from(["R1".to_owned()]),
            }),
        },
        DecodeTestCase {
            description: "a payload without its tables is invalid",
            response: json!({"readsets": []}),
            expected_slice: Err("custom rule host returned an invalid payload".to_owned()),
        },
        DecodeTestCase {
            description: "findings must be a list",
            response: json!({
                "readsets": [], "untracked": {}, "uncacheable": [], "observed": [],
                "evaluations": [{"code": "R1", "findings": {}}],
            }),
            expected_slice: Err("custom rule host returned invalid findings".to_owned()),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            decode_host_response(&test_case.response),
            test_case.expected_slice,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_host_slices_when_merging_then_results_follow_single_host_order() {
    let test_cases = [
        MergeTestCase {
            description: "split slices are reordered and conflicting observations forgotten",
            slices: vec![
                HostSlice {
                    evaluations: vec![evaluation("R1", "b", Some(&[&["k"]]))],
                    observed: BTreeMap::from([(vec!["t".to_owned()], Some("1".to_owned()))]),
                    ..HostSlice::default()
                },
                HostSlice {
                    evaluations: vec![evaluation("R1", "a", Some(&[&["k"]]))],
                    observed: BTreeMap::from([(vec!["t".to_owned()], Some("2".to_owned()))]),
                    ..HostSlice::default()
                },
            ],
            order: invocations(&[("R1", "a"), ("R1", "b")]),
            expected_order: invocations(&[("R1", "a"), ("R1", "b")]),
            expected_untracked: vec![],
            expected_observed: vec![(vec!["t".to_owned()], None)],
        },
        MergeTestCase {
            description: "a bounded host untracks every tracked rule",
            slices: vec![HostSlice {
                evaluations: vec![evaluation("R1", "a", Some(&[&["k"]]))],
                bounded: true,
                ..HostSlice::default()
            }],
            order: invocations(&[("R1", "a")]),
            expected_order: invocations(&[("R1", "a")]),
            expected_untracked: vec!["R1".to_owned()],
            expected_observed: vec![],
        },
    ];
    for test_case in test_cases {
        let run = merge_host_slices(test_case.slices, &test_case.order);
        let order: Vec<(String, String)> = run
            .evaluated
            .iter()
            .map(|evaluation| (evaluation.code.clone(), evaluation.subject.clone()))
            .collect();

        assert_eq!(order, test_case.expected_order, "{}", test_case.description);
        assert_eq!(
            run.untracked_reads.keys().cloned().collect::<Vec<_>>(),
            test_case.expected_untracked,
            "{}",
            test_case.description
        );
        assert_eq!(
            run.observed.into_iter().collect::<Vec<_>>(),
            test_case.expected_observed,
            "{}",
            test_case.description
        );
    }
}
