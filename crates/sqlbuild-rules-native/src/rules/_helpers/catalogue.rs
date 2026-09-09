use crate::constants::API_VERSION;
use crate::models::RulesCodeGrammar;
use crate::models::{CustomRule, ResolveRulesRequest, RuleGuidance, RuleMetadata};
use fensu_policy::policy::errors::PolicyError;
use fensu_policy::policy::main::resolve_policy::resolve_policy;
use fensu_policy::policy::models::PolicySelectors;
use fensu_policy::policy::types::RuleCodeGrammar;
use sha2::{Digest, Sha256};

const CUSTOM_RULE_COVERAGE_CODE: &str = "SQBRTEST301";

macro_rules! rule {
    ($code:expr, $family:expr, $slug:expr, $message:expr, $remediation:expr $(,)?) => {
        RuleMetadata {
            code: $code.into(),
            family: $family.into(),
            slug: $slug.into(),
            message: $message.into(),
            remediation: $remediation.into(),
            guidance: None,
            implementation_fingerprint: env!("CARGO_PKG_VERSION").into(),
            enabled_by_default: true,
            project_wide: matches!(
                $code,
                "SQBRDECLARATION201"
                    | "SQBRDECLARATION301"
                    | "SQBRDECLARATION302"
                    | "SQBRDECLARATION303"
                    | "SQBRDECLARATION304"
                    | "SQBRDECLARATION305"
                    | "SQBRDECLARATION306"
                    | "SQBRPROJECT201"
                    | "SQBRPROJECT202"
                    | "SQBRPROJECT203"
                    | "SQBRPROJECT204"
                    | "SQBRTEST101"
                    | "SQBRTEST102"
                    | "SQBRTEST103"
                    | "SQBRTEST104"
                    | "SQBRTEST105"
                    | "SQBRTEST301"
            ),
            custom: false,
        }
    };
}

