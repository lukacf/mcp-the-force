"""Fast test utilities for mocking time-based operations."""

import asyncio
import time


class FastTimeSimulator:
    """Simulates time progression without actual waiting."""

    def __init__(self):
        self.current_time = time.monotonic()
        self.sleep_history = []

    def advance_time(self, seconds):
        """Advance simulated time by given seconds."""
        self.current_time += seconds

    def mock_monotonic(self):
        """Return current simulated time."""
        return self.current_time

    async def mock_sleep(self, seconds):
        """Record sleep call and advance time without actually sleeping."""
        self.sleep_history.append(seconds)
        self.advance_time(seconds)
        # Yield control but don't actually sleep
        await asyncio.sleep(0)

    def get_total_sleep_time(self):
        """Get total time that would have been slept."""
        return sum(self.sleep_history)
