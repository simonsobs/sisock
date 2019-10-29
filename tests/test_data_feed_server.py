import sys, os
sys.path.insert(0, os.path.dirname("./components/data_node_servers/data_feed/"))
from data_feed_server import data_feed_server

import mock
import time

from twisted.trial import unittest
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred, returnValue

class TestDataFeedServerClass(unittest.TestCase):
    """Test the data_feed_server ApplicationSession.

    There is not a lot of documentation for properly testing twisted/WAMP
    applications. The start of this was based on this blog post:
    https://medium.com/@headquartershq/using-mock-and-trial-to-create-unit-tests-for-crossbar-applications-867e5b941cf2

    """

    def setUp(self):
        #print('setUp was run')
        config = mock.MagicMock()
        self.app_session = data_feed_server(config, 'test', 'description', 'feed', target='testing')

    def tearDown(self):
        #print('tearDown was run')
        del(self.app_session)
        #print(self.app_session.data)

    @inlineCallbacks
    def mock_call(self, procedure, value, *args, **kwargs):
        """twisted way to test an inlineCallback."""
        d = Deferred()
        reactor.callLater(0, d.callback, [], {})
        result = yield d
        returnValue(result)

    def test_extend_data(self):
        """Tests extend_data(). This should populate the application session's
        data dictionary with the data in 'message'.

        Here we test for particular values from our example message.

        """
        # Mock the "call" method to use the above one
        #self.app_session.call = mock.MagicMock(side_effect=self.mock_call)

        t = time.time()
        message = {'temps': {'block_name': 'temps',
                   'data': {'Channel 1 T': [1.0, 2.0, 3.0, 4.0],
                            'Channel 1 V': [5.0, 6.0, 7.0, 8.0],
                            'Channel 2 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 2 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 3 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 3 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 4 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 4 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 5 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 5 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 6 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 6 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 7 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 7 V': [0.0, 0.0, 8.8, 0.0],
                            'Channel 8 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 8 V': [0.0, 0.0, 0.0, 0.0]},
                   'timestamps': [t, t+1, t+2, t+3],
                   'prefix': ''}}
        self.app_session.extend_data(message)

        # Test data points make it into session data
        self.assertEqual(self.app_session.data['channel_1_t']['data'], [1, 2, 3, 4])
        self.assertEqual(self.app_session.data['channel_7_v']['data'], [0, 0, 8.8, 0])

        # Test time makes it into session data, should be 1 second apart
        self.assertEqual(self.app_session.data['channel_1_t']['time'][0], t)
        t_diff = self.app_session.data['channel_1_t']['time'][1] - \
                 self.app_session.data['channel_1_t']['time'][0]
        self.assertEqual(t_diff, 1.0)

    @inlineCallbacks
    def test_get_data(self):
        """Test get_data().

        This tests the get_data call in the data_feed_server. Annoyingly I
        don't fully understand properly cleaning up ApplicationSessions, so data
        inserted into the self.app_session.data dictionary is persistent
        between tests. We insert data further in the future to avoid other
        data. This should be fixed, I'm just not sure how...

        """
        # Mock the "call" method to use the above one
        self.app_session.call = mock.MagicMock(side_effect=self.mock_call)
        t = time.time()
        message = {'temps': {'block_name': 'temps',
                   'data': {'Channel 1 T': [1.0, 2.0, 3.0, 4.0],
                            'Channel 1 V': [5.0, 6.0, 7.0, 8.0],
                            'Channel 2 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 2 V': [2.0, 3.0, 4.0, 5.0],
                            'Channel 3 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 3 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 4 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 4 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 5 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 5 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 6 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 6 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 7 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 7 V': [0.0, 0.0, 8.8, 0.0],
                            'Channel 8 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 8 V': [0.0, 0.0, 0.0, 0.0]},
                   'timestamps': [t+10, t+11, t+12, t+13],
                   'prefix': ''}}
        self.app_session.extend_data(message)
        result = yield self.app_session.get_data(['channel_2_v'], t+10, t+15)

        # Check data returned is the data we inserted
        self.assertEqual(result['data']['channel_2_v'], [2, 3, 4, 5])

        # Check top level structure of dictionary
        self.assertIn('data', result.keys())
        self.assertIsInstance(result['data'], dict)
        self.assertIn('timeline', result.keys())
        self.assertIsInstance(result['timeline'], dict)

        # Test except block when key doesn't exist
        value = yield self.app_session.get_data(['test'], 1, 2)

    @inlineCallbacks
    def test_get_fields(self):
        """Test get_fields().

        This tests the get_fields call in the data_feed_server. This has the
        same problem as the get_data test, so again we move the data further
        into the future.

        """
        # Mock the "call" method to use the above one
        self.app_session.call = mock.MagicMock(side_effect=self.mock_call)
        t = time.time()
        message = {'temps': {'block_name': 'temps',
                   'data': {'Channel 1 T': [1.0, 2.0, 3.0, 4.0],
                            'Channel 1 V': [5.0, 6.0, 7.0, 8.0],
                            'Channel 2 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 2 V': [2.0, 3.0, 4.0, 5.0],
                            'Channel 3 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 3 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 4 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 4 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 5 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 5 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 6 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 6 V': [0.0, 0.0, 0.0, 0.0],
                            'Channel 7 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 7 V': [0.0, 0.0, 8.8, 0.0],
                            'Channel 8 T': [0.0, 0.0, 0.0, 0.0],
                            'Channel 8 V': [0.0, 0.0, 0.0, 0.0]},
                   'timestamps': [t+20, t+21, t+22, t+23],
                   'prefix': ''}}
        self.app_session.extend_data(message)
        result = yield self.app_session.get_fields(t+20, t+25)

        # Check that two dictionaries are returned
        self.assertIsInstance(result[0], dict)
        self.assertIsInstance(result[1], dict)

        # Check field dict structure
        self.assertIn('channel_1_t', result[0].keys())
        self.assertIn('description', result[0]['channel_1_t'].keys())
        self.assertIn('timeline', result[0]['channel_1_t'].keys())
        self.assertIn('type', result[0]['channel_1_t'].keys())
        self.assertIn('units', result[0]['channel_1_t'].keys())
        self.assertIn(result[0]['channel_1_t']['type'], ["number", "string", "bool"])

        # Check timeline dict structure
        self.assertIn('observatory.testing.channel_1_t', result[1].keys())
        self.assertIn('interval', result[1]['observatory.testing.channel_1_t'].keys())
        self.assertIn('field', result[1]['observatory.testing.channel_1_t'].keys())
        self.assertIsInstance(result[1]['observatory.testing.channel_1_t']['field'], list)
        self.assertIn('channel_1_t', result[1]['observatory.testing.channel_1_t']['field'])
