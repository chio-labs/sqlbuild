"""Custom rules used by public harness tests."""

from sqlbuild.rules import Finding, Model, RuleContext, RuleOption, rule

REQUIRED_DOMAIN: RuleOption[str] = RuleOption.string(
    name="required_domain",
    default="commerce",
    description="Domain that models must belong to.",
)


@rule(
    code="XSQBRD001",
    slug="required-domain",
    message="model belongs to the wrong domain",
    remediation="Move this model beneath models/<required-domain>/ and rename its domain prefix.",
    options=(REQUIRED_DOMAIN,),
)
def required_domain(*, model: Model, ctx: RuleContext) -> list[Finding]:
    matches: bool = model.name.startswith(f"{ctx.option(REQUIRED_DOMAIN)}__")
    return [ctx.finding(subject=model)] * int(not matches)
