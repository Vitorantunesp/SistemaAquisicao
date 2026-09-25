from pathlib import Path
import tempfile
import unittest

from ads1800_app.config import ChannelConfig, ExperimentConfig


class ConfigTests(unittest.TestCase):
    def test_calibration(self):
        channel = ChannelConfig(0, gain=2.5, offset=-1.0)
        self.assertEqual(channel.apply_calibration(4.0), 9.0)

    def test_config_round_trip(self):
        original = ExperimentConfig(name="Ensaio", sample_rate=500.0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original.save(path)
            loaded = ExperimentConfig.load(path)
        self.assertEqual(loaded.name, "Ensaio")
        self.assertEqual(loaded.sample_rate, 500.0)
        self.assertEqual(len(loaded.channels), 8)

    def test_requires_enabled_channel(self):
        config = ExperimentConfig(channels=[ChannelConfig(i) for i in range(8)])
        with self.assertRaisesRegex(ValueError, "canal"):
            config.validate()


if __name__ == "__main__":
    unittest.main()
