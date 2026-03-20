"""Tests for time-based tiered adaptive polling logic."""

from taskmanager.daemon.poller import AdaptivePoller, DEFAULT_TIERS, INTERVAL_ACTIVE


class FakeClock:
    """Injectable clock for deterministic tests."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# Smaller tiers for fast tests: (interval, duration)
TEST_TIERS = [
    (10, 100),  # tier 0: 10s interval, stays for 100s
    (20, 100),  # tier 1: 20s interval, stays for 100s
    (50, 100),  # tier 2: 50s interval, stays for 100s
    (120, 0),   # tier 3: 120s interval, permanent
]


class TestAdaptivePoller:
    def test_initial_interval(self):
        clock = FakeClock()
        p = AdaptivePoller(clock=clock)
        assert p.current_interval == INTERVAL_ACTIVE
        assert p.tier_index == 0

    def test_custom_initial_interval(self):
        clock = FakeClock()
        p = AdaptivePoller(initial_interval=15, tiers=TEST_TIERS, clock=clock)
        # First tier interval is overridden to initial_interval
        assert p.current_interval == 15

    def test_stays_at_tier_0_within_duration(self):
        clock = FakeClock()
        p = AdaptivePoller(initial_interval=10, tiers=TEST_TIERS, clock=clock)

        # Poll multiple times within the 100s tier-0 duration
        for _ in range(5):
            clock.advance(10)
            p.no_work_found()

        assert p.tier_index == 0
        assert p.current_interval == 10

    def test_promotes_after_tier_duration(self):
        clock = FakeClock()
        p = AdaptivePoller(initial_interval=10, tiers=TEST_TIERS, clock=clock)

        # Advance past tier 0 duration (100s)
        clock.advance(101)
        p.no_work_found()

        assert p.tier_index == 1
        assert p.current_interval == 20

    def test_promotes_through_multiple_tiers(self):
        clock = FakeClock()
        p = AdaptivePoller(initial_interval=10, tiers=TEST_TIERS, clock=clock)

        # Tier 0 → 1
        clock.advance(101)
        p.no_work_found()
        assert p.tier_index == 1

        # Tier 1 → 2
        clock.advance(101)
        p.no_work_found()
        assert p.tier_index == 2
        assert p.current_interval == 50

        # Tier 2 → 3 (permanent)
        clock.advance(101)
        p.no_work_found()
        assert p.tier_index == 3
        assert p.current_interval == 120

    def test_permanent_tier_stays(self):
        clock = FakeClock()
        p = AdaptivePoller(tiers=TEST_TIERS, clock=clock)

        # Advance well past all tiers
        clock.advance(500)
        p.no_work_found()
        assert p.tier_index == 3
        assert p.current_interval == 120

        # Even more time passes — still at max
        clock.advance(10000)
        p.no_work_found()
        assert p.tier_index == 3
        assert p.current_interval == 120

    def test_work_found_resets_to_tier_0(self):
        clock = FakeClock()
        p = AdaptivePoller(initial_interval=10, tiers=TEST_TIERS, clock=clock)

        # Promote to tier 2
        clock.advance(101)
        p.no_work_found()
        clock.advance(101)
        p.no_work_found()
        assert p.tier_index == 2

        p.work_found()
        assert p.tier_index == 0
        assert p.current_interval == 10

    def test_work_found_resets_timer(self):
        clock = FakeClock()
        p = AdaptivePoller(tiers=TEST_TIERS, clock=clock)

        # Almost at tier promotion
        clock.advance(99)
        p.no_work_found()
        assert p.tier_index == 0

        # Work found resets the clock
        p.work_found()

        # 99 more seconds — still at tier 0 because timer reset
        clock.advance(99)
        p.no_work_found()
        assert p.tier_index == 0

    def test_default_tiers_structure(self):
        assert len(DEFAULT_TIERS) == 4
        # First tier starts at 30s
        assert DEFAULT_TIERS[0][0] == 30
        # Last tier is 900s (15 min)
        assert DEFAULT_TIERS[-1][0] == 900

    def test_default_active_interval(self):
        assert INTERVAL_ACTIVE == 30

    def test_current_interval_triggers_promotion(self):
        """current_interval should auto-promote if duration elapsed."""
        clock = FakeClock()
        p = AdaptivePoller(tiers=TEST_TIERS, clock=clock)

        clock.advance(101)
        # Just reading current_interval should promote
        assert p.current_interval == 20
        assert p.tier_index == 1
