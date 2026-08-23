"""Custom rules used by public harness tests."""

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.kata import KataFault, RuleContext, RuleOption, kata
from sqlbuild.kata_engine.models import ModelNameParts

REQUIRED_DOMAIN: RuleOption[str] = RuleOption.string(
    name="required_domain",
    default="market",
    description="Domain that models must belong to.",
)


@kata(
    code="XSQBKD001",
    family="project",
    slug="required-domain",
    message="model belongs to the wrong domain",
    remediation="Move this model beneath models/<required-domain>/ and rename its domain prefix.",
    options=(REQUIRED_DOMAIN,),
)
def required_domain(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    parts: ModelNameParts | None = ctx.name_parts
    matches: bool = parts is not None and parts.domain == ctx.option(REQUIRED_DOMAIN)
    return [ctx.path_fault()] * int(not matches)
