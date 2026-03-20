"""Adaptive polling logic — time-based tiered backoff, no sleep/threading."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

# Default initial interval
INTERVAL_ACTIVE = 30  # seconds — after finding work

# Backoff tiers: (interval_seconds, duration_seconds)
# Each tier stays for its duration before promoting to the next.
# The last tier stays forever (duration is ignored).
DEFAULT_TIERS: list[tuple[float, float]] = [
    (30, 300),   # 30s interval for 5 minutes
    (60, 300),   # 60s interval for 5 minutes
    (300, 300),  # 5min interval for 5 minutes
    (900, 0),    # 15min interval — permanent
]


class AdaptivePoller:
    """Calculates poll intervals using time-based tiered backoff.

    Each tier has an interval and a duration. The poller stays at a tier
    for the specified duration (wall-clock time), then promotes to the next.
    The last tier is permanent. ``work_found()`` resets to tier 0.
    """

    def __init__(
        self,
        initial_interval: float = INTERVAL_ACTIVE,
        tiers: Sequence[tuple[float, float]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._tiers = tiers or DEFAULT_TIERS
        # Override the first tier's interval with initial_interval
        self._tiers = [
            (initial_interval, self._tiers[0][1]),
            *self._tiers[1:],
        ]
        self._clock = clock
        self._tier_index = 0
        self._tier_entered_at = self._clock()

    @property
    def current_interval(self) -> float:
        self._maybe_promote()
        return self._tiers[self._tier_index][0]

    @property
    def tier_index(self) -> int:
        self._maybe_promote()
        return self._tier_index

    def work_found(self) -> None:
        """Reset to tier 0 after finding work."""
        self._tier_index = 0
        self._tier_entered_at = self._clock()

    def no_work_found(self) -> None:
        """Called after an empty poll — promotes tier if duration elapsed."""
        self._maybe_promote()

    def _maybe_promote(self) -> None:
        """Promote to the next tier if the current tier's duration has elapsed."""
        while self._tier_index < len(self._tiers) - 1:
            _, duration = self._tiers[self._tier_index]
            elapsed = self._clock() - self._tier_entered_at
            if elapsed < duration:
                break
            self._tier_index += 1
            self._tier_entered_at += duration
