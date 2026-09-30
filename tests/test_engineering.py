"""Exercise the real driver's parameter decoding and engineering conversion."""
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor' / 'lynx_driver'))
import LynxDriver
import LDTP_Const as constants
from ads1800_app.backends.lynx import LynxBackend
from ads1800_app.config import ChannelConfig


class EngineeringTests(unittest.TestCase):
    def test_device_parameters_to_engineering_endpoints_and_no_second_calibration(self):
        for low, high in [(-100., 300.), (-50., 50.), (0., 1000.), (100., -100.)]:
            with self.subTest(low=low, high=high):
                driver = LynxDriver.LynxDriverV1.__new__(LynxDriver.LynxDriverV1)
                driver.Module = Mock()
                driver.ChInfo = [[]]
                driver.Module.GetDevInfo.return_value = SimpleNamespace(NumAnInCh=1)
                requested = []
                def request(dev, params):
                    param = params[0].ParamNum
                    requested.append(param)
                    if param in (constants.LDTP_PARAM_ANIN_LOWLIM, constants.LDTP_PARAM_ANIN_HIGHLIM):
                        value = low if param == constants.LDTP_PARAM_ANIN_LOWLIM else high
                        return True, [SimpleNamespace(Size=4, Values=[struct.unpack('<I', struct.pack('<f', value))[0]])]
                    value = b'Martelo' if param == constants.LDTP_PARAM_ANIN_CHNAME else b'N'
                    return True, [SimpleNamespace(Size=32, Values=struct.unpack('<8I', value.ljust(32, b'\0')))]
                driver.Module.RequestParam.side_effect = request
                self.assertTrue(driver._LynxDriverV1__GetAnChannelConf(0, constants.LDTP_CHTYPE_ANIN))
                self.assertEqual(driver.ChInfo[0][0].LowLim, low)
                self.assertEqual(driver.ChInfo[0][0].HighLim, high)
                self.assertEqual(driver.ChInfo[0][0].Unit, 'N')
                self.assertIn(1921, requested)
                self.assertIn(1922, requested)
                driver.PeriodicHandle = Mock()
                driver._LynxDriverV1__lastSampReadAll = 0
                driver._LynxDriverV1__chRef = [0]
                driver.Module.GetNumSamps.return_value = 4
                half = constants.LDTP_ANIN_RANGE_NOT_OVERRANGE / 2
                driver.Module.GetSamples.side_effect = lambda ch, count: ([0., 1., 2., 3.] if ch == -1
                                                                          else [-half, 0., half, half * 1.05])
                backend = LynxBackend()
                backend._driver = driver
                backend._channels = [ChannelConfig(0, enabled=True, gain=400, offset=10)]
                times, values = backend.read()
                self.assertEqual(times, [0, 1, 2, 3])
                for actual, expected in zip(values[0], [low, (low + high) / 2, high, high + .025 * (high - low)]):
                    self.assertAlmostEqual(actual, expected)
                self.assertEqual(backend.read(), ([], []))
