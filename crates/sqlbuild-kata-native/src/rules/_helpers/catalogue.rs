use crate::constants::{
    API_VERSION, BUILT_IN_RULE_NAMESPACE, CUSTOM_RULE_NAMESPACE, DEFAULT_RULE_CODE,
};
use crate::models::{CustomRule, ResolveRulesRequest, RuleMetadata};
use fensu_policy::policy::errors::PolicyError;
use fensu_policy::policy::main::resolve_policy::resolve_policy;
use fensu_policy::policy::models::{PolicySelectors, ProductRuleCodeGrammar};
use fensu_policy::policy::types::RuleCodeGrammar;
use sha2::{Digest, Sha256};

const CUSTOM_RULE_COVERAGE_CODE: &str = "SQBKX201";

fn grammar() -> Result<ProductRuleCodeGrammar, String> {
    ProductRuleCodeGrammar::new(BUILT_IN_RULE_NAMESPACE, CUSTOM_RULE_NAMESPACE)
}

macro_rules! rule {
    ($code:expr, $family:expr, $slug:expr, $message:expr, $remediation:expr $(,)?) => {
        RuleMetadata {
            code: $code.into(),
            family: $family.into(),
            slug: $slug.into(),
            message: $message.into(),
            remediation: $remediation.into(),
            implementation_fingerprint: env!("CARGO_PKG_VERSION").into(),
            enabled_by_default: $code == DEFAULT_RULE_CODE,
            project_wide: matches!($code, "SQBKH101" | "SQBKH201" | "SQBKX201"),
            custom: false,
        }
    };
}

