use std::path::{Path, PathBuf};

use crate::custom_host_pool::models::HostEvaluation;
use crate::custom_host_pool::types::{HostInvocation, HostPlan};

/// Write a fake `/proc/self/cgroup` and a cgroup hierarchy below `root`.
pub(super) fn write_cgroup_files(
    root: &Path,
    (proc_cgroup, files): (&[u8], &[(&str, &[u8])]),
) -> PathBuf {
    for (relative_path, contents) in files {
        let path: PathBuf = root.join("cgroup").join(relative_path);
        std::fs::create_dir_all(path.parent().expect("parent")).expect("cgroup folder");
        std::fs::write(path, contents).expect("cgroup file");
    }
    let proc: PathBuf = root.join("proc-self-cgroup");
    std::fs::write(&proc, proc_cgroup).expect("process cgroup");
    proc
}

pub(super) fn plan(entries: &[(&str, Option<&[&str]>)]) -> HostPlan {
    entries
        .iter()
        .map(|(code, subjects)| {
            (
                (*code).to_owned(),
                subjects.map(|subjects| {
                    subjects
                        .iter()
                        .map(|subject| (*subject).to_owned())
                        .collect()
                }),
            )
        })
        .collect()
}

pub(super) fn invocations(entries: &[(&str, &str)]) -> Vec<HostInvocation> {
    entries
        .iter()
        .map(|(code, subject)| ((*code).to_owned(), (*subject).to_owned()))
        .collect()
}

pub(super) fn evaluation(code: &str, subject: &str, reads: Option<&[&[&str]]>) -> HostEvaluation {
    HostEvaluation {
        code: code.to_owned(),
        subject: subject.to_owned(),
        findings: Vec::new(),
        reads: reads.map(|keys| {
            keys.iter()
                .map(|key| key.iter().map(|part| (*part).to_owned()).collect())
                .collect()
        }),
    }
}
