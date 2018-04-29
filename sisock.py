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
        In this parent class, name = `None`. Each data node server inheriting
        this class must set its own name. The hub will reject duplicate
        names.

    Methods
    -------
    onJoin
    onConnect
    onChallenge
    """

    name = None

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
        reg = yield self.register(self)
        for r in reg:
            if isinstance(r, Failure):
                print("Failed to register procedure: %s." % (r.value))
            else:
                print("Registration ID %d: %s." % (r.id, r.procedure))

        # Tell the hub that we are ready to serve data.
        try:
            res = yield self.call(uri("data_node.add"), self.name,
                                      details.session)
            if not res:
                self.log.warn("Request to add data node denied.")
            else:
                self.log.info("Data node registered as \"%s\"." % self.name)
        except Exception as e:
            self.log.error("Call error: %s." % e)


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
