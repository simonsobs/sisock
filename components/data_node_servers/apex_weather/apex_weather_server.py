"""
A DataNodeServer which serves APEX weather from disk. Based on the original
example, which served modified APEX weather files.
"""

import glob
import os
import six
import time
import numpy as np

from os import environ

from autobahn.wamp.types import ComponentConfig
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import threads
from OpenSSL import crypto

import sisock

DATA_LOCATION = "/data/"


def _build_file_list(field, start, end):
    """Build file list for given field and specified start/end range.

    Args:
        field (str): field name for file search (field must be in file name)
        start (float): unixtime stamp for start time
        end (float): unixtime stamp for end time

    Returns:
        list: A sorted list of files with data in the given range for the given
              field

    """
    t0 = time.time()

    file_list = []

    all_files = glob.glob(DATA_LOCATION + 'targets/*{field}*.dat'.format(field=field))
    all_files.sort()

    print("Processing {} files".format(len(all_files)))

    # Add files once start falls in the range covered by a file, then keeping
    # adding them until end falls in the range of another file. The
    # construction is a bit strange, my original approach made ranges out of
    # the ctimes in a file name and checked if the queried start/end times were
    # in the ranges. While this approach was quick when run directly on the
    # host, in a Docker container the performance suffered by a factor of
    # ~3,500, for reasons I couldn't figure out.

    add = False
    done = False

    for _file in all_files:
        file_info = os.path.split(_file)[1].replace(".dat", "").split("_")
        file_start = int(file_info[2])
        file_end = int(file_info[3])

        if done:
            break

        if add is False:
            if start >= file_start and start <= file_end:
                add = True
            if end >= file_start and end <= file_end:
                done = True
        else:
            if end >= file_start and end <= file_end:
                done = True

        if add:
            file_list.append(_file)

    file_list.sort()
    print("Built file list in {} seconds".format(time.time() - t0))

    return file_list


def _read_data_from_disk(file_list, start, end, max_points=None):
    """Do the I/O to get the data in file_list form disk up to end timestamp.

    Args:
        file_list (list): list of files to read
        end (float): ending timestamp, past which we won't read data
        max_points (int): maximum number of points to return

    Returns:
        dict: properly formatted dict for sisock to pass to grafana

    """
    _data = {'data': {}, 'timeline': {}}

    for _file in file_list:
        file_info = os.path.split(_file)[1].replace(".dat", "").split("_")[1:]
        field = file_info[0]
        print("Identified field {} for file {}".format(field, _file))

        # Initialize the field's data and timeline keys.
        if field not in _data['data'].keys():
            print("Adding {} to data dictionary".format(field))
            _data['data'][field] = []
            _data['timeline'][field] = {}
            _data['timeline'][field]['t'] = []
            _data['timeline'][field]['finalized_until'] = None
        else:
            print("Key {} already in data dictionary".format(field))

        with open(_file, 'r') as f:
            for l in f.readlines():
                line = l.strip().split()

                data = float(line[1])
                timestamp = float(line[0])

                if timestamp <= end and timestamp >= start:
                    _data['data'][field].append(data)
                    _data['timeline'][field]['t'].append(timestamp)
                    _data['timeline'][field]['finalized_until'] = timestamp
                else:
                    pass

    if max_points is not None:
        for field in _data['data'].keys():
            if max_points < len(_data['data'][field]):
                limiter = range(0, len(_data['data'][field]), int(len(_data['data'][field])/max_points))
                _data['data'][field] = np.array(_data['data'][field])[limiter].tolist()
                _data['timeline'][field]['t'] = np.array(_data['timeline'][field]['t'])[limiter].tolist()
                _data['timeline'][field]['finalized_until'] = _data['timeline'][field]['t'][-1]

    return _data


