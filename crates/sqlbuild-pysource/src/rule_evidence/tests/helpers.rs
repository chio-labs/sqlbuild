use std::path::{Path, PathBuf};

const RULE_FILES: [(&str, &str); 4] = [
    ("rules/__init__.py", ""),
    (
        "rules/custom.py",
        "from rules.shared import util\nfrom .missing import nothing\n\ndef check(*, model, ctx):\n    return []\n",
    ),
    ("rules/shared/__init__.py", ""),
    ("rules/shared/util.py", "import os\n"),
];

/// A fresh project holding the rule files and `tests/test_rule.py` with `test_source`.
pub(crate) fn rule_project(name: &str, test_source: &str) -> PathBuf {
    let root: PathBuf = std::env::temp_dir()
        .join(format!("sqlbuild-rule-evidence-{}", std::process::id()))
        .join(name);
    let _ = std::fs::remove_dir_all(&root);
    for (path, contents) in RULE_FILES
        .into_iter()
        .chain([("tests/test_rule.py", test_source)])
    {
        write(&root.join(path), contents);
    }
    std::fs::canonicalize(&root).unwrap_or(root)
}

fn write(path: &Path, contents: &str) {
    let _ = std::fs::create_dir_all(path.parent().unwrap_or(path));
    let _ = std::fs::write(path, contents);
}
