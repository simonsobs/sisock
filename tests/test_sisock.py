import sisock
import mock

from twisted.trial import unittest
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred, returnValue

class TestSisockBaseFunctions(unittest.TestCase):
    """Test functions within the sisock base module."""
    def test_sisock_uri(self):
        """Test URI construction, which just combines the BASE_URI with the
        argument.
        """
        self.assertEqual(sisock.base.uri('test'), 'org.simonsobservatory.test')

    def test_sisock_to_unix_time(self):
        """Test sisock timestamp to unix time conversion.

        Input is a unix ctime, or a negative float which is used to set a time
        t seconds from now. This is a harder case to test, as it dynamically makes a
        time based on the current time stamp. We just test that it's not
        returning the negative value (which would be the default if it wasn't properly
        checked.)

        """
        # Test positive input (a fixed ctime)
        t = 1571772601.4099216
        self.assertEqual(sisock.base.sisock_to_unix_time(t), 1571772601.4099216)

        # Test negative input, which should return time.time() + t input
        self.assertNotEqual(sisock.base.sisock_to_unix_time(-1), -1)

class TestDataNodeServerClass(unittest.TestCase):
    """Test the sisock base DataNodeSever ApplicationSession.

    There is not a lot of documentation for properly testing twisted/WAMP
    applications. The start of this was based on this blog post:
    https://medium.com/@headquartershq/using-mock-and-trial-to-create-unit-tests-for-crossbar-applications-867e5b941cf2

    """

    def setUp(self):
        self.app_session = sisock.base.DataNodeServer()

    @inlineCallbacks
    def mock_call(self, procedure, value, *args, **kwargs):
        """twisted way to test an inlineCallback."""
        d = Deferred()
        reactor.callLater(0, d.callback, [], {})
        result = yield d
        returnValue(result)

    @inlineCallbacks
    def test_direct_get_data_call(self):
        """get_data should raise an error if _get_data_blocking isn't
        overridden. Make the call and test that.

        """
        # Mock the "call" method to use the above one
        self.app_session.call = mock.MagicMock(side_effect=self.mock_call)
        with self.assertRaises(RuntimeError):
            value = yield self.app_session.get_data('test', 1, 2)

    @inlineCallbacks
    def test_direct_get_data_fields(self):
        """get_fields should raise an error if _get_fields_blocking isn't
        overridden. Make the call and test that.

        """
        # Mock the "call" method to use the above one
        self.app_session.call = mock.MagicMock(side_effect=self.mock_call)
        with self.assertRaises(RuntimeError):
            value = yield self.app_session.get_fields(1, 2)