class apex_weather(sisock.base.DataNodeServer):
    """A DataNodeServer serving APEX weather station information.

    Inhereits from :class:`sisock.base.data_node_server`.
    """
    def __init__(self, config, max_points=None):
        ApplicationSession.__init__(self, config)
        self.max_points = max_points

        # Here we set the name of this data node server.
        self.name = "apex_weather"
        self.description = "Weather station information from APEX."


    def get_fields(self, start, end):
        """Over-riding the parent class prototype: see the parent class for the
        API."""

        # Note: These could be built dynamically, however, we've been logging
        # these things for ages, and they are unlikely to change. Also, things
        # like the description and units are not available within each file
        # like they are in the weather example.

        field = {"humidity": {"description": "APEX weather station humidity.",
                              "timeline": "humidity",
                              "type": "number",
                              "units": '%'},
                 "pressure": {"description": "APEX weather station pressure.",
                              "timeline": "pressure",
                              "type": "number",
                              "units": 'mBar'},
                 "radiometer": {"description": "APEX radiometer data.",
                                "timeline": "radiometer",
                                "type": "number",
                                "units": 'mm'},
                 "dewpoint": {"description": "APEX weather station dewpoint.",
                              "timeline": "dewpoint",
                              "type": "number",
                              "units": 'C'},
                 "temperature": {"description": "APEX weather station temperature.",
                                 "timeline": "temperature",
                                 "type": "number",
                                 "units": 'C'},
                 "windspeed": {"description": "APEX weather station windspeed.",
                               "timeline": "windspeed",
                               "type": "number",
                               "units": 'km/h'},
                 "winddirection": {"description": "APEX weather station wind direction.",
                                   "timeline": "winddirection",
                                   "type": "number",
                                   "units": 'deg'}}

        timeline = {"humidity": {"interval": None,
                                 "field": "humidity"},
                    "pressure": {"interval": None,
                                 "field": "pressure"},
                    "radiometer": {"interval": None,
                                   "field": "radiometer"},
                    "dewpoint": {"interval": None,
                                 "field": "dewpoint"},
                    "temperature": {"interval": None,
                                    "field": "temperature"},
                    "windspeed": {"interval": None,
                                  "field": "windspeed"},
                    "winddirection": {"interval": None,
                                      "field": "winddirection"}}

        return field, timeline

    def _get_data_blocking(self, field, start, end, min_stride=None):
        """Over-riding the parent class prototype: see the parent class for the
        API.

        """
        start = sisock.base.sisock_to_unix_time(start)
        end = sisock.base.sisock_to_unix_time(end)

        file_list = []
        for f in field:
            try:
                file_list += _build_file_list(f, start, end)
            except IOError:
                # Silently pass over a requested field that doesn't exist.
                pass

        print('Reading data from disk from {start} to {end}.'.format(start=start, end=end))
        return _read_data_from_disk(file_list, start, end, max_points=self.max_points)


if __name__ == "__main__":
    # Give time for crossbar server to start
    time.sleep(5)

    # Because we're using a self-signed certificate, we need to tell Twisted
    # that it is OK to trust it.
    cert_fname = (".crossbar/server_cert.pem")
    cert = crypto.load_certificate(crypto.FILETYPE_PEM,
                                   six.u(open(cert_fname, 'r').read()))

    opt = CertificateOptions(trustRoot=OpenSSLCertificateAuthorities([cert]))

    # Check variables setup when creating the Docker container.
    expected_env = ['MAX_POINTS']

    for var in expected_env:
        try:
            environ[var]
            print("Found environment variable {} with value of {}.".format(var, environ[var]))
        except KeyError:
            environ[var] = None
            print("Environment variable {} not provided. \
                  Setting to None and proceeding.".format(var))

    # Start our component.
    runner = ApplicationRunner('wss://sisock_crossbar:8080/ws', sisock.base.REALM, ssl=opt)
    runner.run(apex_weather(ComponentConfig(sisock.base.REALM, {}),
                            max_points=int(environ['MAX_POINTS'])))
