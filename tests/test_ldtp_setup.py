"""Exercise the real driver's setup serialization without a network connection."""
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor" / "lynx_driver"))
import LDTP_Const
import LDTP_Module


class SetupTests(unittest.TestCase):
    def test_setup_serializes_integer_sample_count_and_preserves_frequency(self):
        for frequency, channels, expected_count in (
            (1000.0, [0], 100),
            (1000.0, [0, 1, 2], 100),
            (1000.0, list(range(8)), 45),
            (12.5, [7], 1),
            (12000.0, [0], 360),
            (24000.0, list(range(8)), 45),
            (48000.0, list(range(8)), 45),
            (1.0, [0], 1),
            (5.0, [0], 1),
        ):
            with self.subTest(frequency=frequency, channels=channels):
                # Only construct the state used by DataAcqSetup; no large sample
                # buffers or real sockets are required for this regression test.
                module = LDTP_Module.LDTPModule.__new__(LDTP_Module.LDTPModule)
                socket = Mock()
                module._LDTPModule__listDataSocket = [socket]
                module._LDTPModule__acqActive = False
                module._LDTPModule__acqNumCh = []
                module._LDTPModule__listDev = [SimpleNamespace(ConnectionKey=42)]
                module._LDTPModule__command_tag = 0
                module._LDTPModule__RunAsThread = True
                module._LDTPModule__GetMessageAnswer = Mock(return_value=b"ack")
                with patch.object(LDTP_Const, "ldtp_byte_to_packet_ack",
                                  return_value=SimpleNamespace(ErrorCode=0)):
                    self.assertTrue(module.DataAcqSetup(0, frequency, channels))
                payload = socket.send.call_args.args[0]
                decoded = struct.unpack(
                    LDTP_Const.LDTP_MSG_PACK_DATAACQSETUP_FORMAT + "H" * len(channels),
                    payload,
                )
                self.assertEqual(decoded[5], frequency)
                self.assertEqual(decoded[6], len(channels))
                self.assertEqual(decoded[7], expected_count)
                self.assertEqual(list(decoded[15:]), channels)


if __name__ == "__main__":
    unittest.main()