pub(crate) fn catalogue() -> Vec<RuleMetadata> {
    let mut rules = vec![
        rule!(
            "SQBRMODEL101",
            "structure",
            "dependency-import-ctes",
            "dependencies must be isolated in import CTEs",
            "Move each __ref(...) or __source(...) into one named top-level import CTE and reference that CTE from later logic.",
        ),
        rule!(
            "SQBRMODEL102",
            "structure",
            "select-star-discipline",
            "SELECT * is allowed only inside dependency import CTEs",
            "Enumerate output columns in this logical CTE or terminal SELECT; keep * only in a dependency import CTE.",
        ),
        rule!(
            "SQBRMODEL103",
            "structure",
            "view-marker",
            "view materialization and model v marker must agree",
            "Use stg_v/int_v/mart_v for a view, or change the materialization to match the non-view layer name.",
        ),
        rule!(
            "SQBRGRAPH101",
            "graph",
            "forward-only-references",
            "model dependencies must flow forward through the layer order",
            "Move the dependency logic to the current or an earlier layer; skipping layers forward is allowed, reaching backward from an earlier layer is not.",
        ),
        rule!(
            "SQBRGRAPH102",
            "graph",
            "declared-table-references",
            "table dependencies must use __ref or __source",
            "Replace this qualified table with __ref(\"<model>\") or __source(\"<source>\") so it participates in the DAG.",
        ),
        rule!(
            "SQBRPROJECT101",
            "repository",
            "model-name-grammar",
            "model names must use the closed rule layer grammar",
            "Rename deterministic conforming work to int_clean and cross-source resolution work to int_enriched; express additional steps in the entity suffix.",
        ),
        rule!(
            "SQBRPROJECT102",
            "repository",
            "folder-layer",
            "model layer names must match their folders",
            "Move the model beneath staging/, intermediate/, or mart/ to match its name, or rename it for the folder that owns it.",
        ),
        rule!(
            "SQBRPROJECT103",
            "repository",
            "source-token-policy",
            "model source suffixes must use approved, current tokens",
            "Rename the source suffix at this model path to the configured token.",
        ),
        rule!(
            "SQBRPROJECT104",
            "repository",
            "reference-name-policy",
            "referenced model identifiers must follow rule naming grammar",
            "Rename the referenced model and this __ref to the rule model grammar.",
        ),
        rule!(
            "SQBRCONTRACT101",
            "contracts",
            "contract-enforced-required",
            "models must declare an enforced output contract",
            "Declare contract enforced and list the authoritative output columns in MODEL().",
        ),
        rule!(
            "SQBRPROJECT201",
            "repository",
            "domain-level-layout",
            "models must resolve to one configured domain root and level",
            "Move the model beneath a configured level, or configure an explicit domain root when inference is ambiguous.",
        ),
        rule!(
            "SQBRPROJECT202",
            "repository",
            "owner-leaf-or-branch",
            "model owners must be either leaves or branches",
            "Keep models directly in a leaf owner, or move all direct models into meaningfully named child owners.",
        ),
        rule!(
            "SQBRPROJECT203",
            "repository",
            "maximum-subdomain-depth",
            "model ownership must stay within the configured subdomain depth",
            "Flatten this ownership path, promote part of it into the domain root, or increase max_subdomain_depth explicitly.",
        ),
        rule!(
            "SQBRPROJECT204",
            "repository",
            "shared-owner-prefix",
            "sibling owner names must not hide an implicit hierarchy",
            "Consolidate the shared concern, make the compressed token owner explicit, or rename siblings whose prefix is not ownership.",
        ),
        rule!(
            "SQBRCONTRACT102",
            "contracts",
            "boolean-column-name",
            "boolean column names must have BOOLEAN types",
            "Declare this is_/has_/can_ column as BOOLEAN in columns (...), or rename it to match its actual type.",
        ),
        rule!(
            "SQBRCONTRACT103",
            "contracts",
            "timestamp-column-name",
            "timestamp column names must have timestamp types",
            "Declare this *_at/*_ts/*_timestamp column with a timestamp type in columns (...), or rename it.",
        ),
        rule!(
            "SQBRCONTRACT104",
            "contracts",
            "date-column-name",
            "date column names must have DATE types",
            "Declare this *_date column as DATE in columns (...), or rename it to match its actual type.",
        ),
        rule!(
            "SQBRDECLARATION101",
            "declarations",
            "named-enum-decisions",
            "enum comparisons must use declared members and normalized operands",
            "Compare directly to @enum(\"<enum>\").<MEMBER>. Only a direct source-side value may be normalized in the comparison; move other normalization upstream and never wrap the enum member.",
        ),
        rule!(
            "SQBRDECLARATION102",
            "declarations",
            "named-numeric-decisions",
            "non-canonical numeric comparisons must use constants",
            "Declare the threshold as a CONSTANT and compare through @const(\"<name>\"); only -1, 0, and 1 are self-explanatory.",
        ),
        rule!(
            "SQBRDECLARATION201",
            "declarations",
            "duplicate-enums",
            "identical enum domains must be consolidated",
            "Keep one public enum declaration and replace the duplicate declaration's references with it.",
        ),
        rule!(
            "SQBRDECLARATION301",
            "declarations",
            "declaration-domain-placement",
            "public enum and constant files must live under a configured domain folder",
            "Move this declaration beneath enums/<domain>/ or constants/<domain>/.",
        ),
        rule!(
            "SQBRDECLARATION302",
            "declarations",
            "declaration-container-shape",
            "declaration role containers must be flat or grouped",
            "Keep files directly in the role container, or move every file into one level of meaningful concern buckets.",
        ),
        rule!(
            "SQBRDECLARATION303",
            "declarations",
            "declaration-container-depth",
            "declaration role buckets must stay within the configured depth",
            "Flatten nested buckets or increase max_role_container_depth explicitly.",
        ),
        rule!(
            "SQBRDECLARATION304",
            "declarations",
            "declaration-container-capacity",
            "declaration role containers and buckets must remain bounded",
            "Group files by a meaningful concern or increase the declaration-kind file threshold explicitly.",
        ),
        rule!(
            "SQBRDECLARATION305",
            "declarations",
            "declaration-bucket-name",
            "declaration role buckets must name a specific concern",
            "Rename this generic or reserved bucket after the concern it contains.",
        ),
        rule!(
            "SQBRDECLARATION306",
            "declarations",
            "declaration-container-prefix",
            "declaration filenames must not hide an obvious navigation bucket",
            "Group this compressed filename prefix into a scope-neutral concern bucket or rename files whose prefix is not a shared concern.",
        ),
        rule!(
            "SQBRTEST101",
            "tests",
            "canonical-test-roots",
            "SQL unit tests and scenarios must use their compiler-owned canonical roots",
            "Move unit tests beneath tests/unit/ and scenarios beneath tests/scenarios/.",
        ),
        rule!(
            "SQBRTEST102",
            "tests",
            "test-filename-grammar",
            "SQL test and scenario filenames must identify their subject and behavior",
            "Use test_<subject>__<behavior>.sql for unit tests and <subject>__<behavior>.sql for scenarios.",
        ),
        rule!(
            "SQBRTEST103",
            "tests",
            "semantic-test-mirroring",
            "SQL unit tests must mirror compiler-resolved resource ownership",
            "Move the test to the reported directory derived from its resolved models or direct tested resource.",
        ),
        rule!(
            "SQBRTEST104",
            "tests",
            "structured-test-name",
            "every SQL unit-test block must have a target-aware subject__expected_behavior name",
            "Add name \"<resolved_subject>__<expected_behavior>\" to this TEST header.",
        ),
        rule!(
            "SQBRTEST105",
            "tests",
            "scenario-business-description",
            "scenario descriptions must identify a concrete business behavior",
            "Write a non-generic SCENARIO description that states the business behavior under test.",
        ),
        rule!(
            "SQBRTEST201",
            "tests",
            "minimum-audits",
            "non-passthrough models must declare the configured minimum audits",
            "Attach concrete not_null, unique, or accepted_values audits to this model's contract; audits gate promotion when bad rows appear.",
        ),
        minimum_tests_rule(),
        rule!(
            "SQBRTEST301",
            "tests",
            "custom-rule-test-coverage",
            "selected custom rules must have public-harness test cases",
            "Add RuleCase values evaluated by evaluate_rule under tests/.",
        ),
    ];
    rules.extend(
        crate::sql_lint::main::catalogue::catalogue()
            .into_iter()
            .map(|rule| RuleMetadata {
                code: rule.code.into(),
                family: "sql".into(),
                slug: rule.code.to_ascii_lowercase(),
                message: rule.message.into(),
                remediation: rule.remediation.into(),
                guidance: None,
                implementation_fingerprint: env!("CARGO_PKG_VERSION").into(),
                enabled_by_default: true,
                project_wide: false,
                custom: false,
            }),
    );
    rules.sort_by(|a, b| a.code.cmp(&b.code));
    rules
}

