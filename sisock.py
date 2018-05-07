"""
================================================================================
Sisock: serve Simons data over secure sockets (:mod:`sisock`)
================================================================================

.. currentmodule:: sisock

Classes
=======

.. autosummary::
    :toctree: generated/

    data_node_server

Functions
=========

.. autosummary::
   :toctree: generated/

   uri

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
from autobahn.twisted.component import Component, run
from autobahn.twisted.util import sleep
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.wamp.types import RegisterOptions
from autobahn import wamp
from twisted.python.failure import Failure
from twisted.internet.defer import inlineCallbacks, returnValue

WAMP_USER   = u"server"
WAMP_SECRET = u"Q5#x4%HCmgTsS!Pj"
WAMP_URI    = u"wss://127.0.0.1:8080/ws"
REALM       = u"sisock"
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

class data_node_server(ApplicationSession):
    """Parent class for all data node servers.

    Attributes
    ----------
    name : string
        Each data node server inheriting this class must set its own name. The
        hub will reject duplicate names.
    description : string
        Each data node server inheriting this class must provide its own, human-
        readable description for consumers.

    Methods
    -------
    onJoin
    onConnect
    onChallenge
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
                (self.get_data, uri("consumer." + self.name + ".get_data")),
                (self.last_update, 
                 uri("consumer." + self.name + ".last_update"))]
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


    def get_fields(self, t):
        """Get a list of available fields at a given time.

        This method must be overriden by child classes.

        Parameters
        ----------
        t : float
            The time at which to get the field list. If positive, interpret as a
            UNIX time; if 0 or negative, get field list `t` seconds ago.

        Returns
        -------
        field : list of dictionaries
            For each available field, a dictionary with the following entries is
            provided:
            - name        : the field name
            - description : information about the field; can be `None`.
            - timeline    : the name of the timeline used by this field
            - type        : one of "number", "string", "bool"
            - units       : the physical units; can be `None`
            The list can be empty, indicating that no fields are available at
            that time.
        """
        raise RuntimeError("This method must be overriden.")

    def get_data(self, field, start, length, min_stride=None):
        """Request data.

        This method must be overriden by child classes.

        Parameters
        ----------
        field      : list of strings
                     The list of fields you want data from.
        start      : float
                     The start time for the data: if positive, interpret as a 
                     UNIX time; if 0 or negative, start `t_start` seconds ago.
        length     : float
                     The number of seconds worth of data to request.
        min_stride : float or :obj:`None`
                     If not :obj:`None` then, if necessary, downsample data
                     such that successive samples are separated by at least
                     `min_stride` seconds.

        Returns
        -------
        On success, a dictionary is returned with two entries
        - data : A dictionary with one entry per field:
          - field_name : array containing the timestream of data.
        - timeline : A dictionary with one entry per timeline:
          - timeline_name : An array with timestamps.

        If data are not available during the whole length requested, all
        available data will be returend; if no data are available for a field,
        or the field does not exist, its timestream will be an empty array.
        Timelines will only be included if there is at least one field to which
        it corresponds with available data. If no data are available for any of 
        the fields, all arrays will be empty.

        If the amount of data exceeds the data node server's pipeline allowance,
        :obj:`False` will be returned.
        """
        raise RuntimeError("This method must be overriden.")

    def last_update(self, field):
        """Ask when fields were last updated.

        This method must be overriden by child classes.

        Parameters
        ----------
        field : list of strings
            The fields to query.

        Returns
        -------
        t : list
            For each field, return a UNIX time representing the timestamp of the
            most recent datum. If the field name is unrecognised, :obj:`None` is
            reported.
        """
        raise RuntimeError("This method must be overriden.")
