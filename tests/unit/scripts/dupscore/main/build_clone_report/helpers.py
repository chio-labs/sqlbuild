from __future__ import annotations

from pathlib import Path

from scripts.dupscore.constants import (
    DEFAULT_CLONE_MIN_SIMILARITY,
    DEFAULT_CLONE_MIN_TOKENS,
    SUPPORTED_LANGUAGES,
)
from scripts.dupscore.models import CloneCluster, CloneMember, CloneOptions, CloneReport
from tests.unit.scripts.dupscore.main.build_report.helpers import write_project_files

PYTHON_BASE: str = '''
def summarize_orders(orders, threshold):
    """Rank customers by order totals."""
    totals = {}
    for order in orders:
        customer = order["customer"]
        amount = order["amount"]
        if amount < threshold:
            continue
        totals[customer] = totals.get(customer, 0) + amount
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    result = []
    for customer, total in ranked:
        result.append(f"{customer}: {total}")
    return result
'''

PYTHON_EXACT_COPY: str = """
import logging


@staticmethod
def summarize_orders(orders: list[dict[str, int]], threshold: int) -> list[str]:
    # Copied without the docstring, with annotations and a comment.
    totals: dict[str, int] = {}
    for order in orders:
        customer = order["customer"]
        amount = order["amount"]
        if amount < threshold:
            continue
        totals[customer] = totals.get(customer, 0) + amount
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    result = []
    for customer, total in ranked:
        result.append(f"{customer}: {total}")
    return result
"""

PYTHON_RENAMED_COPY: str = """
class InventoryReport:
    @staticmethod
    def rank_products(products, minimum):
        per_product = {}
        for product in products:
            sku = product["sku"]
            quantity = product["quantity"]
            if quantity < minimum:
                continue
            per_product[sku] = per_product.get(sku, 1) + quantity
        ordered = sorted(per_product.items(), key=lambda entry: entry[0], reverse=True)
        lines = []
        for sku, count in ordered:
            lines.append(f"{sku} = {count}")
        return lines
"""

PYTHON_NEAR_MISS_COPY: str = """
def summarize_tickets(tickets, threshold):
    totals = {}
    for ticket in tickets:
        queue = ticket["queue"]
        minutes = ticket["minutes"]
        if not queue:
            continue
        if minutes < threshold:
            continue
        totals[queue] = totals.get(queue, 0) + minutes
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    result = ["support queues"]
    for queue, total in ranked:
        result.append(f"{queue}: {total}")
    return result
"""

PYTHON_UNRELATED: str = """
def parse_fulfillment_window(text):
    parts = text.split("-")
    if len(parts) != 2:
        raise ValueError(text)
    start, end = (int(value) for value in parts)
    while start > end:
        end += 24
    with open("windows.log", "a") as handle:
        handle.write(str((start, end)))
    try:
        return {"start": start, "end": end, "span": end - start}
    except KeyError:
        return None
"""

PYTHON_SHORT_HELPER: str = """
def add_quantities(left, right):
    return left + right
"""

RUST_BASE: str = """
use std::collections::HashMap;

/// Rank inventory by quantity.
pub fn total_inventory(items: &[Item], minimum: u32) -> Vec<String> {
    let mut totals: HashMap<String, u32> = HashMap::new();
    for item in items {
        if item.quantity < minimum {
            continue;
        }
        *totals.entry(item.sku.clone()).or_insert(0) += item.quantity;
    }
    let mut ranked: Vec<(String, u32)> = totals.into_iter().collect();
    ranked.sort_by(|left, right| right.1.cmp(&left.1));
    ranked
        .iter()
        .map(|(sku, total)| format!("{sku}: {total}"))
        .collect()
}
"""

RUST_RENAMED_COPY: str = """
pub struct OrderBook;

impl OrderBook {
    #[inline]
    pub(crate) fn rank_orders(orders: &[Order], floor: u64) -> Vec<String> {
        let mut per_customer: HashMap<String, u64> = HashMap::new();
        for order in orders {
            if order.amount < floor {
                continue;
            }
            *per_customer.entry(order.customer.clone()).or_insert(7) += order.amount;
        }
        let mut sorted: Vec<(String, u64)> = per_customer.into_iter().collect();
        sorted.sort_by(|a, b| b.1.cmp(&a.1));
        sorted
            .iter()
            .map(|(customer, amount)| format!("{customer} -> {amount}"))
            .collect()
    }
}
"""