fn minimum_tests_rule() -> RuleMetadata {
    let guidance = RuleGuidance {
        good_example: "For example:\n\nTEST();\n\nWITH\n__ref__upstream_model AS (\n  SELECT 1 AS order_id, 2 AS quantity\n),\n__expected__example_model AS (\n  SELECT 1 AS order_id, 4 AS doubled_quantity\n)\nSELECT 1"
            .into(),
        anti_tautology: "Choose input rows and concrete expected values that exercise the model's actual filter, join, aggregation, or mapping. Do not merely assert that inputs survive unchanged or re-derive expected values with the model's own logic."
            .into(),
        mutation_check: "Prove the test is failable: temporarily perturb the model logic or expected value, confirm the test fails, then revert the mutation."
            .into(),
    };
    RuleMetadata {
        code: "SQBRTEST202".into(),
        family: "tests".into(),
        slug: "minimum-tests".into(),
        message: "non-passthrough models must have the configured minimum unit tests".into(),
        remediation: guidance.remediation(
            "Add a SQL unit test that mocks each real import and asserts concrete transformed rows.",
        ),
        guidance: Some(guidance),
        implementation_fingerprint: env!("CARGO_PKG_VERSION").into(),
        enabled_by_default: true,
        project_wide: false,
        custom: false,
    }
}

