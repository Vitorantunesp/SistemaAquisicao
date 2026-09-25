"""Regression tests against the bundled LDTP implementation, without hardware."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor' / 'lynx_driver'))
import LDTP_Module
import LynxDriver


class RestartTests(unittest.TestCase):
    def test_three_acquisitions_reset_all_counters_on_same_connection(self):
        with patch.object(LDTP_Module, 'MAX_CHANNELS', 2), patch.object(LDTP_Module, 'SAMP_BUFF_SIZE', 32):
            module = LDTP_Module.LDTPModule()
        module._LDTPModule__listIPDev = ['192.168.1.180']
        socket = Mock()
        module._LDTPModule__listDataSocket = [socket]
        module._LDTPModule__listDev = [SimpleNamespace(ConnectionKey=1, Timestamp=100, Synced=True)]
        module.UpdateStatusAll = Mock(return_value=True)
        module.PeriodicHandle = Mock()
        module._LDTPModule__GetMessageAnswer = Mock(return_value=b'ack')
        with patch.object(LDTP_Module.LDTP_Const, 'ldtp_byte_to_packet_ack', return_value=SimpleNamespace(ErrorCode=0)), patch.object(LDTP_Module.time, 'sleep'):
            for _ in range(3):
                self.assertTrue(module.StartDataAcquisition())
                for field in ('sampPos', 'acqLastFrame', 'sampCount', 'sampsLost'):
                    self.assertEqual(getattr(module, '_LDTPModule__' + field), [0])
                    getattr(module, '_LDTPModule__' + field)[0] = 12
                self.assertEqual(module.GetNumSamps(), 0)
                self.assertEqual(module._LDTPModule__syncSampPos, 0)
                module._LDTPModule__syncSampCount = 12
                module._LDTPModule__syncSampPos = 12
                self.assertTrue(module.StopDataAcquisition())
        self.assertEqual(socket.send.call_count, 6)
        socket.close.assert_not_called()

    def test_stop_releases_only_active_devices_and_reports_failure(self):
        driver = LynxDriver.LynxDriverV1.__new__(LynxDriver.LynxDriverV1)
        driver._LynxDriverV1__listIp = ['a', 'b']
        driver.Module = Mock()
        driver.Module.DataConnActive = [False, True]
        driver.Module.StopDataAcquisition.return_value = False
        driver.Module.ReleaseDataConnection.return_value = True
        self.assertFalse(driver.StopAcq())
        driver.Module.ReleaseDataConnection.assert_called_once_with(1)