pub(crate) fn catalogue() -> Vec<RuleMetadata> {
    let mut rules = vec![
        rule!(
            "SQBKS000",
            "structure",
            "cte-comment-discipline",
            "standalone SQL comments belong only on the first inner line of a CTE",
            "Move this comment to the first inner line of the CTE it explains, or move model-level rationale into the MODEL description.",
        ),
        rule!(
            "SQBKS001",
            "structure",
            "cte-only-body",
            "model SQL must keep transformation logic in top-level CTEs",
            "Move transformation logic into named top-level CTEs before the terminal SELECT.",
        ),
        rule!(
            "SQBKS002",
            "structure",
            "single-terminal-select",
            "the terminal SELECT must read from the final top-level CTE",
            "Name the final logical CTE and leave one terminal SELECT from that CTE.",
        ),
        rule!(
            "SQBKS101",
            "structure",
            "dependency-import-ctes",
            "dependencies must be isolated in import CTEs",
            "Move each __ref(...) or __source(...) into one named top-level import CTE and reference that CTE from later logic.",
        ),
        rule!(
            "SQBKS201",
            "structure",
            "select-star-discipline",
            "SELECT * is allowed only inside dependency import CTEs",
            "Enumerate output columns in this logical CTE or terminal SELECT; keep * only in a dependency import CTE.",
        ),
        rule!(
            "SQBKS202",
            "structure",
            "set-operation-star",
            "positional set operations must not use star branches",
            "Enumerate matching columns in every branch or use a supported BY NAME set operation.",
        ),
        rule!(
            "SQBKS301",
            "structure",
            "nested-cte",
            "CTEs must be top-level",
            "Hoist this nested CTE into the model's top-level WITH list.",
        ),
        rule!(
            "SQBKS302",
            "structure",
            "recursive-cte",
            "recursive CTEs are not permitted",
            "Replace the recursive CTE with an explicit upstream model or a bounded non-recursive shape.",
        ),
        rule!(
            "SQBKS401",
            "structure",
            "view-marker",
            "view materialization and model v marker must agree",
            "Use stg_v/int_v/mart_v for a view, or change the materialization to match the non-view layer name.",
        ),
        rule!(
            "SQBKS501",
            "structure",
            "descriptive-cte-name",
            "CTE names must describe their contents",
            "Name this CTE for what it holds, such as filtered_orders or top_two_finishers.",
        ),
        rule!(
            "SQBKL001",
            "layers",
            "forward-only-references",
            "model dependencies must flow forward through the layer order",
            "Move the dependency logic to the current or an earlier layer; skipping layers forward is allowed, reaching backward from an earlier layer is not.",
        ),
        rule!(
            "SQBKL101",
            "layers",
            "declared-table-references",
            "table dependencies must use __ref or __source",
            "Replace this qualified table with __ref(\"<model>\") or __source(\"<source>\") so it participates in the DAG.",
        ),
        rule!(
            "SQBKR001",
            "layers",
            "model-name-grammar",
            "model names must use the closed kata layer grammar",
            "Rename deterministic conforming work to int_clean and cross-source resolution work to int_enriched; express additional steps in the entity suffix.",
        ),
        rule!(
            "SQBKR002",
            "layers",
            "folder-layer",
            "model layer names must match their folders",
            "Move the model beneath staging/, intermediate/, or mart/ to match its name, or rename it for the folder that owns it.",
        ),
        rule!(
            "SQBKR201",
            "layers",
            "source-token-policy",
            "model source suffixes must use approved, current tokens",
            "Rename the source suffix at this model path to the configured token.",
        ),
        rule!(
            "SQBKR301",
            "layers",
            "reference-name-policy",
            "referenced model identifiers must follow kata naming grammar",
            "Rename the referenced model and this __ref to the kata model grammar.",
        ),
        rule!(
            "SQBKR401",
            "layers",
            "contract-enforced-required",
            "models must declare an enforced output contract",
            "Declare contract enforced and list the authoritative output columns in MODEL().",
        ),
        rule!(
            "SQBKJ001",
            "joins",
            "no-comma-join",
            "implicit comma joins are not permitted",
            "Replace the comma join with an explicit JOIN ... ON <key> at this FROM.",
        ),
        rule!(
            "SQBKJ101",
            "joins",
            "explicit-join-key",
            "non-cross joins must declare ON or USING",
            "Add an explicit JOIN ... ON <key> or JOIN ... USING (<key>) condition.",
        ),
        rule!(
            "SQBKJ002",
            "joins",
            "no-cross-join",
            "cross joins require an explicit project exception",
            "Replace CROSS JOIN with an explicit keyed join, or add a reasoned exact exception when the Cartesian product is intentional.",
        ),
        rule!(
            "SQBKN001",
            "naming",
            "boolean-column-name",
            "boolean column names must have BOOLEAN types",
            "Declare this is_/has_/can_ column as BOOLEAN in columns (...), or rename it to match its actual type.",
        ),
        rule!(
            "SQBKN002",
            "naming",
            "timestamp-column-name",
            "timestamp column names must have timestamp types",
            "Declare this *_at/*_ts/*_timestamp column with a timestamp type in columns (...), or rename it.",
        ),
        rule!(
            "SQBKN003",
            "naming",
            "date-column-name",
            "date column names must have DATE types",
            "Declare this *_date column as DATE in columns (...), or rename it to match its actual type.",
        ),
        rule!(
            "SQBKH001",
            "hygiene",
            "named-enum-decisions",
            "enum comparisons must use declared enum members",
            "Replace this bare string with @enum(\"<enum>\").<MEMBER> so the decision uses the declared domain.",
        ),
        rule!(
            "SQBKH002",
            "hygiene",
            "named-numeric-decisions",
            "non-canonical numeric comparisons must use constants",
            "Declare the threshold as a CONSTANT and compare through @const(\"<name>\"); only -1, 0, and 1 are self-explanatory.",
        ),
        rule!(
            "SQBKH101",
            "hygiene",
            "duplicate-enums",
            "identical enum domains must be consolidated",
            "Keep one public enum declaration and replace the duplicate declaration's references with it.",
        ),
        rule!(
            "SQBKH201",
            "hygiene",
            "declaration-domain-placement",
            "public enum and constant files must live under a configured domain folder",
            "Move this declaration beneath enums/<domain>/ or constants/<domain>/.",
        ),
        rule!(
            "SQBKX001",
            "tests",
            "minimum-audits",
            "non-passthrough models must declare the configured minimum audits",
            "Attach concrete not_null, unique, or accepted_values audits to this model's contract; audits gate promotion when bad rows appear.",
        ),
        rule!(
            "SQBKX002",
            "tests",
            "minimum-tests",
            "non-passthrough models must have the configured minimum unit tests",
            "Add a failable SQL unit test that targets this model's real logic.",
        ),
        rule!(
            "SQBKX201",
            "tests",
            "custom-rule-test-coverage",
            "selected custom kata rules must have public-harness test cases",
            "Add RuleCase values evaluated by evaluate_rule under tests/.",
        ),
    ];
    rules.sort_by(|a, b| a.code.cmp(&b.code));
    rules
}

