"""Tests for adaptive polling logic."""

from taskmanager.daemon.poller import (
    AdaptivePoller,
    INTERVAL_ACTIVE,
    INTERVAL_IDLE_3,
    INTERVAL_IDLE_10,
)


class TestAdaptivePoller:
    def test_initial_interval(self):
        p = AdaptivePoller()
        assert p.current_interval == INTERVAL_ACTIVE
        assert p.consecutive_empty == 0

    def test_custom_initial_interval(self):
        p = AdaptivePoller(initial_interval=30)
        assert p.current_interval == 30

    def test_work_found_resets(self):
        p = AdaptivePoller()
        for _ in range(5):
            p.no_work_found()
        assert p.current_interval == INTERVAL_IDLE_3

        p.work_found()
        assert p.current_interval == INTERVAL_ACTIVE
        assert p.consecutive_empty == 0

    def test_backoff_at_3(self):
        p = AdaptivePoller()
        for _ in range(3):
            p.no_work_found()
        assert p.current_interval == INTERVAL_IDLE_3

    def test_backoff_at_10(self):
        p = AdaptivePoller()
        for _ in range(10):
            p.no_work_found()
        assert p.current_interval == INTERVAL_IDLE_10

    def test_stays_at_max_backoff(self):
        p = AdaptivePoller()
        for _ in range(20):
            p.no_work_found()
        assert p.current_interval == INTERVAL_IDLE_10
        assert p.consecutive_empty == 20

    def test_below_3_stays_active(self):
        p = AdaptivePoller()
        p.no_work_found()
        assert p.current_interval == INTERVAL_ACTIVE
        p.no_work_found()
        assert p.current_interval == INTERVAL_ACTIVE

    def test_between_3_and_10(self):
        p = AdaptivePoller()
        for _ in range(7):
            p.no_work_found()
        assert p.current_interval == INTERVAL_IDLE_3
