import time
import unittest

from ads1800_app.backends.simulator import SimulatorBackend
from ads1800_app.config import ChannelConfig


class SimulatorTests(unittest.TestCase):
    def test_simulator_generates_aligned_samples(self):
        backend = SimulatorBackend()
        info = backend.connect("127.0.0.1")
        self.assertEqual(info.channel_count, 8)
        channels = [ChannelConfig(0, enabled=True), ChannelConfig(2, enabled=True)]
        backend.start(1000, channels)
        time.sleep(0.03)
        timestamps, values = backend.read()
        backend.stop()
        self.assertGreater(len(timestamps), 0)
        self.assertEqual(len(values), 2)
        self.assertTrue(all(len(channel) == len(timestamps) for channel in values))


if __name__ == "__main__":
    unittest.main()