pub(crate) fn with_custom(custom: &[CustomRule]) -> Result<Vec<RuleMetadata>, String> {
    let grammar = grammar()?;
    let mut result = catalogue();
    for item in custom {
        if !grammar.rule_code_is_exact(&item.code) || !item.code.starts_with("XSQBK") {
            return Err(format!("invalid kata rule code: {}", item.code));
        }
        result.push(RuleMetadata {
            code: item.code.clone(),
            family: item.family.clone(),
            slug: item.slug.clone(),
            message: item.message.clone(),
            remediation: item.remediation.clone(),
            implementation_fingerprint: item.implementation_fingerprint.clone(),
            enabled_by_default: item.enabled_by_default,
            project_wide: item.project_wide,
            custom: true,
        });
    }
    result.sort_by(|a, b| a.code.cmp(&b.code));
    for pair in result.windows(2) {
        if pair[0].code == pair[1].code {
            return Err(format!("duplicate kata rule codes: {}", pair[0].code));
        }
    }
    Ok(result)
}

pub(crate) fn select<'a>(
    catalogue: &'a [RuleMetadata],
    selected: &[String],
    ignored: &[String],
) -> Result<Vec<&'a RuleMetadata>, String> {
    let grammar = grammar()?;
    let references: Vec<&RuleMetadata> = catalogue.iter().collect();
    let configured = PolicySelectors {
        select: selected.to_vec(),
        warn: Vec::new(),
        ignore: Vec::new(),
    };
    let configured_policy =
        resolve_policy(&references, &(), &configured, &grammar).map_err(policy_error)?;
    let mut effective_select = selected.to_vec();
    if configured_policy.blocking.iter().any(|rule| rule.custom)
        && !effective_select
            .iter()
            .any(|code| code == CUSTOM_RULE_COVERAGE_CODE)
    {
        effective_select.push(CUSTOM_RULE_COVERAGE_CODE.to_owned());
    }
    let effective = PolicySelectors {
        select: effective_select,
        warn: Vec::new(),
        ignore: ignored.to_vec(),
    };
    resolve_policy(&references, &(), &effective, &grammar)
        .map(|policy| policy.blocking)
        .map_err(policy_error)
}

pub(crate) fn selected_codes_json(request_json: &str) -> Result<String, String> {
    let request: ResolveRulesRequest = serde_json::from_str(request_json)
        .map_err(|error| format!("invalid kata policy request: {error}"))?;
    if request.version != API_VERSION {
        return Err(format!(
            "unsupported kata native API version {}; expected {API_VERSION}",
            request.version
        ));
    }
    crate::configuration::main::validate::validate(&request.config)?;
    let rules = with_custom(&request.custom_rules)?;
    let selected = select(&rules, &request.config.select, &request.config.ignore)?;
    let codes: Vec<&str> = selected.iter().map(|rule| rule.code.as_str()).collect();
    serde_json::to_string(&codes).map_err(|error| error.to_string())
}

fn policy_error(error: PolicyError) -> String {
    match error {
        PolicyError::InvalidSelector { selector, .. } => {
            format!("malformed kata rule selector: {selector}")
        }
        PolicyError::SelectorMatchesNoConfiguredRule { selector, .. } => {
            format!("kata rule selector matches no rules: {selector}")
        }
        other => format!("invalid kata policy: {other}"),
    }
}

pub(crate) fn fingerprint(
    rules: &[&RuleMetadata],
    config: &crate::models::KataConfig,
) -> Result<String, String> {
    let payload = serde_json::to_vec(&(rules, config)).map_err(|e| e.to_string())?;
    Ok(format!("{:x}", Sha256::digest(payload)))
}