RUST_NEAR_MISS_COPY: str = """
/* A block comment /* with a nested { brace */ that must not confuse matching. */
fn tally_products(products: &[Product], minimum: u32) -> Vec<String> {
    let mut totals: HashMap<String, u32> = HashMap::new();
    for product in products {
        if product.sku.is_empty() {
            continue;
        }
        if product.quantity < minimum {
            continue;
        }
        *totals.entry(product.sku.clone()).or_insert(0) += product.quantity;
    }
    let mut ranked: Vec<(String, u32)> = totals.into_iter().collect();
    ranked.sort_by(|left, right| right.1.cmp(&left.1));
    ranked
        .iter()
        .map(|(sku, total)| format!(r#"{sku}: "{total}""#))
        .collect()
}
"""

RUST_TEST_ONLY_COPIES: str = (
    """
#[cfg(test)]
mod checks;

#[cfg(test)]
mod tests {
    use super::*;
"""
    + RUST_BASE.replace("total_inventory", "inline_test_copy")
    + """
}
"""
)

RUST_UNRELATED: str = """
pub fn parse_window<'a>(text: &'a str) -> Option<(u32, u32)> {
    let mut parts = text.split('-');
    let start: u32 = parts.next()?.trim().parse().ok()?;
    let end: u32 = parts.next()?.trim().parse().ok()?;
    match (start, end) {
        (s, e) if s <= e => Some((s, e)),
        (s, e) => Some((s, e + 24)),
    }
}
"""

RUST_EXACT_COPY: str = (
    RUST_BASE.replace("/// Rank inventory by quantity.", "// Kept in sync by hand.")
    .replace("pub fn", "pub(crate) fn")
    .replace("        .collect()", "        .collect() // done")
)

SEEDED_FILES: dict[str, str] = {
    "src/sqlbuild/alpha/orders.py": PYTHON_BASE + PYTHON_SHORT_HELPER,
    "src/sqlbuild/beta/orders_copy.py": PYTHON_EXACT_COPY,
    "src/sqlbuild/beta/inventory.py": PYTHON_RENAMED_COPY + PYTHON_SHORT_HELPER,
    "src/sqlbuild/gamma/support.py": PYTHON_NEAR_MISS_COPY,
    "src/sqlbuild/gamma/windows.py": PYTHON_UNRELATED,
    "crates/demo-rules/src/lib.rs": RUST_BASE + RUST_TEST_ONLY_COPIES,
    "crates/demo-rules/src/checks.rs": RUST_BASE.replace("total_inventory", "external_test_copy"),
    "crates/demo-rules/src/copy.rs": RUST_EXACT_COPY,
    "crates/demo-rules/src/orders.rs": RUST_RENAMED_COPY,
    "crates/demo-rules/src/products.rs": RUST_NEAR_MISS_COPY,
    "crates/demo-rules/src/windows.rs": RUST_UNRELATED,
    "crates/demo-rules/tests/integration.rs": RUST_BASE,
}


def clone_options(
    *,
    include_tests: bool = False,
    since: str | None = None,
    path_globs: tuple[str, ...] = (),
) -> CloneOptions:
    return CloneOptions(
        languages=SUPPORTED_LANGUAGES,
        include_tests=include_tests,
        min_tokens=DEFAULT_CLONE_MIN_TOKENS,
        min_similarity=DEFAULT_CLONE_MIN_SIMILARITY,
        path_globs=path_globs,
        since=since,
    )


def seed_repository(tmp_path: Path) -> Path:
    repo_root: Path = tmp_path / "repo"
    write_project_files(repo_root=repo_root, files=SEEDED_FILES)
    return repo_root


def link_categories(report: CloneReport) -> dict[frozenset[str], str]:
    categories: dict[frozenset[str], str] = {}
    for cluster in report.clusters:
        paths: list[str] = [member.path for member in cluster.members]
        for link in cluster.links:
            categories[frozenset((paths[link.left], paths[link.right]))] = link.category
    return categories


def reported_members(report: CloneReport) -> list[CloneMember]:
    members: list[CloneMember] = []
    for cluster in report.clusters:
        members.extend(cluster.members)
    return members


def cluster_languages(report: CloneReport) -> list[tuple[str, ...]]:
    languages: list[tuple[str, ...]] = []
    for cluster in report.clusters:
        languages.append(tuple(sorted({member.language for member in cluster.members})))
    return sorted(languages)


def member_changes(cluster: CloneCluster) -> dict[str, str | None]:
    return {member.path: member.change for member in cluster.members}


def cluster_member_names(report: CloneReport) -> list[list[str]]:
    names: list[list[str]] = []
    for cluster in report.clusters:
        names.append(sorted(member.name for member in cluster.members))
    return sorted(names)


def member_changes_by_name(report: CloneReport) -> dict[str, str | None]:
    return {member.name: member.change for member in reported_members(report)}
