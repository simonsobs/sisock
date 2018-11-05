"""
A DataNodeServer which serves UCSC Radiometer data from the ACT site.

Notes:
    * This server has a single field, 'pwv'.
    * It reads the data from disk on every get_data call, no caching.
    * It uses open and readlines in a non-threadsafe way.
    * It does not implement a min_stride, or maximum number of data points
      returned.
    * It requires a bindmount to /data/.
"""

import os
import six
import time
import datetime

from autobahn.twisted.wamp import ApplicationRunner
from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions
from OpenSSL import crypto

# from twisted.internet import threads, reactor

import sisock

DATA_LOCATION = "/data/"


def _build_file_list(start, end):
    """Build the file list to read in all the data within a given start/end
    range.

    Args:
        start (float): unixtime stamp for start time
        end (float): unixtime stamp for end time

    Returns:
        list: list of 2-tuples with (file, year) for files to read in to
              collect all the data

    """
    start_datetime = datetime.datetime.utcfromtimestamp(start)
    end_datetime = datetime.datetime.utcfromtimestamp(end)

    # Get list of files between start and end
    start_day = (start_datetime - datetime.datetime(start_datetime.year, 1, 1)).days + 1
    end_day = (end_datetime - datetime.datetime(end_datetime.year, 1, 1)).days + 1

    # Build file list to read data
    file_list = []

    years = [start_datetime.year + i for i in range(end_datetime.year - start_datetime.year + 1)]

    # simple case, data within single year
    if len(years) == 1:
        file_list += _get_years_files(years[0], start_day, end_day)

    # start in one year, end in the next
    elif len(years) == 2:
        # might be leap year
        days_in_start_year = (datetime.date(start_datetime.year, 12, 31) -
                              datetime.date(start_datetime.year, 1, 1)).days
        file_list += _get_years_files(years[0], start_day, days_in_start_year)
        file_list += _get_years_files(years[1], 1, end_day)

    # start in one year, end in another, spanning 1 or more full years in between
    else:
        days_in_start_year = (datetime.date(start_datetime.year, 12, 31) -
                              datetime.date(start_datetime.year, 1, 1)).days
        file_list += _get_years_files(years[0], start_day, days_in_start_year)

        for year in years[1:-1]:
            days_in_year = (datetime.date(year, 12, 31) - datetime.date(year, 1, 1)).days
            file_list += _get_years_files(year, 1, days_in_year)

        file_list += _get_years_files(years[-1], 1, end_day)

    return file_list


def _get_years_files(year, start_day, end_day):
    """Get a years worth of files, given the year, start day, and end day.

    Args:
        year (int): year to get the files from
        start_day (int): day of year to start
        end_day (int): day of year to end

    Returns:
        list: list of 2-tuples with (filename, year) for files between start
              and end day for the given year

    """
    ret = []

    for day in range(start_day, end_day+1):
        # arbitrary format change on this day
        if year == 2018:
            if day <= 298:
                _file = DATA_LOCATION + "PWV/PWV_UCSC_{day}-{year}.txt".format(year=year, day=day)
                if os.path.isfile(_file):
                    ret.append((_file, year))
            else:
                _file = DATA_LOCATION + "PWV/PWV_UCSC_{year}-{day}.txt".format(year=year, day=day)
                if os.path.isfile(_file):
                    ret.append((_file, year))
        else:
            _file = DATA_LOCATION + "PWV/PWV_UCSC_{year}-{day}.txt".format(year=year, day=day)
            if os.path.isfile(_file):
                ret.append((_file, year))

    return ret


def julian_day_year_to_unixtime(day, year):
    """Convert radiometer's output Julian Day to unix timestamp.

    Args:
        day (float): day of the year
        year (int): year for corresponding day

    Returns:
        float: unix timestamp

    """
    a = datetime.datetime(year, 1, 1) + datetime.timedelta(day-1)
    unixtime = time.mktime(a.timetuple())
    return unixtime


def _read_data_from_disk(file_list):
    """Do the actual I/O. Meant to be called by blockingCallFromThread.

    Args:
        file_list (list): list of tuples with (file, year)

    Returns:
        dict: properly formatted dict for sisock to pass to grafana

    """
    _data = {'data': {}, 'timeline': {'pwv': {}}}
    _data['data']['pwv'] = []
    _data['timeline']['pwv']['t'] = []
    _data['timeline']['pwv']['finalized_until'] = None

    for (_f, year) in file_list:
        with open(_f, 'r') as f:
            i = 0
            for l in f.readlines():
                if i == 0:
                    pass  # skip header
                else:
                    line = l.strip().split()

                    timestamp = julian_day_year_to_unixtime(float(line[0]), year)
                    if line[1] != "NaN":
                        data = float(line[1])

                        _data['data']['pwv'].append(data)
                        _data['timeline']['pwv']['t'].append(timestamp)
                        _data['timeline']['pwv']['finalized_until'] = timestamp
                    else:
                        pass

                i += 1

    return _data


class apex_weather(sisock.base.DataNodeServer):
    """An example data node server, serving historic data.

    This example serves APEX weather data over a couple of weeks of July 2017
    from simple text files.

    Inhereits from :class:`sisock.base.data_node_server`.
    """
    # Here we set the name of this data node server.
    name = "ucsc_radiometer"
    description = "PWV readings from the UCSC radiometer."

    def get_data(self, field, start, end, min_stride=None):
        """Over-riding the parent class prototype: see the parent class for the
        API.

        The `min_step` parameter is not implemented, and there is no bandwidth
        throttling implemented.
        """
        start = sisock.base.sisock_to_unix_time(start)
        end = sisock.base.sisock_to_unix_time(end)

        # file_list = threads.blockingCallFromThread(reactor, _build_file_list, (start, end))
        # data = threads.blockingCallFromThread(reactor, _read_data_from_disk, (file_list))
        file_list = _build_file_list(start, end)
        print('Reading data from disk from {start} to {end}.'.format(start=start, end=end))
        data = _read_data_from_disk(file_list)
        # print(data)

        return data

    def get_fields(self, start, end):
        """Over-riding the parent class prototype: see the parent class for the
        API.

        Since we only have a single statistic to report, just make a single
        field and timeline with the name 'pwv'.

        """
        # single field called 'pwv'
        _field = {'pwv': {}}
        _timeline = {'pwv': {}}

        _field['pwv'] = {'description': 'PWV from UCSC Radiometer',
                         'timeline': 'pwv',
                         'type': 'number',
                         'units': 'mm'}

        _timeline['pwv'] = {'interval': 60.48,
                            'field': ['pwv']}

        # Debug printing. Do NOT leave on in production.
        # print("_timeline: {}".format(_timeline))
        # print("_field: {}".format(_field))

        return _field, _timeline


if __name__ == "__main__":
    # Give time for crossbar server to start
    time.sleep(5)

    # Because we're using a self-signed certificate, we need to tell Twisted
    # that it is OK to trust it.
    cert_fname = (".crossbar/server_cert.pem")
    cert = crypto.load_certificate(crypto.FILETYPE_PEM,
                                   six.u(open(cert_fname, 'r').read()))

    opt = CertificateOptions(trustRoot=OpenSSLCertificateAuthorities([cert]))

    # Start our component.
    runner = ApplicationRunner('wss://sisock_crossbar:8080/ws', sisock.base.REALM, ssl=opt)
    runner.run(apex_weather)