pub(crate) fn with_custom(custom: &[CustomRule]) -> Result<Vec<RuleMetadata>, String> {
    let grammar = RulesCodeGrammar;
    let mut result = catalogue();
    for item in custom {
        if !grammar.rule_code_is_exact(&item.code) || !item.code.starts_with("XSQBR") {
            return Err(format!("invalid rule code: {}", item.code));
        }
        result.push(RuleMetadata {
            code: item.code.clone(),
            family: item.family.clone(),
            slug: item.slug.clone(),
            message: item.message.clone(),
            remediation: item.remediation.clone(),
            guidance: None,
            implementation_fingerprint: item.implementation_fingerprint.clone(),
            enabled_by_default: item.enabled_by_default,
            project_wide: item.project_wide,
            custom: true,
        });
    }
    result.sort_by(|a, b| a.code.cmp(&b.code));
    for pair in result.windows(2) {
        if pair[0].code == pair[1].code {
            return Err(format!("duplicate rule codes: {}", pair[0].code));
        }
    }
    Ok(result)
}

pub(crate) fn select<'a>(
    catalogue: &'a [RuleMetadata],
    selected: &[String],
    ignored: &[String],
) -> Result<Vec<&'a RuleMetadata>, String> {
    let grammar = RulesCodeGrammar;
    let references: Vec<&RuleMetadata> = catalogue.iter().collect();
    let configured = PolicySelectors {
        select: selected.to_vec(),
        warn: Vec::new(),
        ignore: Vec::new(),
    };
    let _ = resolve_policy(&references, &(), &configured, &grammar).map_err(rules_error)?;
    let (mut effective_select, custom_selected) =
        activate_explicit_custom_matches(catalogue, selected, &grammar);
    if custom_selected
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
        .map(|ruleset| ruleset.blocking)
        .map_err(rules_error)
}

fn activate_explicit_custom_matches(
    catalogue: &[RuleMetadata],
    selected: &[String],
    grammar: &RulesCodeGrammar,
) -> (Vec<String>, bool) {
    let mut effective = selected.to_vec();
    let mut custom_selected = false;
    for rule in catalogue {
        if !rule.custom {
            continue;
        }
        for selector in selected {
            if !grammar.code_matches_selector(&rule.code, selector) {
                continue;
            }
            custom_selected = true;
            if !effective.contains(&rule.code) {
                effective.push(rule.code.clone());
            }
        }
    }
    (effective, custom_selected)
}

pub(crate) fn selected_codes_json(request_json: &str) -> Result<String, String> {
    let request: ResolveRulesRequest = serde_json::from_str(request_json)
        .map_err(|error| format!("invalid rules request: {error}"))?;
    if request.version != API_VERSION {
        return Err(format!(
            "unsupported rules native API version {}; expected {API_VERSION}",
            request.version
        ));
    }
    crate::configuration::main::validate::validate(&request.config)?;
    let rules = with_custom(&request.custom_rules)?;
    let selected = select(&rules, &request.config.select, &request.config.ignore)?;
    let codes: Vec<&str> = selected.iter().map(|rule| rule.code.as_str()).collect();
    serde_json::to_string(&codes).map_err(|error| error.to_string())
}

fn rules_error(error: PolicyError) -> String {
    match error {
        PolicyError::InvalidSelector { selector, .. } => {
            format!("malformed rule selector: {selector}")
        }
        PolicyError::SelectorMatchesNoConfiguredRule { selector, .. } => {
            format!("rule selector matches no rules: {selector}")
        }
        other => format!("invalid rules: {other}"),
    }
}

pub(crate) fn fingerprint(
    rules: &[&RuleMetadata],
    config: &crate::models::RulesConfig,
    dialect: &str,
) -> Result<String, String> {
    let payload = serde_json::to_vec(&(rules, config, dialect)).map_err(|e| e.to_string())?;
    Ok(format!("{:x}", Sha256::digest(payload)))
}
