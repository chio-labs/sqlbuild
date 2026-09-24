from __future__ import annotations

from scripts.dupscore._helpers.clones.tokens import build_clone_unit
from scripts.dupscore.models import CloneUnit, ContractExemptionEntry

CONTRACT_PATH: str = "src/sqlbuild/demo/contract/strict_store.py"
BASE_PATH: str = "src/sqlbuild/demo/contract/base_store.py"
ALPHA_PATH: str = "src/sqlbuild/demo/stores/alpha/classes/alpha_store.py"
BETA_PATH: str = "src/sqlbuild/demo/stores/beta/classes/beta_store.py"
GAMMA_PATH: str = "src/sqlbuild/demo/stores/gamma/classes/gamma_store.py"
CONNECTION_PATH: str = "src/sqlbuild/demo/stores/beta/classes/orders_connection.py"
OUTSIDE_PATH: str = "src/sqlbuild/demo/elsewhere/outside_store.py"
DELTA_PATH: str = "src/sqlbuild/demo/stores/delta/classes/delta_store.py"

_MIXIN_SOURCE: str = """\
from abc import abstractmethod


class ReaderMixin:
    @abstractmethod
    def read_orders(self, connection, keys):
        ...

    @abstractmethod
    def count_orders(self, connection):
        ...
"""

_CONTRACT_SOURCE: str = """\
import abc
from abc import abstractmethod

from sqlbuild.demo.contract.reader_mixin import ReaderMixin as Reader


class StrictStore(Reader):
    @abstractmethod
    def write_orders(self, connection, rows):
        ...

    @abc.abstractmethod
    def delete_orders(self, connection, keys):
        ...

    @property
    @abstractmethod
    def store_name(self):
        ...

    def count_orders(self, connection):
        return 0
"""

WRITE_ORDERS: str = """
    def write_orders(self, connection, rows):
        written = 0
        for row in rows:
            if row.get("status") == "cancelled":
                continue
            values = [row["order_id"], row["customer"], row["amount"]]
            connection.execute("INSERT INTO orders VALUES (?, ?, ?)", values)
            written += 1
        connection.commit()
        return written
"""

DELETE_ORDERS: str = """
    def delete_orders(self, connection, keys):
        pending = sorted(set(keys))
        while pending:
            batch = pending[:50]
            pending = pending[50:]
            placeholders = ", ".join("?" for _ in batch)
            try:
                connection.execute(f"DELETE FROM orders WHERE id IN ({placeholders})", batch)
            except KeyError as error:
                raise ValueError(str(error)) from error
        return len(keys)
"""

READ_ORDERS: str = """
    def read_orders(self, connection, keys):
        cursor = connection.cursor()
        results = {}
        with cursor:
            for key in keys:
                cursor.execute("SELECT * FROM orders WHERE id = ?", [key])
                fetched = cursor.fetchone()
                if fetched is None:
                    results[key] = None
                else:
                    results[key] = dict(zip(("id", "customer", "amount"), fetched))
        return results
"""

RENDER_ORDERS_SQL: str = """
    def _render_orders_sql(self, table, columns, predicates):
        selected = ", ".join(f'"{column}"' for column in columns) or "*"
        clauses = []
        for name, value in predicates.items():
            if value is None:
                clauses.append(f"{name} IS NULL")
            elif isinstance(value, (list, tuple)):
                clauses.append(f"{name} IN ({', '.join(repr(item) for item in value)})")
            else:
                clauses.append(f"{name} = {value!r}")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return f"SELECT {selected} FROM {table}{where}"
"""

_BASE_IMPORT: str = "from sqlbuild.demo.contract.base_store import BaseStore\n\n\n"

CONTRACT_FILES: dict[str, str] = {
    "src/sqlbuild/demo/contract/reader_mixin.py": _MIXIN_SOURCE,
    CONTRACT_PATH: _CONTRACT_SOURCE,
    BASE_PATH: (
        "from .strict_store import StrictStore\n\n\nclass BaseStore(StrictStore):\n" + WRITE_ORDERS
    ),
    ALPHA_PATH: (
        _BASE_IMPORT
        + "class AlphaStore(BaseStore):\n"
        + WRITE_ORDERS
        + DELETE_ORDERS
        + RENDER_ORDERS_SQL
        + "\n    def helper(self):\n        return 1\n"
    ),
    BETA_PATH: (
        _BASE_IMPORT
        + "class BetaStore(BaseStore):\n"
        + WRITE_ORDERS
        + READ_ORDERS
        + RENDER_ORDERS_SQL
    ),
    GAMMA_PATH: (
        "from sqlbuild.demo.stores.alpha.classes.alpha_store import AlphaStore\n\n\n"
        "class GammaStore(AlphaStore):\n" + DELETE_ORDERS
    ),
    CONNECTION_PATH: "class OrdersConnection:\n" + READ_ORDERS,
    OUTSIDE_PATH: (
        _BASE_IMPORT
        + "class OutsideStore(BaseStore):\n"
        + "    def write_orders(self, connection, rows):\n        return 0\n"
    ),
}

DELTA_FILES: dict[str, str] = {
    DELTA_PATH: (
        _BASE_IMPORT + "class DeltaStore(BaseStore):\n" + WRITE_ORDERS + RENDER_ORDERS_SQL
    ),
}

STORE_EXEMPTION: ContractExemptionEntry = ContractExemptionEntry(
    contract_path=CONTRACT_PATH,
    contract_class="StrictStore",
    paths=("src/sqlbuild/demo/contract/*", "src/sqlbuild/demo/stores/*/classes/*"),
    reason="Every store must define each StrictStore method itself.",
    forbidden_owners=((BASE_PATH, "BaseStore"),),
)


def method_unit(*, language: str, path: str, name: str) -> CloneUnit:
    return build_clone_unit(
        language=language,
        path=path,
        name=name,
        start_line=1,
        end_line=2,
        normalized=[],
        concrete=[],
    )
