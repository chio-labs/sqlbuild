"""Run the failure corpus under one engine and report the codes each case really emits."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.compiler_differential._helpers.comparing.comparison import diagnostic_codes
from scripts.compiler_differential._helpers.corpus.corpus import build_corpus
from scripts.compiler_differential._helpers.running.execution import run_engine
from scripts.compiler_differential.constants import (
    CORPUS_FAILURES,
    ERROR_SEVERITY,
    EXPECT_SUCCESS,
    WARNING_SEVERITY,
)
from scripts.compiler_differential.models import (
    CorpusProject,
    DifferentialOptions,
    EmittedCodes,
    EngineRun,
)
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.compiler.resource_names.exceptions import ResourceIdentityError

_SOURCE_DIRECTORY: str = "source"


def emitted_failure_codes(*, options: DifferentialOptions) -> dict[str, EmittedCodes]:
    """Compile every failure case under the first engine and return its emitted codes by name."""

    corpus: list[CorpusProject] = build_corpus(
        repo_root=options.work_dir,
        corpora=(CORPUS_FAILURES,),
        seeds=range(0),
        dense_models=0,
        projects=(),
        project_expectation=EXPECT_SUCCESS,
    )
    with ThreadPoolExecutor(max_workers=options.jobs) as pool:
        emitted: list[EmittedCodes] = list(
            pool.map(lambda project: _emitted_codes(project=project, options=options), corpus)
        )
    return {project.name: codes for project, codes in zip(corpus, emitted, strict=True)}


def discovery_error_codes() -> frozenset[str]:
    """Return the code of every `DiscoveryError` subclass, walking the whole hierarchy."""

    _ = ResourceIdentityError
    codes: set[str] = set()
    pending: list[type[DiscoveryError]] = list(DiscoveryError.__subclasses__())
    while pending:
        error_class: type[DiscoveryError] = pending.pop()
        codes.add(str(error_class.code))
        pending.extend(error_class.__subclasses__())
    return frozenset(codes)


def _emitted_codes(*, project: CorpusProject, options: DifferentialOptions) -> EmittedCodes:
    case_dir: Path = options.work_dir / project.name.replace("/", "__")
    source_dir: Path = case_dir / _SOURCE_DIRECTORY
    if project.writer is not None:
        project.writer(source_dir)
    run: EngineRun = run_engine(
        project=project,
        source_dir=source_dir,
        case_dir=case_dir,
        engine=options.engines[0],
        options=options,
    )
    return EmittedCodes(
        errors=diagnostic_codes(outcome=run.outcomes[0], severity=ERROR_SEVERITY),
        warnings=diagnostic_codes(outcome=run.outcomes[0], severity=WARNING_SEVERITY),
    )
