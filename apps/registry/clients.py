"""Clients for the external deforestation-risk registry.

The real registry is slow (seconds to tens of seconds) and has outages lasting hours, so it is
only ever called from the Celery worker, never from a request/response cycle.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from django.conf import settings


class RegistryError(Exception):
    """Base class for transient registry failures that are worth retrying."""

    outcome: str = "error"


class RegistryUnavailable(RegistryError):
    """Registry answered with an error or refused the connection."""

    outcome = "error"


class RegistryTimeout(RegistryError):
    """Registry did not answer within REGISTRY_API_TIMEOUT seconds."""

    outcome = "timeout"


@dataclass(frozen=True)
class RiskAssessment:
    status: Literal["clear", "flagged"]
    reference: str


class RiskRegistryClient(Protocol):
    def check_plot(self, *, plot_code: str, latitude: Decimal, longitude: Decimal) -> RiskAssessment: ...


class SimulatedRiskRegistry:
    """Stand-in for the registry with realistic latency, outages and timeouts."""

    def __init__(
        self,
        *,
        min_latency: float,
        max_latency: float,
        failure_rate: float,
        flag_rate: float,
        timeout: float,
        rng: random.Random | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_latency = min_latency
        self.max_latency = max(max_latency, min_latency)
        self.failure_rate = failure_rate
        self.flag_rate = flag_rate
        self.timeout = timeout
        self._rng = rng or random.Random()
        self._sleep = sleep

    def check_plot(self, *, plot_code: str, latitude: Decimal, longitude: Decimal) -> RiskAssessment:
        latency = self._rng.uniform(self.min_latency, self.max_latency)
        if latency > self.timeout:
            self._sleep(self.timeout)
            raise RegistryTimeout(f"registry did not answer within {self.timeout:.0f}s")
        self._sleep(latency)
        if self._rng.random() < self.failure_rate:
            raise RegistryUnavailable("registry returned 503 Service Unavailable")
        status: Literal["clear", "flagged"] = "flagged" if self._rng.random() < self.flag_rate else "clear"
        return RiskAssessment(status=status, reference=f"SIM-{plot_code}")


def get_registry_client() -> RiskRegistryClient:
    """Return the configured registry client.

    F1 ships only the simulator; a real HTTP client for REGISTRY_API_URL plugs in here.
    """
    return SimulatedRiskRegistry(
        min_latency=settings.RISK_REGISTRY_MIN_LATENCY,
        max_latency=settings.RISK_REGISTRY_MAX_LATENCY,
        failure_rate=settings.RISK_REGISTRY_FAILURE_RATE,
        flag_rate=settings.RISK_REGISTRY_FLAG_RATE,
        timeout=settings.REGISTRY_API_TIMEOUT,
    )
