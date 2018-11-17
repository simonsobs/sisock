###############################################################################
#
# The MIT License (MIT)
#
# Copyright (c) Crossbar.io Technologies GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
###############################################################################

import sys
import time
import numpy as np

from os import environ

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

from autobahn.wamp.types import ComponentConfig
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner

import sisock


class thermometry_server(sisock.base.DataNodeServer):
    """
    An application component that subscribes and receives events
    of no payload and of complex payload, and stops after 5 seconds.
    """
    data = {}
    _available = False

    def __init__(self, config, name, description, target=None):
        ApplicationSession.__init__(self, config)
        self.target = target
        self.name = name
        self.description = description

    # Need to overload onConnect and onChallenge to get ws connection over port 8001 to crossbar
    def onConnect(self):
        self.log.info('transport connected')
        self.join(self.config.realm)

    def onChallenge(self, challenge):
        self.log.info('authentication challenge received')

    def onJoin(self, details):
        """Override parent method. See parent class for documentation. It is
        triggered after successfully joining WAMP session. 
        """
        self.log.info("Successfully joined WAMP.")

        self._register_procedures(details)

        print('targeting observatory.{}.feeds.temperatures'.format(self.target))

        def cache_data(subscription_message):
            """Cache data from the LS372 Agent.

            Args:
                subscription_message (tuple): Data from the OCS subscription feed.
                                              See OCS Feed documentation for
                                              message structure.
            """
            message, feed_data = subscription_message

            # Check we're a DataNodeServer for the correct Agent.
            if feed_data['agent_address'] == 'observatory.{}'.format(self.target):
                for channel in message.keys():
                    channel_name = channel.lower().replace(' ', '_')

                    if channel_name not in self.data.keys():
                        self.data[channel_name] = {"time": [], "data": []}

                    # Cache latest data point.
                    self.data[channel_name]['time'].append(message[channel][0])
                    self.data[channel_name]['data'].append(message[channel][1])

                    # Clear front entry if older than an hour.
                    if time.time() - self.data[channel_name]['time'][0] > 3600:
                        self.data[channel_name]['time'].pop(0)
                        self.data[channel_name]['data'].pop(0)

                # Only report it's available to the hub after self.data is ready
                if not self._available:
                    self._report_availability(details)
                    self._available = True

                # Debug printing. Do NOT leave on in production.
                # print("Got event: {}".format(a))
                # print("data: {}".format(self.data))

        yield self.subscribe(cache_data, u'observatory.{}.feeds.temperatures'.format(self.target))

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

                # Get the data for this field from self.data within given time frame.
                idx = np.where(np.logical_and(np.array(self.data[field_name]['time'])>=start, np.array(self.data[field_name]['time'])<=end))
                _data['data'][field_name] = np.array(self.data[field_name]['data'])[idx[0]].tolist()

                # _data['timeline']
                _timeline_name = 'observatory.{}'.format(self.target) + '.' + field_name

                if _timeline_name not in _data['timeline']:
                    _data['timeline'][_timeline_name] = {'t': [], 'finalized_until': None}

                _data['timeline'][_timeline_name]['t'] = np.array(self.data[field_name]['time'])[idx[0]].tolist()

            except KeyError:
                print("Received data query for field {} when it doesn't exist.".format(field_name))

        return _data

    def get_fields(self, start, end):
        """Overriding parent method definition.

        Always return all fields available in any time range, ignoring
        start/end arguments.
        """
        _field = {}
        _timeline = {}

        for channel_name in self.data.keys():
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

    # Check variables setup when creating the Docker container.
    required_env = ['TARGET', 'NAME', 'DESCRIPTION']

    for var in required_env:
        try:
            environ[var]
        except KeyError:
            print("Required environment variable {} missing. Check your environment setup and try again.".format(var))
            sys.exit()

    # Start our component.
    # When running locally, not in a container.
    # runner = ApplicationRunner(u'ws://127.0.0.1:8001/ws', u'test_realm')
    runner = ApplicationRunner(u'ws://sisock_crossbar:8001/ws', u'test_realm')
    runner.run(thermometry_server(ComponentConfig(u'test_realm', {}), name=environ['NAME'], description=environ['DESCRIPTION'], target=environ['TARGET']))
