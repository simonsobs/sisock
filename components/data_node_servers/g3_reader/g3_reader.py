"""
g3_reader
A DataNodeServer which reads housekeeping data from .g3 files written to disk.

Notes:
    * You will need to also run the sisock component g3-file-scanner, with an
      accompanying MySQL database.
    * It does not implement a min_stride
    * It does implement a maximum number of data points returned, through the
      MAX_POINTS environment variable (optional).
"""

import time
import os
from os import environ
from datetime import datetime

import numpy as np
import six
import mysql.connector
import txaio
from autobahn.wamp.types import ComponentConfig
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions
from OpenSSL import crypto

import so3g
import sisock
from spt3g import core
from spt3g.core import G3FrameType
from so3g.hk import HKArchiveScanner

# For logging
txaio.use_twisted()

def _build_file_list(cur, start, end):
    """Build the file list to read in all the data within a given start/end
    range.

    We build the list by querying the database for all files that have fields
    within the start/end range.

    Parameters
    ----------
    cur : mysql.connector.cursor.MySQLCursor object
        SQL cursor provided by mysql.connector connection.
    start : float
        unixtime stamp for start time
    end : float
        unixtime stamp for end time

    Returns
    -------
    list
        list of complete file paths to read in

    """
    # datetime objects from unix times
    start_dt = datetime.utcfromtimestamp(start)
    end_dt = datetime.utcfromtimestamp(end)

    # String formatting for SQL query
    start_str = start_dt.strftime("%Y-%m-%d %H-%M-%S.%f")
    end_str = end_dt.strftime("%Y-%m-%d %H-%M-%S.%f")

    print("Querying database for filelist")
    cur.execute("SELECT path, filename \
                 FROM feeds \
                 WHERE id IN (SELECT DISTINCT feed_id \
                              FROM fields \
                              WHERE end > %s \
                              AND start < %s)", (start_str, end_str))
    path_file_list = cur.fetchall()

    # Build file list to read data
    file_list = []

    for path, _file in path_file_list:
        file_list.append(os.path.join(path, _file))

    # Remove duplicates
    file_list = list(set(file_list))
    file_list.sort()

    return file_list


def _read_data_from_disk(data_cache, file_list):
    """Read data from disk using the so3g HKArchiveScanner.  Meant to be called
    by blockingCallFromThread.

    Parameters
    ----------
    data_cache : dict
        data_cache dictionary with same format returned by
        this function, allows for checking already loaded
        data.
    file_list : list
        list of files

    Returns
    -------
    so3g.hk.HKArchive
        HKArchive object, which has get_fields and get_data methods identical
        to sisock. Can be used directly to retrieve data.

    """
    hkcs = HKArchiveScanner()
    for filename in file_list:
        hkcs.process_file(filename)
    archive = hkcs.finalize()

    return archive


def _format_data_cache_for_sisock(cache, start, end, max_points=0):
    """Format for return from sisock API.

    Parameters
    ----------
    cache : dict
        Cache of the data read from disk.
    start : float
        Starting unix timestamp, before which we won't return data
    end : float
        Ending unix timestamp, after which we won't return data
    max_points : int
        Maximum number of points to return, 0 returns all points.

    Returns
    -------
    dict
        dictionary structured for return from the sisock API

    """

    _data = {'data': {},
             'timeline': {}}

    # Needs to be sorted so that data is displayed properly in grafana
    filenames = list(cache.keys())
    filenames.sort()

    for filename in filenames:
        contents = cache[filename]
        for field, data in contents['Timestamps'].items():
            # Add timelines to _data['timeline']
            if field not in _data['timeline']:
                _data['timeline'][field] = {'t': [], 'finalized_until': None}

            full_t = np.array(data)
            t_idx = np.logical_and(full_t > start, full_t < end)
            t_cut = full_t[t_idx]
            _data['timeline'][field]['t'] += t_cut.tolist()

            # Add data to _data['data']
            if field not in _data['data']:
                _data['data'][field] = []

            #print("T_IDX", t_idx)
            #print("LOOK", contents['TODs'][field])
            _data['data'][field] += np.array(contents['TODs'][field])[t_idx].tolist()

    # Determine 'finalized_until' time for each timeline
    for field in _data['timeline']:
        try:
            _data['timeline'][field]['finalized_until'] = np.max(_data['timeline'][field]['t'])
        except Exception as e:
            _data['timeline'][field]['finalized_until'] = None
            print("%s occured on field '%s', unable to determine 'finalized_until' time, \
                  setting to None..." % (type(e), field))

    # Limit maximum number of points to return.
    if max_points != 0:
        for field in _data['data']:
            if max_points < len(_data['data'][field]):
                limiter = range(0, len(_data['data'][field]),
                                int(len(_data['data'][field])/max_points))
                _data['data'][field] = np.array(_data['data'][field])[limiter].tolist()
                _data['timeline'][field]['t'] = np.array(_data['timeline'][field]['t'])[limiter].tolist()
                _data['timeline'][field]['finalized_until'] = _data['timeline'][field]['t'][-1]

    return _data


