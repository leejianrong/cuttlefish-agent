from __future__ import annotations

import pytest

from cuttlefish.sandbox.container import ContainerSandboxProvider, DockerNotAvailableError


def test_raises_when_docker_binary_is_not_on_path() -> None:
    with pytest.raises(DockerNotAvailableError):
        ContainerSandboxProvider(docker_binary="docker-binary-that-does-not-exist")


@pytest.mark.requires_docker
def test_constructs_when_docker_binary_is_on_path() -> None:
    ContainerSandboxProvider()
