//! Playground templates, skill install locations and generated-file markers.

pub(crate) const PLAYGROUND_TEMPLATES: [&str; 5] = [
    "waffle_shop",
    "loader_waffle_shop",
    "dagster",
    "rivers",
    "python_nodes",
];
pub(crate) const WAFFLE_SHOP_TEMPLATE: &str = "waffle_shop";
pub(crate) const LOADER_WAFFLE_SHOP_TEMPLATE: &str = "loader_waffle_shop";
pub(crate) const PYTHON_NODES_TEMPLATE: &str = "python_nodes";
pub(crate) const DAGSTER_TEMPLATE: &str = "dagster";
pub(crate) const RIVERS_TEMPLATE: &str = "rivers";
pub(crate) const ORCHESTRATED_TEMPLATES: [&str; 2] = [DAGSTER_TEMPLATE, RIVERS_TEMPLATE];
pub(crate) const ORCHESTRATED_PROJECT_DIR: &str = "waffle_shop";
pub(crate) const PYTHON_TEMPLATE_SUFFIX: &str = ".py.txt";
pub(crate) const TEMPLATE_SUFFIX: &str = ".txt";
pub(crate) const GENERATED_MARKER: &str = "<!-- generated-by: sqlbuild skills -->";
pub(crate) const LEGACY_GENERATED_MARKER: &str = "<!-- generated-by: sqlbuild skills update -->";
pub(crate) const FRONTMATTER_OPENING: &str = "---\n";
pub(crate) const FRONTMATTER_CLOSING: &str = "\n---\n";
pub(crate) const SKILL_NAME: &str = "sqlbuild";
pub(crate) const SKILL_ENTRY_FILE: &str = "SKILL.md";
pub(crate) const SKILL_FILE_SUFFIX: &str = ".md";
pub(crate) const SKIPPED_SKILL_PREFIXES: [&str; 2] = [".", "__"];
pub(crate) const VALID_SKILL_TARGETS: [&str; 3] = ["opencode", "claude", "agents"];
pub(crate) const DEFAULT_SKILL_TARGETS: [&str; 2] = ["agents", "claude"];
pub(crate) const OPENCODE_TARGET: &str = "opencode";
pub(crate) const CLAUDE_TARGET: &str = "claude";
pub(crate) const UTF8_BYTE_ORDER_MARK: char = '\u{feff}';
pub(crate) const GIT_MARKER: &str = ".git";
pub(crate) const PLAYGROUND_EXAMPLES: [(&str, &str); 4] = [
    (DAGSTER_TEMPLATE, "waffle shop + Dagster"),
    (RIVERS_TEMPLATE, "waffle shop + Rivers"),
    (LOADER_WAFFLE_SHOP_TEMPLATE, "loader-focused waffle shop"),
    (PYTHON_NODES_TEMPLATE, "Python nodes demo"),
];
pub(crate) const DEFAULT_EXAMPLE: &str = "waffle shop";
pub(crate) const PYTHON_NODES_COMMANDS: [&str; 3] = [
    "sqb plan --select +fact_orders --select +orders_export",
    "sqb build --select +fact_orders --select +orders_export",
    "sqb check --select check_orders_export",
];
pub(crate) const PROJECT_COMMANDS: [&str; 4] =
    ["sqb compile", "sqb build", "sqb test", "sqb audit"];
pub(crate) const DAGSTER_COMMAND: &str = "DAGSTER_IS_DEV_CLI=1 dagster dev -f definitions.py";
pub(crate) const RIVERS_COMMAND: &str = "rivers dev definitions";