def _format_sisock_time_for_sql(sisock_time):
    """Format a sisock timestamp for SQL queries.

    Parameters
    ----------
    sisock_time : float
        The sisock time for the field list. See base.DataNodeServer API for
        details.

    Returns
    -------
    string
        date formatted as string in format %Y-%m-%d %H-%M-%S.%f, suitable for a
        query to SQL

    """
    # Unix timestamp format (ctime)
    unix = sisock.base.sisock_to_unix_time(sisock_time)

    # datetime object format
    time_dt = datetime.fromtimestamp(unix)

    # String formatting for SQL query
    sql_str = time_dt.strftime("%Y-%m-%d %H-%M-%S.%f")

    return sql_str


def _cast_data_timeline_to_list(data, timeline):
    """Cast data and timelines as lists for WAMP serialization.

    The so3g HKArchiveScanner returns data as either native g3 types or numpy
    arrays. We need them to be lists in order for WAMP to accept them.

    Parameters
    ----------
    data : dict
        Data dictionary returned by so3g HKArchiveScanner's get_data() method
    timeline : dict
        Timeline dictionary returned by so3g HKArchiveScanner's get_data()
        method

    Returns
    -------
    dict, dict
        data and timeline dictionaries with data and 't' fields cast as lists

    """
    _new_data = {}
    for k, v in data.items():
        _new_data[k] = list(v)

    _new_timeline = {}
    for k, v in timeline.items():
        new_v = {}
        for k2, v2 in v.items():
            if k2 == 't':
                new_v[k2] = list(v2)
            else:
                new_v[k2] = v2
        _new_timeline[k] = new_v

    return _new_data, _new_timeline

