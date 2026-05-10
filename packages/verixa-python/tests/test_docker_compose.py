"""pytest suite for deploy/docker-compose/docker-compose.yml.

Validates structural invariants on the compose file so CP-2.3 has real
test coverage (the 100pct discipline applies to every code+config artefact
that ships in the repo).

Coverage of the YAML *as a configuration artefact*:
  - File parses as valid YAML
  - All services declare a healthcheck
  - All services join the verixa-net network
  - All required services are present
  - Port mappings have no host-side collisions
  - Prometheus config references the same services that compose declares
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest
import yaml

# ---------------------------------------------------------------------------
# Locate compose file relative to this test (no env var indirection)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PATH = REPO_ROOT / "deploy" / "docker-compose" / "docker-compose.yml"
PROMETHEUS_PATH = (
    REPO_ROOT / "deploy" / "docker-compose" / "prometheus" / "prometheus.yml"
)

REQUIRED_SERVICES: tuple[str, ...] = (
    "postgres",
    "redis",
    "opa",
    "vault",
    "minio",
    "prometheus",
)

EXPECTED_NETWORK = "verixa-net"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def compose_doc() -> dict[str, Any]:
    assert COMPOSE_PATH.is_file(), f"compose file not found at {COMPOSE_PATH}"
    with COMPOSE_PATH.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    assert isinstance(doc, dict), "compose root must be a mapping"
    return doc


@pytest.fixture(scope="module")
def prometheus_doc() -> dict[str, Any]:
    assert PROMETHEUS_PATH.is_file(), f"prometheus.yml not found at {PROMETHEUS_PATH}"
    with PROMETHEUS_PATH.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    assert isinstance(doc, dict), "prometheus.yml root must be a mapping"
    return doc


# ---------------------------------------------------------------------------
# Top-level structure
# ---------------------------------------------------------------------------


def test_compose_has_top_level_keys(compose_doc: dict[str, Any]) -> None:
    assert "services" in compose_doc
    assert "networks" in compose_doc
    assert "volumes" in compose_doc
    assert compose_doc.get("name") == "verixa-dev"


def test_compose_declares_named_network(compose_doc: dict[str, Any]) -> None:
    networks = compose_doc["networks"]
    assert EXPECTED_NETWORK in networks
    assert networks[EXPECTED_NETWORK]["driver"] == "bridge"


# ---------------------------------------------------------------------------
# Required services present
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("service_name", REQUIRED_SERVICES)
def test_each_required_service_is_declared(
    compose_doc: dict[str, Any], service_name: str
) -> None:
    assert service_name in compose_doc["services"], (
        f"service {service_name} missing from docker-compose.yml"
    )


# ---------------------------------------------------------------------------
# Healthchecks on every service
# ---------------------------------------------------------------------------


def test_every_service_has_a_healthcheck(compose_doc: dict[str, Any]) -> None:
    services = compose_doc["services"]
    missing = [
        name for name, spec in services.items() if "healthcheck" not in spec
    ]
    assert not missing, f"services missing healthcheck: {missing}"


@pytest.mark.parametrize("service_name", REQUIRED_SERVICES)
def test_healthcheck_has_test_command(
    compose_doc: dict[str, Any], service_name: str
) -> None:
    hc = compose_doc["services"][service_name]["healthcheck"]
    assert "test" in hc, f"{service_name} healthcheck missing 'test' key"
    assert isinstance(hc["test"], list)
    assert len(hc["test"]) >= 2  # CMD/CMD-SHELL plus the actual command


# ---------------------------------------------------------------------------
# Network membership
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("service_name", REQUIRED_SERVICES)
def test_each_service_joins_verixa_net(
    compose_doc: dict[str, Any], service_name: str
) -> None:
    spec = compose_doc["services"][service_name]
    assert "networks" in spec, f"{service_name} not connected to any network"
    assert EXPECTED_NETWORK in spec["networks"], (
        f"{service_name} not on {EXPECTED_NETWORK}"
    )


# ---------------------------------------------------------------------------
# Port mappings — no host-side collisions
# ---------------------------------------------------------------------------


def _host_port_from_mapping(mapping: str) -> int:
    """Extract host port from a 'HOST:CONTAINER' or 'HOST:CONTAINER/proto' string."""
    # Compose ports are strings like "5432:5432" or "9000:9000"
    match = re.match(r"^(\d+):", mapping)
    assert match, f"invalid port mapping: {mapping}"
    return int(match.group(1))


def _iter_host_ports(services: dict[str, Any]) -> Iterable[tuple[str, int]]:
    for name, spec in services.items():
        for port_mapping in spec.get("ports", []) or []:
            yield name, _host_port_from_mapping(str(port_mapping))


def test_no_host_port_collisions(compose_doc: dict[str, Any]) -> None:
    seen: dict[int, str] = {}
    for service, port in _iter_host_ports(compose_doc["services"]):
        assert port not in seen, (
            f"host port {port} declared by both {seen[port]} and {service}"
        )
        seen[port] = service


# ---------------------------------------------------------------------------
# Volumes used by services are declared at top level
# ---------------------------------------------------------------------------


def test_named_volumes_are_declared(compose_doc: dict[str, Any]) -> None:
    declared = set(compose_doc.get("volumes", {}).keys())
    used: set[str] = set()
    for spec in compose_doc["services"].values():
        for vol in spec.get("volumes", []) or []:
            v = str(vol)
            # Bind mounts start with . or / ; named volumes don't
            if not v.startswith((".", "/")):
                # Named volume; first segment before ':' is the volume name
                used.add(v.split(":", 1)[0])
    missing = used - declared
    assert not missing, f"used but not declared: {missing}"


# ---------------------------------------------------------------------------
# Prometheus config references services that exist
# ---------------------------------------------------------------------------


def test_prometheus_config_is_valid_yaml(prometheus_doc: dict[str, Any]) -> None:
    assert "global" in prometheus_doc
    assert "scrape_configs" in prometheus_doc
    assert isinstance(prometheus_doc["scrape_configs"], list)
    assert len(prometheus_doc["scrape_configs"]) >= 1


def test_prometheus_scrape_jobs_are_well_formed(
    prometheus_doc: dict[str, Any],
) -> None:
    for job in prometheus_doc["scrape_configs"]:
        assert "job_name" in job
        assert "static_configs" in job
        for sc in job["static_configs"]:
            assert "targets" in sc
            assert isinstance(sc["targets"], list)
            assert len(sc["targets"]) >= 1


def test_prometheus_opa_target_matches_compose_service(
    prometheus_doc: dict[str, Any], compose_doc: dict[str, Any]
) -> None:
    """The OPA scrape job uses dns name 'opa' which must match the service name."""
    for job in prometheus_doc["scrape_configs"]:
        if job["job_name"] == "opa":
            targets = job["static_configs"][0]["targets"]
            for target in targets:
                # Expect host portion to be 'opa' (compose service DNS)
                host = target.split(":")[0]
                assert host in compose_doc["services"], (
                    f"prometheus targets host {host!r} which is not a "
                    f"declared compose service"
                )
            break
    else:
        pytest.fail("prometheus.yml missing 'opa' scrape job")
