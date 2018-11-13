"""
Sisock: serve Simons data over secure sockets (:mod:`sisock`)

.. currentmodule:: sisock

Classes
=======
.. autosummary::
    sisock.base.DataNodeServer

Functions
=========
.. autosummary::
   sisock.base.uri
   sisock.base.sisock_to_unix_time

Constants
=========
:const:`WAMP_USER`
    Username for servers/hub to connect to WAMP router.
:const:`WAMP_SECRET`
    Password for servers/hub to connect to WAMP router.
:const:`WAMP_URI`
    Address of WAMP router.
:const:`REALM`
    Realm in WAMP router to connect to.
:const:`BASE_URI`
    The lowest level URI for all pub/sub topics and RPC registrations.
"""

import six
import time
from autobahn.twisted.component import Component, run
from autobahn.twisted.util import sleep
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.wamp.types import RegisterOptions
from autobahn import wamp
from twisted.python.failure import Failure
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import threads

WAMP_USER   = u"server"
WAMP_SECRET = u"Q5#x4%HCmgTsS!Pj"
WAMP_URI    = u"wss://127.0.0.1:8080/ws"
REALM       = u"test_realm"
BASE_URI        = u"org.simonsobservatory"

def uri(s):
    """Compose a full URI for pub/sub or RPC calls.

    Parameters
    ----------
    s : The final part of the URI to compose.

    Returns
    -------
    uri : string
       The string returned is "%s.%s" % (BASE_URI, s).
    """
    return u"%s.%s" % (BASE_URI, s)


def sisock_to_unix_time(t):
    """Convert a sisock timestamp to a UNIX timestamp.

    Parameters
    ----------
    t : float
        A sisock timestamp.

    Returns
    -------
    unix_time : float
        If `t` is positive, return `t`. If `t` is zero or negative, return
        :math:`time.time() - t`.
    """
    if t > 0:
        return t
    else:
        return time.time() + t

