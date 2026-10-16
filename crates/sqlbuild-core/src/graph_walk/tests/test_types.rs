pub(super) type Rows = &'static [(&'static str, &'static [&'static str])];

pub(super) struct ReachTestCase {
    pub(super) description: &'static str,
    pub(super) edges: Rows,
    pub(super) starts: &'static [&'static str],
    pub(super) include_starts: bool,
    pub(super) max_depth: Option<u64>,
    pub(super) expected_order: Vec<&'static str>,
}

pub(super) struct PathTestCase {
    pub(super) description: &'static str,
    pub(super) edges: Rows,
    pub(super) endpoints: (&'static str, &'static str),
    pub(super) expected_nodes: Option<Vec<&'static str>>,
}

pub(super) struct GoalPathTestCase {
    pub(super) description: &'static str,
    pub(super) edges: Rows,
    pub(super) origin: &'static str,
    pub(super) goals: &'static [&'static str],
    pub(super) blocked: &'static [&'static str],
    pub(super) expected_path: Option<Vec<&'static str>>,
}

pub(super) struct KahnTestCase {
    pub(super) description: &'static str,
    pub(super) edges: Rows,
    pub(super) nodes: &'static [&'static str],
    pub(super) expected_order: Vec<&'static str>,
}

pub(super) struct OrderTestCase {
    pub(super) description: &'static str,
    pub(super) edges: Rows,
    pub(super) roots: &'static [&'static str],
    pub(super) expected_order: Vec<&'static str>,
}

pub(super) struct CycleTestCase {
    pub(super) description: &'static str,
    pub(super) edges: Rows,
    pub(super) roots: &'static [&'static str],
    pub(super) expected_cycle: Option<Vec<&'static str>>,
}
