# Original work Copyright (c) Crossbar.io Technologies GmbH
# Modified work Copyright (c) 2018-2019 Simons Observatory Collaboration
# Please refer to licensing information in the root of this repository.

import sys
import time
import txaio
import numpy as np

from os import environ

from twisted.internet import reactor, threads
from twisted.internet.defer import inlineCallbacks

from autobahn.wamp.types import ComponentConfig
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.wamp.uri import SubscribeOptions

import sisock

# For logging
txaio.use_twisted()


class data_feed_server(sisock.base.DataNodeServer):
    """A data server that subscribes to a single ocs data feed address,
    recieves and caches data published to that feed, and returns that data when
    queried.

    Parameters
    ----------
    config : ComponentConfig
        autobahn ComponentConfig
    name : str
        sisock data server name, used within sisock
    description : str
        sisock data server description, used within sisock
    feed : str
        ocs registered feed name i.e. 'temperatures', used for subscribing to
        feed for data collection and caching
    target : str
        ocs agent target, i.e. "LSA22HA", used to assemble the complete
        crossbar address for subscribing to a feed for data collection
    buffer_time : int
        amount of time, in seconds, to buffer data for live monitor
    log : txaio.tx.Logger
        txaio logger object, used for logging in WAMP applications

    Attributes
    ----------
    cache : dict
        Data cache for storing published data

    """
    def __init__(self, config, name, description, feed, target=None,
                 buffer_time=3600):
        ApplicationSession.__init__(self, config)
        self.target = target
        self.name = name
        self.description = description
        self.buffer_time = buffer_time
        self.feed = feed

        # Logging
        self.log = txaio.make_logger()

        # Data Cache
        self.cache = {}

    # Need to overload onConnect and onChallenge to get ws connection over port
    # 8001 to crossbar
    def onConnect(self):
        self.log.info('transport connected')
        self.join(self.config.realm)

    def onChallenge(self, challenge):
        self.log.info('authentication challenge received')

    @inlineCallbacks
    def after_onJoin(self, details):
        print("session attached")

        print('targeting observatory.{}.feeds.{}'.format(self.target,
                                                         self.feed))

        @inlineCallbacks
        def cache_data(subscription_message):
            """Cache data from an OCS data feed.

            Parameters
            ----------
            subscription_message : tuple
                Data from the OCS subscription feed. See OCS Feed
                documentation for message structure.

            """
            message, feed_data = subscription_message
            self.log.debug("feed_data: {m}", m=feed_data)

            # Check we're a DataNodeServer for the correct Agent.
            if feed_data['agent_address'] == 'observatory.{}'.format(self.target):
                yield threads.deferToThread(self.extend_data, message, feed_data)
                print("Received published data from feed: " +
                      "observatory.{}.feeds.{}".format(self.target, self.feed))

        topic_uri = u'observatory.{}.feeds.{}'.format(self.target, self.feed)
        yield self.subscribe(cache_data, topic_uri, SubscribeOptions(match=u"wildcard"))

    def extend_data(self, message, feed_data):
        """Extend data in the cache recieved in message.

        This operation was slow enough to cause issues when run in the reactor
        thread. Be sure to call with deferToThread().

        Parameters
        ----------
        message
            message from OCS subscription feed. See OCS Feed documentation for
            message structure.
        feed_data
            feed_data dict from OCS Feed subscription

        """
        agent_address = feed_data['agent_address']
        feed_name = feed_data['feed_name']

        # Initialize top of cache dict
        if agent_address not in self.cache.keys():
            self.cache[agent_address] = {}

        if feed_name not in self.cache[agent_address].keys():
            self.cache[agent_address][feed_name] = {}

        # The specific sub-dict of the cache we're going to load data into
        target_cache = self.cache[agent_address][feed_name]

        for _, value in message.items():
            for key, data_array in value['data'].items():
                key_name = key.lower().replace(' ', '_')

                if key_name not in target_cache.keys():
                    target_cache[key_name] = {"time": [], "data": []}

                # Cache latest data point.
                target_cache[key_name]['data'].extend(value['data'][key])
                # This could be improved. We're caching a copy of the
                # timestamps array for each key, which is
                # inefficient for the 240s, but used to make sense in
                # the old feed scheme
                target_cache[key_name]['time'].extend(value['timestamps'])

                # Clear data from buffer.
                buff_idx = sum(time.time() -
                               np.array(target_cache[key_name]['time']) > self.buffer_time)
                target_cache[key_name]['time'] = target_cache[key_name]['time'][buff_idx:]
                target_cache[key_name]['data'] = target_cache[key_name]['data'][buff_idx:]

    def onDisconnect(self):
        print("disconnected")
        reactor.stop()

    def get_data(self, field, start, end, min_stride=None):
        """Overriding parent method definition.

        Note: min_stride not implemented.
        """
        start = sisock.base.sisock_to_unix_time(start)
        end = sisock.base.sisock_to_unix_time(end)

        _data = {'data': {}, 'timeline': {}}

        for field_name in field:
            try:
                # Populate _data
                # _data['data']
                if field_name not in _data['data']:
                    _data['data'][field_name] = []

                # Get the data for this field from self.cache within given time frame.
                idx = np.where(np.logical_and(np.array(self.cache[field_name]['time']) >= start,
                                              np.array(self.cache[field_name]['time']) <= end))
                _data['data'][field_name] = np.array(self.cache[field_name]['data'])[idx[0]].tolist()

                # _data['timeline']
                _timeline_name = 'observatory.{}'.format(self.target) + '.' + field_name

                if _timeline_name not in _data['timeline']:
                    _data['timeline'][_timeline_name] = {'t': [], 'finalized_until': None}

                _data['timeline'][_timeline_name]['t'] = \
                    np.array(self.cache[field_name]['time'])[idx[0]].tolist()

            except KeyError:
                self.log.warn("Received data query for field {} when it doesn't exist.".format(field_name))

        return _data

    def get_fields(self, start, end):
        """Overriding parent method definition.

        Always return all fields available in any time range, ignoring
        start/end arguments.
        """
        _field = {}
        _timeline = {}

        for channel_name in self.cache.keys():
            # Populate _field and _timeline
            _timeline_name = 'observatory.{}'.format(self.target) + '.' + channel_name

            if channel_name not in _field:
                _field[channel_name] = {'description': None,
                                        'timeline': _timeline_name,
                                        'type': 'number',
                                        'units': None}

            if _timeline_name not in _timeline:
                _timeline[_timeline_name] = {'interval': None,
                                             'field': []}

            if channel_name not in _timeline[_timeline_name]['field']:
                _timeline[_timeline_name]['field'].append(channel_name)

        # Debug printing. Do NOT leave on in production.
        # print("_timeline: {}".format(_timeline))
        # print("_field: {}".format(_field))

        return _field, _timeline


if __name__ == '__main__':
    # Give time for crossbar server to start
    time.sleep(5)

    # Start logging
    txaio.start_logging(level=environ.get("LOGLEVEL", "info"))

    # Check variables setup when creating the Docker container.
    required_env = ['TARGET', 'NAME', 'DESCRIPTION', 'FEED']

    for var in required_env:
        try:
            environ[var]
        except KeyError:
            print('Required environment variable {} missing. Check your environment setup and try again.'.format(var))
            sys.exit()

    # Optional environment variables.
    buffer_length = int(environ.get('BUFFER_TIME', '3600'))

    # Start our component.
    # When running locally, not in a container.
    runner = ApplicationRunner("ws://%s:%d/ws" % (sisock.base.SISOCK_HOST,
                                                  sisock.base.OCS_PORT),
                               sisock.base.REALM)
    runner.run(data_feed_server(ComponentConfig(u'test_realm', {}),
                                name=environ['NAME'],
                                description=environ['DESCRIPTION'],
                                feed=environ['FEED'],
                                target=environ['TARGET'],
                                buffer_time=buffer_length))
