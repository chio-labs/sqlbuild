from __future__ import annotations

from scripts.dupscore.constants import CATEGORY_EXACT
from scripts.dupscore.models import CloneCluster, CloneMember, ClonePairLink, CloneReport

_MEMBER_NAMES: tuple[str, ...] = ("OrdersStore.write_orders", "BaseStore.write_orders")
_FIRST_MEMBER_LINE: int = 2


def report_with_members(forced_flags: tuple[bool, ...]) -> CloneReport:
    members: list[CloneMember] = []
    for position, (name, forced) in enumerate(zip(_MEMBER_NAMES, forced_flags, strict=True)):
        members.append(
            CloneMember(
                language="python",
                path="src/sqlbuild/demo/orders.py",
                name=name,
                start_line=1 + 10 * position,
                end_line=9 + 10 * position,
                tokens=80,
                change=None,
                forced_override=forced,
            )
        )
    cluster: CloneCluster = CloneCluster(
        category=CATEGORY_EXACT,
        similarity_min=1.0,
        similarity_max=1.0,
        duplicated_tokens=80,
        members=tuple(members),
        links=(ClonePairLink(left=0, right=1, similarity=1.0, category=CATEGORY_EXACT),),
    )
    return CloneReport(
        since=None,
        unit_counts={"python": 2},
        allowlisted_pairs=0,
        contract_exempt_members=0,
        clusters=(cluster,),
    )


def member_lines(text: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in text.splitlines()[_FIRST_MEMBER_LINE:])
