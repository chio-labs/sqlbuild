from dataclasses import dataclass, field


@dataclass(frozen=True)
class DefaultBranchDetectionTestCase:
    description: str
    init_branch: str | None
    extra_branches: tuple[str, ...] = field(default_factory=tuple)
    set_remote_head_to: str | None = None
    is_git_repo: bool = True
    expected_ref: str = "main"
