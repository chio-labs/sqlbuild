use crate::compiler::models::{InterpolationRead, NestingFailure};
use crate::compiler::types::{CharSpan, InterpolationHost};
use std::collections::BTreeMap;

pub(crate) struct ModelHeaderTokenizationTestCase {
    pub(crate) description: &'static str,
    pub(crate) run: fn() -> bool,
    pub(crate) expected_success: bool,
}

pub(crate) struct ModelHeaderMatchTestCase {
    pub(crate) description: &'static str,
    pub(crate) contents: &'static str,
    pub(crate) expected_offsets: Option<(usize, usize, usize)>,
}

pub(crate) struct DeclarationReferenceScanTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    /// References spelled `kind:name[.member]@start..end, ...` in code points.
    pub(crate) expected_references: Option<&'static str>,
}

pub(crate) struct HeaderNestingTestCase {
    pub(crate) description: &'static str,
    /// The header is `prefix`, `open` repeated `depth` times, `1`, `close` as often, then `suffix`.
    pub(crate) prefix: &'static str,
    pub(crate) open: &'static str,
    pub(crate) close: &'static str,
    pub(crate) suffix: &'static str,
    pub(crate) depth: usize,
    /// The header position of the container past the limit; `None` when the header parses.
    pub(crate) expected_error_position: Option<usize>,
}

pub(crate) struct HeaderNestingLocationTestCase {
    pub(crate) description: &'static str,
    pub(crate) error: &'static str,
    pub(crate) header: &'static str,
    pub(crate) header_line: usize,
    pub(crate) expected_failure: Option<NestingFailure>,
}

pub(crate) struct InterpolationTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) context: bool,
    pub(crate) expected_sql: Result<&'static str, &'static str>,
}

pub(crate) struct InterpolationFactsTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_spans: Vec<CharSpan>,
    pub(crate) expected_reads: Vec<InterpolationRead>,
}

/// Variables, environment and context for interpolation tests.
pub(crate) struct MapHost {
    pub(crate) variables: BTreeMap<&'static str, Result<&'static str, &'static str>>,
    pub(crate) environment: BTreeMap<&'static str, &'static str>,
    pub(crate) context: Option<BTreeMap<&'static str, Option<&'static str>>>,
}

impl InterpolationHost for MapHost {
    fn variable(&self, name: &str) -> Option<Result<String, String>> {
        self.variables
            .get(name)
            .map(|value| value.map(str::to_owned).map_err(str::to_owned))
    }

    fn variable_names(&self) -> Vec<String> {
        self.variables
            .keys()
            .map(|name| (*name).to_owned())
            .collect()
    }

    fn environment(&self, name: &str) -> Result<Option<String>, String> {
        Ok(self.environment.get(name).map(|value| (*value).to_owned()))
    }

    fn context_allowed(&self) -> bool {
        self.context.is_some()
    }

    fn context(&self, name: &str) -> Option<Option<String>> {
        self.context
            .as_ref()?
            .get(name)
            .map(|value| value.map(str::to_owned))
    }

    fn context_names(&self) -> Vec<String> {
        self.context
            .iter()
            .flat_map(BTreeMap::keys)
            .map(|name| (*name).to_owned())
            .collect()
    }
}
