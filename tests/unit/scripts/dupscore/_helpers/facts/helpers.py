from __future__ import annotations

from scripts.dupscore.models import ClassFact, FunctionFact, ProjectFacts


def find_function(*, facts: ProjectFacts, qualified_name: str) -> FunctionFact:
    functions: dict[str, FunctionFact] = {}
    for module in facts.modules:
        for function in module.functions:
            functions[function.qualified_name] = function
    return functions[qualified_name]


def find_class(*, facts: ProjectFacts, qualified_name: str) -> ClassFact:
    classes: dict[str, ClassFact] = {}
    for module in facts.modules:
        for class_fact in module.classes:
            classes[class_fact.qualified_name] = class_fact
    return classes[qualified_name]
