"""Adaptive polling logic — purely computational, no sleep/threading."""

from __future__ import annotations

# Interval thresholds
INTERVAL_ACTIVE = 60  # seconds — after finding work
INTERVAL_IDLE_3 = 300  # 5 minutes — after 3 consecutive empty polls
INTERVAL_IDLE_10 = 900  # 15 minutes — after 10 consecutive empty polls


class AdaptivePoller:
    """Calculates poll intervals based on consecutive empty polls."""

    def __init__(self, initial_interval: float = INTERVAL_ACTIVE) -> None:
        self._initial_interval = initial_interval
        self._consecutive_empty = 0
        self._current_interval = initial_interval

    @property
    def current_interval(self) -> float:
        return self._current_interval

    @property
    def consecutive_empty(self) -> int:
        return self._consecutive_empty

    def work_found(self) -> None:
        """Reset to active interval after finding work."""
        self._consecutive_empty = 0
        self._current_interval = self._initial_interval

    def no_work_found(self) -> None:
        """Increment empty count and recalculate interval."""
        self._consecutive_empty += 1
        self._recalculate()

    def _recalculate(self) -> None:
        if self._consecutive_empty >= 10:
            self._current_interval = INTERVAL_IDLE_10
        elif self._consecutive_empty >= 3:
            self._current_interval = INTERVAL_IDLE_3
        else:
            self._current_interval = self._initial_interval