class G3ReaderServer(sisock.base.DataNodeServer):
    """A DataNodeServer serving housekeeping data stored in .g3 format on disk."""
    def __init__(self, config, sql_config):
        ApplicationSession.__init__(self, config)

        # Default to 0, which returns all available data
        self.max_points = int(environ.get("MAX_POINTS", 0))

        # Here we set the name of this data node server
        self.name = "g3_reader"
        self.description = "Read g3 files from disk."

        # For SQL connections within blocking methods
        self.sql_config = sql_config

        # Data cache for opening g3 files
        self.data_cache = {}

        # Logging
        self.log = txaio.make_logger()

    def _get_fields_blocking(self, start, end):
        """Over-riding the parent class prototype: see the parent class for the
        API.

        Query the MySQL DB for available fields between the start and end
        times.

        """
        # Profiling the get_fields method
        t = time.time()

        # Establish DB connection
        cnx = mysql.connector.connect(host=self.sql_config['host'],
                                      user=self.sql_config['user'],
                                      passwd=self.sql_config['passwd'],
                                      db=self.sql_config['db'])
        cur = cnx.cursor()
        print("SQL server connection established")

        # Get feed_ids and field names from database.
        print("Querying database for all fields")
        cur.execute("SELECT description \
                     FROM description")
        descriptions = cur.fetchall()

        # print("Queried for fields:", fields) # debug

        # Construct our fields.
        _field = {}
        _timeline = {}

        for description in descriptions:
            _timeline_name = description[0]

            if _timeline_name not in _field:
                _field[_timeline_name] = {'description': None,
                                          'timeline': _timeline_name,
                                          'type': 'number',
                                          'units': None}

            if _timeline_name not in _timeline:
                _timeline[_timeline_name] = {'interval': None,
                                             'field': []}

            if _timeline_name not in _timeline[_timeline_name]['field']:
                _timeline[_timeline_name]['field'].append(_timeline_name)

        # Close DB connection
        cur.close()
        cnx.close()

        total_time = time.time() - t
        print("Time to build field list:", total_time)

        return _field, _timeline

    def _get_data_blocking(self, field, start, end, min_stride=None):
        """Over-riding the parent class prototype: see the parent class for the
        API.

        """
        # Benchmarking
        t_data = time.time()

        # Establish DB connection
        cnx = mysql.connector.connect(host=self.sql_config['host'],
                                      user=self.sql_config['user'],
                                      passwd=self.sql_config['passwd'],
                                      db=self.sql_config['db'])
        cur = cnx.cursor()
        self.log.debug("SQL server connection established")

        # Format start and end times
        start = sisock.base.sisock_to_unix_time(start)
        end = sisock.base.sisock_to_unix_time(end)

        # Build the list of files to open
        file_list = _build_file_list(cur, start, end)
        self.log.debug("Built file list: {}".format(file_list))

        # Close DB connection
        cur.close()
        cnx.close()

        # Use HKArchiveScanner to read data from disk
        self.log.debug('Reading data from disk from {start} to {end}'.format(start=start, end=end))
        self.data_cache = _read_data_from_disk(self.data_cache, file_list)

        self.log.info(f"Getting data for fields: {field}")
        _data, _timeline = self.data_cache.get_data(field, start, end, min_stride, short_match=True)

        # Cast as lists
        _new_data, _new_timeline = _cast_data_timeline_to_list(_data, _timeline)
        _formatting = {"data": _new_data, "timeline": _new_timeline}

        #t = time.time()
        #_formatting = _format_data_cache_for_sisock(self.data_cache, start,
        #                                            end, max_points=self.max_points)
        #t_ellapsed = time.time() - t
        #print("Formatted data in: {} seconds".format(t_ellapsed))
        #print("Formatted data:", _formatting) # debug

        #print(_formatting['data'].keys())
        #print(_formatting['timeline'].keys())

        #group_map = {}
        #for group, v in _formatting['timeline'].items():
        #    for _field in v['fields']:
        #        group_map[_field] = group
        #self.log.debug('group_map: {}'.format(group_map))

        ## Naive downsampling
        #max_points = 1000
        #if max_points != 0:
        #    for field in _formatting['data']:
        #        if max_points < len(_formatting['data'][field]):
        #            limiter = range(0, len(_formatting['data'][field]),
        #                            int(len(_formatting['data'][field])/max_points))
        #            _formatting['data'][field] = np.array(_formatting['data'][field])[limiter].tolist()
        #            _formatting['timeline'][group_map[field]]['t'] = np.array(_formatting['timeline'][group_map[field]]['t'])[limiter].tolist()
        #            _formatting['timeline'][group_map[field]]['finalized_until'] = _formatting['timeline'][group_map[field]]['t'][-1]

        total_time_data = time.time() - t_data
        print("Time to get data:", total_time_data)

        return _formatting


if __name__ == "__main__":
    # Give time for crossbar server to start
    time.sleep(5)

    # Start logging
    txaio.start_logging(level=environ.get("LOGLEVEL", "info"))

    # Because we're using a self-signed certificate, we need to tell Twisted
    # that it is OK to trust it.
    cert_fname = (".crossbar/server_cert.pem")
    cert = crypto.load_certificate(crypto.FILETYPE_PEM,
                                   six.u(open(cert_fname, 'r').read()))

    opt = CertificateOptions(trustRoot=OpenSSLCertificateAuthorities([cert]))

    # Check variables setup when creating the Docker container.
    required_env = ['SQL_HOST', 'SQL_USER', 'SQL_PASSWD', 'SQL_DB']

    for var in required_env:
        try:
            environ[var]
        except KeyError:
            print("Required environment variable {} is missing. \
                   Check your environment setup and try again.".format(var))

    # SQL Config
    # User/password just for development purposes, obviously change in production.
    SQL_CONFIG = {'host': environ['SQL_HOST'],
                  'user': environ['SQL_USER'],
                  'passwd': environ['SQL_PASSWD'],
                  'db': environ['SQL_DB']}

    # Start our component.
    runner = ApplicationRunner("wss://%s:%d/ws" % (sisock.base.SISOCK_HOST, \
                                                   sisock.base.SISOCK_PORT), \
                               sisock.base.REALM, ssl=opt)
    runner.run(G3ReaderServer(ComponentConfig(sisock.base.REALM, {}),
                              sql_config=SQL_CONFIG))
