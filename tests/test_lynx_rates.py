"""Hardware-reported rates must remain authoritative, without an 8/24 kHz cap."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ads1800_app.backends.lynx import LynxBackend
from ads1800_app.config import ChannelConfig


class LynxRatesTests(unittest.TestCase):
    def test_hardware_rates_are_preserved_and_sent_unchanged(self):
        for maximum in (8000, 24000, 48000, 96000):
            with self.subTest(maximum=maximum):
                driver = Mock()
                driver.ConnectTo.return_value = True
                driver.GetAvailableSampFreq.return_value = [maximum, 1000]
                driver.ChInfo = [[SimpleNamespace(IsDig=False)]]
                driver.Module.GetDevInfo.return_value = SimpleNamespace(Tag='Teste')
                driver.StartAcq.return_value = True
                loader = (SimpleNamespace(LynxDriverV1=lambda: driver), SimpleNamespace(LDTP_CHTYPE_ANIN=0))
                with patch.object(LynxBackend, '_load_driver', return_value=loader):
                    backend = LynxBackend()
                    info = backend.connect('192.168.1.180')
                    self.assertEqual(max(info.available_sample_rates), maximum)
                    backend.start(maximum, [ChannelConfig(0, enabled=True)])
                    driver.StartAcq.assert_called_once_with(maximum, [['192.168.1.180', 0, 0]], useDeviceTimestamp=False)
                    with self.assertRaisesRegex(ValueError, 'nao informada'):
                        backend.start(maximum + 1, [ChannelConfig(0, enabled=True)])
                    self.assertEqual(driver.StartAcq.call_count, 1)
                    backend.disconnect()
                    self.assertEqual(backend._available_sample_rates, [])