class DataNodeServer(ApplicationSession):
    """Parent class for all data node servers.

    Attributes
    ----------
    name : string
        Each data node server inheriting this class must set its own name. The
        hub will reject duplicate names.
    description : string
        Each data node server inheriting this class must provide its own, human-
        readable description for consumers.
    """

    name = None
    description = None

    @inlineCallbacks
    def onJoin(self, details):
        """Fired when the session joins WAMP (after successful authentication).

        After registering procedures, the hub is requested to add this data node
        server.

        Parameters
        ----------
        details : :class:`autobahn.wamp.types.SessionDetails`
            Details about the session.
        """
        self.log.info("Successfully joined WAMP.")

        proc = [(self.get_fields, uri("consumer." + self.name + ".get_fields")),
                (self.get_data, uri("consumer." + self.name + ".get_data"))]
        for p in proc:
            try:
                yield self.register(p[0], p[1])
                self.log.info("Registered procedure %s." % p[1])
            except Exception as e:
                self.log.error("Could not register procedure: %s." % (e))

        # Tell the hub that we are ready to serve data.
        try:
            res = yield self.call(uri("data_node.add"), self.name,
                                  self.description, details.session)
            if not res:
                self.log.warn("Request to add data node denied.")
            else:
                self.log.info("Data node registered as \"%s\"." % self.name)
        except Exception as e:
            self.log.error("Call error: %s." % e)

        self.after_onJoin(details)


    def onConnect(self):
        """Fired when session first connects to WAMP router."""
        self.log.info("Client session connected.")
        self.join(self.config.realm, [u"wampcra"], WAMP_USER)


    def onChallenge(self, challenge):
        """Fired when the WAMP router requests authentication.

        Parameters
        ----------
        challenge : :class:`autobahn.wamp.types.Challenge`
            The authentication request to be responded to.

        Returns
        -------
        signature : string
            The authentication response.
        """
        if challenge.method == u"wampcra":
            self.log.info("WAMP-CRA challenge received.")

            # compute signature for challenge, using the key
            signature = wamp.auth.compute_wcs(WAMP_SECRET,
                                              challenge.extra["challenge"])

            # return the signature to the router for verification
            return signature
        else:
            raise Exception("Invalid authmethod {}".format(challenge.method))

    def after_onJoin(self, details):
        """This method is called after onJoin() has finished.

        This method can be overriden by child classes that need to run more code
        after the parent onJoin method has run.

        Parameters
        ----------
        details : :class:`autobahn.wamp.types.SessionDetails`
            Details about the session, as passed to onJoin.
        """
        pass


    def get_fields(self, start, end):
        """Get a list of available fields and associated timelines available 
        within a time interval.

        Any field that has at least one available sample in the interval
        `[start, stop)` must be included in the reply; however, be aware that
        the data server is allowed to include fields with zero samples available
        in the interval.

        This method must be overriden by child classes.

        Parameters
        ----------
        start : float
            The start time for the field list. If positive, interpret as a
            UNIX time; if 0 or negative, get field list `t` seconds ago.
        end : float
            The end time for the field list, using the same format as `start`.

        Returns
        -------
        dictionary
            Two dictionaries of dictionaries, as defined below.

            - field : the field name is the key, and the value is:
                - description : information about the field; can be `None`.
                - timeline : the name of the timeline this field follows.
                - type : one of "number", "string", "bool"
                - units : the physical units; can be `None`
            - timeline : the field name is the key, and the value is:
                - interval : the average interval, in seconds, between
                  readings; if the readings are aperiodic, :obj:`None`.
                - field : a list of field names associated with this timeline

            The `field` dictionary can be empty, indicating that no fields are 
            available during the requested interval.
        """
        raise RuntimeError("This method must be overriden.")


    @inlineCallbacks
    def get_data(self, field, start, end, min_stride=None):
        """Request data.

        This method must be overriden by child classes.

        Parameters
        ----------
        field      : list of strings
                     The list of fields you want data from.
        start      : float
                     The start time for the data: if positive, interpret as a 
                     UNIX time; if 0 or negative, begin `start` seconds ago.
        end        : float
                     The end time for the data, using the same format as
                     `start`.
        min_stride : float or :obj:`None`
                     If not :obj:`None` then, if necessary, downsample data
                     such that successive samples are separated by at least
                     `min_stride` seconds.

        Returns
        -------
        dictionary
            On success, a dictionary is returned with two entries.

            - data : A dictionary with one entry per field:
                - field_name : array containing the timestream of data.
            - timeline : A dictionary with one entry per timeline:
                - timeline_name : An dictionary with the following entries.
                - t : an array containing the timestamps
                - finalized_until : the timestamp prior to which the presently
                  requested data are guaranteed not to change; :obj:`None` may 
                  be returned if all requested data are finalized

            If data are not available during the whole length requested, all
            available data will be returend; if no data are available for a 
            field, or the field does not exist, its timestream will be an empty 
            array. Timelines will only be included if there is at least one 
            field to which it corresponds with available data. If no data are 
            available for any of the fields, all arrays will be empty.

            If the amount of data exceeds the data node server's pipeline
            allowance,
            :obj:`False` will be returned.
        """
        start = sisock_to_unix_time(start)
        end = sisock_to_unix_time(end)

        data = yield threads.deferToThread(self.get_data_blocking, field, start, end, min_stride)
        returnValue(data)


    def get_data_blocking(self, field, start, end, min_stride=None):
        """Request data.

        This method must be overriden by child classes.

        Parameters
        ----------
        field      : list of strings
                     The list of fields you want data from.
        start      : float
                     The start time for the data: if positive, interpret as a 
                     UNIX time; if 0 or negative, begin `start` seconds ago.
        end        : float
                     The end time for the data, using the same format as
                     `start`.
        min_stride : float or :obj:`None`
                     If not :obj:`None` then, if necessary, downsample data
                     such that successive samples are separated by at least
                     `min_stride` seconds.

        Returns
        -------
        dictionary
            On success, a dictionary is returned with two entries.

            - data : A dictionary with one entry per field:
                - field_name : array containing the timestream of data.
            - timeline : A dictionary with one entry per timeline:
                - timeline_name : An dictionary with the following entries.
                - t : an array containing the timestamps
                - finalized_until : the timestamp prior to which the presently
                  requested data are guaranteed not to change; :obj:`None` may 
                  be returned if all requested data are finalized

            If data are not available during the whole length requested, all
            available data will be returend; if no data are available for a 
            field, or the field does not exist, its timestream will be an empty 
            array. Timelines will only be included if there is at least one 
            field to which it corresponds with available data. If no data are 
            available for any of the fields, all arrays will be empty.

            If the amount of data exceeds the data node server's pipeline
            allowance,
            :obj:`False` will be returned.
        """
        raise RuntimeError("This method must be overriden.")
