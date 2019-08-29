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

from so3g.hk import HKArchiveScanner
import sisock

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


def _down_sample_data(get_data_dict, max_points):
    """Simple downsampling via numpy slicing.

    Slices data using a step size determined by len(array)/max_points. Will not
    capture details like single sample spikes, etc, but should allow us to use
    the g3-reader for larget datasets until better downsampling to file is
    implemented.

    Parameters
    ----------
    get_data_dict : dict
        Dictionary that we've built for get_data, fully sampled
    max_points : int
        The maximum number of points per field to return (roughly anyway)

    Returns
    -------
    dict
        A dictionary with the same layout as get_data_dict, just downsampled

    """
    new_get_data_array = {'data': {}, 'timeline': {}}
    for field, data_array in get_data_dict['data'].items():
        if max_points < len(data_array):
            step = int(len(data_array)/max_points)
            new_get_data_array['data'][field] = np.array(data_array)[::step].tolist()
        else:
            new_get_data_array['data'][field] = data_array

    for group, timeline_dict in get_data_dict['timeline'].items():
        if max_points < len(timeline_dict['t']):
            step = int(len(timeline_dict['t'])/max_points)
            new_get_data_array['timeline'][group] = {'t': np.array(timeline_dict['t'])[::step].tolist()}
            new_get_data_array['timeline'][group]['fields'] = timeline_dict['fields']
            new_get_data_array['timeline'][group]['finalized_until'] = np.array(timeline_dict['t'])[::step][-1]
        else:
            new_get_data_array['timeline'][group] = timeline_dict

    return new_get_data_array


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
        self.cache_list = []
        self.hkas = HKArchiveScanner()
        self.archive = None

        # Logging
        self.log = txaio.make_logger()


    def _scan_data_from_disk(self, file_list):
        """Scan data from disk using the so3g HKArchiveScanner. Meant to be called
        by blockingCallFromThread.

        Parameters
        ----------
        file_list : list
            list of files to scan with the ArchiveScanner

        Returns
        -------
        so3g.hk.HKArchive
            HKArchive object, which has get_fields and get_data methods identical
            to sisock. Can be used directly to retrieve data.

        """
        for filename in file_list:
            if filename not in self.cache_list:
                try:
                    self.hkas.process_file(filename)
                    self.cache_list.append(filename)
                except RuntimeError:
                    self.log.debug("Exception raised while reading file {f}," +
                                   "likely the file is not yet done writing",
                                   f=filename)
            else:
                self.log.debug("{f} already in cache list, skipping", f=filename)

        self.archive = self.hkas.finalize()

        return self.archive


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
        self._scan_data_from_disk(file_list)

        self.log.info(f"Getting data for fields: {field}")
        _data, _timeline = self.archive.get_data(field, start, end, min_stride, short_match=True)

        # Cast as lists
        _new_data, _new_timeline = _cast_data_timeline_to_list(_data, _timeline)
        _formatting = {"data": _new_data, "timeline": _new_timeline}

        # Downsample the data
        t = time.time()
        result = _down_sample_data(_formatting, self.max_points)
        t_ellapsed = time.time() - t
        self.log.debug("Downsampled data in: {time} seconds", time=t_ellapsed)

        total_time_data = time.time() - t_data
        self.log.debug("Time to get data: {time}", time=total_time_data)

        return result


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
    runner = ApplicationRunner("wss://%s:%d/ws" % (sisock.base.SISOCK_HOST,
                                                   sisock.base.SISOCK_PORT),
                               sisock.base.REALM, ssl=opt)
    runner.run(G3ReaderServer(ComponentConfig(sisock.base.REALM, {}),
                              sql_config=SQL_CONFIG))
