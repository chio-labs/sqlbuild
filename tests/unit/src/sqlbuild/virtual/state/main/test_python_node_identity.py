from __future__ import annotations

import pytest

from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.python_nodes.models import PythonNodeIdentity
from sqlbuild.virtual.state.main.python_identities.python_node_identity_read import (
    read_virtual_python_identity_fingerprints,
)
from sqlbuild.virtual.state.main.python_identities.python_node_identity_write import (
    try_record_virtual_python_node_identity,
)
from tests.unit.src.sqlbuild.virtual.state.main._test_types import (
    VirtualPythonNodeIdentityTestCase,
)
from tests.unit.src.sqlbuild.virtual.state.main.helpers import (
    RecordingPythonIdentityStateBackend,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPythonNodeIdentityTestCase(
            description="writes and reads virtual python identity as fingerprint",
            virtual_environment_name="dev_alice",
            expected_node_type="task",
            expected_node_name="prepare_orders",
            expected_version_hash="version-hash",
            expected_definition_json='{"node_name":"prepare_orders"}',
            expected_metadata_json='{"dependencies":[]}',
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_python_identity_when_recording_then_reads_previous_fingerprint(
    test_case: VirtualPythonNodeIdentityTestCase,
) -> None:
    backend: RecordingPythonIdentityStateBackend = RecordingPythonIdentityStateBackend()
    identity: PythonNodeIdentity = PythonNodeIdentity(
        node_type=test_case.expected_node_type,
        node_name=test_case.expected_node_name,
        object_module="tasks.orders",
        object_qualname="prepare_orders",
        source_path="tasks/orders.py",
        source_hash="source-hash",
        definition_hash="definition-hash",
        version_hash=test_case.expected_version_hash,
        definition_json=test_case.expected_definition_json,
        metadata_json=test_case.expected_metadata_json,
    )

    try_record_virtual_python_node_identity(
        backend=backend,
        state_connection=None,
        schema="sqlbuild_state",
        virtual_environment_name=test_case.virtual_environment_name,
        identity=identity,
    )
    fingerprints: dict[tuple[str, str], Fingerprint] = read_virtual_python_identity_fingerprints(
        backend=backend,
        state_connection=None,
        schema="sqlbuild_state",
        virtual_environment_name=test_case.virtual_environment_name,
    )

    fingerprint: Fingerprint = fingerprints[
        (test_case.expected_node_type, test_case.expected_node_name)
    ]
    assert fingerprint.node_type == test_case.expected_node_type
    assert fingerprint.node_name == test_case.expected_node_name
    assert fingerprint.version_hash == test_case.expected_version_hash
    assert fingerprint.definition == test_case.expected_definition_json
    assert fingerprint.metadata_json == test_case.expected_metadata_json
