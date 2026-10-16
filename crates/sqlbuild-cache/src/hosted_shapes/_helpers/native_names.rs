//! Every hosted Python shape name with the one native class hosting it, indexed once.

use std::sync::LazyLock;

use rustc_hash::FxHashMap;

use crate::hosted_shapes::constants::{HOSTED_SHAPE_TYPES, NATIVE_MODULE};
use crate::hosted_shapes::errors::AmbiguousShapeName;

static NATIVE_NAMES: LazyLock<FxHashMap<(&'static str, &'static str), Option<&'static str>>> =
    LazyLock::new(|| {
        let mut index = FxHashMap::default();
        for (native, python) in HOSTED_SHAPE_TYPES {
            let Some(shape) = python.split_once(':') else {
                continue;
            };
            let Some(native_name) = native
                .strip_prefix(NATIVE_MODULE)
                .and_then(|rest| rest.strip_prefix(':'))
            else {
                continue;
            };
            index
                .entry(shape)
                .and_modify(|found: &mut Option<&'static str>| {
                    if found.is_some_and(|existing| existing != native_name) {
                        *found = None;
                    }
                })
                .or_insert(Some(native_name));
        }
        index
    });

/// The native class hosting `module:class`, an ambiguity, or `None` when no native class hosts it.
pub(crate) fn native_name(
    module: &str,
    class: &str,
) -> Option<Result<&'static str, AmbiguousShapeName>> {
    NATIVE_NAMES
        .get(&(module, class))
        .map(|found| found.ok_or(AmbiguousShapeName))
}
