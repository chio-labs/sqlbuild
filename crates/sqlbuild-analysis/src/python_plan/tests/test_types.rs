pub(crate) struct OrderTestCase {
    pub(crate) description: &'static str,
    pub(crate) selected: &'static [&'static str],
    pub(crate) upstream: &'static [(&'static str, &'static [&'static str])],
    pub(crate) expected_order: &'static [&'static str],
}

pub(crate) struct ClosureTestCase {
    pub(crate) description: &'static str,
    pub(crate) start: &'static str,
    pub(crate) upstream: &'static [(&'static str, &'static [&'static str])],
    pub(crate) expected_closure: &'static [&'static str],
}
