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
from autobahn.wamp.types import ComponentConfig
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions
from OpenSSL import crypto

import so3g
import sisock
from spt3g import core
from spt3g.core import G3FrameType


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
    cur.execute("SELECT I.path, I.filename \
                 FROM file_info I \
                 JOIN feeds E on I.id = E.file_id \
                 WHERE E.id IN (SELECT DISTINCT feed_id \
                                FROM fields \
                                WHERE end > %s \
                                AND start < %s)", (start_str, end_str))
    path_file_list = cur.fetchall()

    # Build file list to read data
    file_list = []

    for path, _file in path_file_list:
        file_list.append(os.path.join(path, _file))

    return file_list


def _read_data_from_disk(data_cache, file_list):
    """Read data from disk. Meant to be called by blockingCallFromThread.

    Parameters
    ----------
    data_cache : dict
        data_cache dictionary with same format returned by
        this function, allows for checking already loaded
        data.
    file_list : list
        list of tuples with (file, year)

    Returns
    -------
    dict
        full file paths as keys, a dictionary as the value containing
        timestamps and tods. Requires further formatting before returning
        from sisock

    """
    for _file in file_list:
        # Only load data if not already in the cache
        if _file not in data_cache:
            print("{} not in data_cache, loading".format(_file))
            file_cache = _load_g3_file(_file)
            if file_cache is not None:
                data_cache[_file] = file_cache

    return data_cache

def _load_g3_file(_f):
    """Read in a g3 file.

    Parameters
    ----------
    _f (string) : file name to load (full path)

    Returns
    -------
    result (dict) : two keys, 'Timestamps' and 'TODs', each with a dictionary as
                    their values, the dictionary structure is dictated by that
                    stored in the .g3 file.

    """
    t = time.time()
    # Dependent on the actual .g3 internal format. Will also need updating when
    # so3g format finalized.
    cache_data = {'Timestamps': {},
                  'TODs': {}}

    prov_id_map = {}

    try:
        p = core.G3Pipeline()
        print("Adding {} to G3Reader".format(_f))
        p.Add(core.G3Reader, filename="{}".format(_f))
        p.Add(_read_data_to_cache, cache=cache_data, prov_map=prov_id_map)
        p.Run()
    except RuntimeError:
        print("Could not open {}".format(_f))
        cache_data = None

    # very much a debug statement, do not leave on in production (we really
    # need a better logging system...)
    #print("loaded data from file", cache_data)
    total_time_data = time.time() - t
    print("Time to read %s:" % _f, total_time_data)

    return cache_data

def _read_data_to_cache(frame, cache, prov_map):
    """A G3Pipeline Module for caching the current format of .g3 files for
    thermometry. Will need to be updated/replaced when general so3g format
    finalized.

    Parameters
    ----------
    frame : G3Frame
        the frame passed in a G3Pipeline
    cache : dict
        Cache of the data. Establish structure outside of this function, since
        we aren't really returning anything from the Pipeline. Allows
        extraction of data from G3Pipeline.
    prov_map : dict
        Map of provider ids and descriptions for creating timeline names from
        descriptions. Cached outside of pipeline.

    """
    # Make sure we're on an HKData frame.
    if frame.type == G3FrameType.Housekeeping:
        if frame['hkagg_type'] == 1:
            # Populate provider map.
            for provider in frame['providers']:
                description = str(provider['description']).strip('"')
                prov_id = int(str(provider['prov_id']))

                prov_map[prov_id] = description

            return

        if frame['hkagg_type'] == 2:
            pass
        else:
            return
    else:
        return

    for block in frame['blocks']:
        for channel in block.data.keys():
            # Create a feed dependent timeline_name just like in get_fields().
            _timeline_name = "{feed}.{field}".format(feed=prov_map[frame['prov_id']],
                                                     field=channel.lower().replace(' ', '_'))

            # Add channel key if it doesn't exist.
            if _timeline_name not in cache['Timestamps']:
                #print("Adding channel {} to cache['Timestamps']".format(channel))
                cache['Timestamps'][_timeline_name] = []
            if _timeline_name not in cache['TODs']:
                #print("Adding _timeline_name {} to cache['TODs']".format(_timeline_name))
                cache['TODs'][_timeline_name] = []

            # Add data from frame to cache
            cache['Timestamps'][_timeline_name] += list(block.t)
            cache['TODs'][_timeline_name] += list(block.data[channel])

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

    t = time.time()
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

    print("Time spent organizing data: {}".format(time.time() - t))

    t = time.time()
    # Determine 'finalized_until' time for each timeline
    for field in _data['timeline']:
        try:
            _data['timeline'][field]['finalized_until'] = np.max(_data['timeline'][field]['t'])
        except Exception as e:
            _data['timeline'][field]['finalized_until'] = None
            print("%s occured on field '%s', unable to determine ".format((type(e), field)) +
                  "'finalized_until' time, setting to None...")
    print("Time spent finding finalized_until: {}".format(time.time() - t))

    t = time.time()
    # Limit maximum number of points to return.
    if max_points != 0:
        for field in _data['data']:
            if max_points < len(_data['data'][field]):
                limiter = range(0, len(_data['data'][field]),
                                int(len(_data['data'][field])/max_points))
                _data['data'][field] = np.array(_data['data'][field])[limiter].tolist()
                _data['timeline'][field]['t'] = np.array(_data['timeline'][field]['t'])[limiter].tolist()
                _data['timeline'][field]['finalized_until'] = _data['timeline'][field]['t'][-1]
    print("Time spent downsampling: {}".format(time.time() - t))

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

        self.data_cache = {}

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
        # Profiling the get_fields method
        t_data = time.time()

        # Establish DB connection
        cnx = mysql.connector.connect(host=self.sql_config['host'],
                                      user=self.sql_config['user'],
                                      passwd=self.sql_config['passwd'],
                                      db=self.sql_config['db'])
        cur = cnx.cursor()
        print("SQL server connection established")

        start = sisock.base.sisock_to_unix_time(start)
        end = sisock.base.sisock_to_unix_time(end)

        file_list = _build_file_list(cur, start, end)
        print("Building file list for range {} to {}".format(start, end))
        #print("Built file list: {}".format(file_list)) # debug

        print('Reading data from disk from {start} to {end}.'.format(start=start, end=end))
        self.data_cache = _read_data_from_disk(self.data_cache, file_list)
        print("data_cache contains data from:", self.data_cache.keys())

        #print("data_cache contains:", self.data_cache) # debug

        t = time.time()
        _formatting = _format_data_cache_for_sisock(self.data_cache, start,
                                                    end, max_points=self.max_points)
        t_ellapsed = time.time() - t
        print("Formatted data in: {} seconds".format(t_ellapsed))
        #print("Formatted data:", _formatting) # debug

        # Close DB connection
        cur.close()
        cnx.close()

        total_time_data = time.time() - t_data
        print("Time to get data:", total_time_data)

        return _formatting


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
