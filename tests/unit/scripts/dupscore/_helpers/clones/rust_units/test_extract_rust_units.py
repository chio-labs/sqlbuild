from __future__ import annotations

import pytest

from scripts.dupscore._helpers.clones.rust_units import extract_rust_units
from scripts.dupscore.models import RustFileUnits
from tests.unit.scripts.dupscore._helpers.clones.rust_units._test_types import (
    RustKeyTestCase,
    RustTestModuleTestCase,
    RustUnitsTestCase,
)

_IMPL_AND_TRAIT_SOURCE: str = """\
pub struct Inventory<T> { items: Vec<T> }

impl<T: Clone> Inventory<T> where T: Default {
    #[must_use]
    pub fn first(&self) -> Option<&T> {
        self.items.first()
    }
}

pub trait Fulfill {
    fn ship(&self) -> bool;
    fn describe(&self) -> String {
        String::from("pending")
    }
}

impl<'a> Fulfill for &'a Inventory<u8> {
    fn ship(&self) -> bool { true }
}

fn helper(pointer: fn(u8) -> u8) -> u8 {
    fn nested() -> u8 { 1 }
    pointer(nested())
}
"""

_BRACE_TRAPS_SOURCE: str = """\
fn braces() -> &'static str {
    let open = '{';
    let text = r#"}}} "{" }"#;
    /* } /* } */ } */
    let bytes = b"}";
    text
}

fn after() {}
"""

_TEST_ITEMS_SOURCE: str = """\
fn kept() {}

#[cfg(test)]
fn test_helper() {}

#[cfg(not(test))]
fn production_only() {}

#[cfg(test)]
mod tests {
    #[test]
    fn checks_orders() {}
}

#[tokio::test]
async fn async_check() {}

macro_rules! make_fn {
    () => { fn generated() {} };
}
"""


@pytest.mark.parametrize(
    "test_case",
    [
        RustUnitsTestCase(
            description="impl and trait methods are qualified and bodiless decls skipped",
            source=_IMPL_AND_TRAIT_SOURCE,
            include_tests=False,
            expected_units=(
                ("Inventory::first", 5, 7),
                ("Fulfill::describe", 12, 14),
                ("Inventory::ship", 18, 18),
                ("helper", 21, 24),
            ),
        ),
        RustUnitsTestCase(
            description="braces inside chars, raw strings, comments, and bytes are ignored",
            source=_BRACE_TRAPS_SOURCE,
            include_tests=False,
            expected_units=(("braces", 1, 7), ("after", 9, 9)),
        ),
        RustUnitsTestCase(
            description="cfg(test) items, test functions, and macro bodies are skipped",
            source=_TEST_ITEMS_SOURCE,
            include_tests=False,
            expected_units=(("kept", 1, 1), ("production_only", 7, 7)),
        ),
        RustUnitsTestCase(
            description="include-tests keeps test items",
            source=_TEST_ITEMS_SOURCE,
            include_tests=True,
            expected_units=(
                ("kept", 1, 1),
                ("test_helper", 4, 4),
                ("production_only", 7, 7),
                ("checks_orders", 12, 12),
                ("async_check", 16, 16),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rust_source_when_extracting_units_then_returns_fn_items(
    test_case: RustUnitsTestCase,
) -> None:
    extracted: RustFileUnits = extract_rust_units(
        relative_path="crates/demo/src/lib.rs",
        source=test_case.source,
        include_tests=test_case.include_tests,
    )

    assert (
        tuple((unit.name, unit.start_line, unit.end_line) for unit in extracted.units)
        == test_case.expected_units
    )


@pytest.mark.parametrize(
    "test_case",
    [
        RustTestModuleTestCase(
            description="module root declares sibling test module",
            relative_path="crates/demo/src/engine/mod.rs",
            source="#[cfg(test)]\nmod tests;\nmod kept;\n",
            expected_prefixes=(
                "crates/demo/src/engine/tests.rs",
                "crates/demo/src/engine/tests/",
            ),
        ),
        RustTestModuleTestCase(
            description="non-root file declares nested test module",
            relative_path="crates/demo/src/engine.rs",
            source="#[cfg(test)]\nmod checks;\n",
            expected_prefixes=(
                "crates/demo/src/engine/checks.rs",
                "crates/demo/src/engine/checks/",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cfg_test_module_declaration_when_extracting_then_reports_test_paths(
    test_case: RustTestModuleTestCase,
) -> None:
    extracted: RustFileUnits = extract_rust_units(
        relative_path=test_case.relative_path,
        source=test_case.source,
        include_tests=False,
    )

    assert extracted.test_module_prefixes == test_case.expected_prefixes


@pytest.mark.parametrize(
    "test_case",
    [
        RustKeyTestCase(
            description="renamed identifiers, literals, and visibility share the normalised stream",
            left_source='fn count_orders(x: u8) -> u8 { let y = x + 1; println!("{y}"); y }',
            right_source='pub fn tally(value: u16) -> u16 { let n = value + 9; println!("n"); n }',
            expected_same_concrete=False,
            expected_same_normalized=True,
        ),
        RustKeyTestCase(
            description="different macros keep distinct normalised streams",
            left_source='fn f(x: u8) { println!("{x}"); }',
            right_source='fn f(x: u8) { print!("{x}"); }',
            expected_same_concrete=False,
            expected_same_normalized=False,
        ),
        RustKeyTestCase(
            description="different called functions keep distinct normalised streams",
            left_source="fn f(x: u8) -> u8 { load(x) }",
            right_source="fn f(x: u8) -> u8 { save(x) }",
            expected_same_concrete=False,
            expected_same_normalized=False,
        ),
        RustKeyTestCase(
            description="different called methods keep distinct normalised streams",
            left_source="fn f(x: &str) -> usize { x.len() }",
            right_source="fn f(x: &str) -> usize { x.count() }",
            expected_same_concrete=False,
            expected_same_normalized=False,
        ),
        RustKeyTestCase(
            description="field reads and receivers stay abstracted",
            left_source="fn f(order: &Order) -> u8 { order.total(order.count) }",
            right_source="fn g(item: &Item) -> u8 { item.total(item.size) }",
            expected_same_concrete=False,
            expected_same_normalized=True,
        ),
        RustKeyTestCase(
            description="comments and attributes do not change identity",
            left_source="fn f(x: u8) -> u8 { x /* note */ }",
            right_source="#[inline]\npub(crate) fn f(x: u8) -> u8 {\n    // note\n    x\n}",
            expected_same_concrete=True,
            expected_same_normalized=True,
        ),
        RustKeyTestCase(
            description="char and string literals keep distinct placeholders",
            left_source="fn f() -> char { 'x' }",
            right_source='fn f() -> char { "x" }',
            expected_same_concrete=False,
            expected_same_normalized=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_two_rust_functions_when_extracting_then_identity_keys_reflect_normalisation(
    test_case: RustKeyTestCase,
) -> None:
    left: RustFileUnits = extract_rust_units(
        relative_path="crates/demo/src/a.rs", source=test_case.left_source, include_tests=False
    )
    right: RustFileUnits = extract_rust_units(
        relative_path="crates/demo/src/b.rs", source=test_case.right_source, include_tests=False
    )

    assert (
        left.units[0].concrete_key == right.units[0].concrete_key
    ) is test_case.expected_same_concrete
    assert (
        left.units[0].normalized_key == right.units[0].normalized_key
    ) is test_case.expected_same_normalized
