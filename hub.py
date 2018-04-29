"""
================================================================================
Sisock hub (:mod:`hub`)
================================================================================

.. currentmodule:: hub

Classes
=======

.. autosummary::
    :toctree: generated/

    hub
"""

from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger
from twisted.python.failure import Failure

from autobahn.twisted.util import sleep
from autobahn.twisted.wamp import ApplicationSession
from autobahn.wamp.exception import ApplicationError
from autobahn import wamp
from autobahn.wamp import auth

import numpy as np
import re
import sisock

from spt3g import core as ser

class hub(ApplicationSession):
    """The sisock hub that keeps track of available data node servers..

    Inherets from :class:`autobahn.twisted.wamp.ApplicationSession`

    Attributes
    ----------
    data_node : list
        A list of tuples (name, session_id) containing the names of all the
        available data nodes and the WAMP sessions they are associated with.

    Methods
    -------
    onJoin
    onConnect
    onChallenge
    check_data_node_leave
    add_data_node
    subtract_data_node
    check_subtract_data_node
    """
    # --------------------------------------------------------------------------
    # Attributes
    # --------------------------------------------------------------------------

    data_node = []


    # --------------------------------------------------------------------------
    # Methods inherited from ApplicationSession
    # --------------------------------------------------------------------------

    @inlineCallbacks
    def onJoin(self, details):
        """Fired when the session joins WAMP (after successful authentication).

        Parameters
        ----------
        details : :class:`autobahn.wamp.types.SessionDetails`
            Details about the session.
        """

        reg = yield self.register(self)
        for r in reg:
            if isinstance(r, Failure):
                self.log.error("Failed to register procedure: %s." % (r.value))
            else:
                self.log.info("Registration ID %d: %s." % (r.id, r.procedure))

        sub = yield self.subscribe(self)
        self.log.info("Subscribing to topics.")
        for s in sub:
            if isinstance(sub, Failure):
                self.log.error("Subscribe failed: %s." % (s.getErrorMessage()))


    def onConnect(self):
        """Fired when session first connects to WAMP router.""" 
        self.log.info("Client session connected.")
        self.join(self.config.realm, [u"wampcra"], sisock.WAMP_USER)


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

            # Compute signature for challenge, using the key
            signature = auth.compute_wcs(sisock.WAMP_SECRET,
                                         challenge.extra["challenge"])

            # Return the signature to the router for verification
            return signature
        else:
            raise Exception("Invalid authmethod {}".format(challenge.method))


    # --------------------------------------------------------------------------
    # Pub/sub and metaevent subscriptions.
    # --------------------------------------------------------------------------

    @wamp.subscribe("wamp.session.on_leave")
    def check_data_node_leave(self, ev):
        """Fires when a WAMP session leaves and checks if whether it was
        running a data node server.

        This method fires when any WAMP session disconnects. It checks to see if
        that session had added a data node. If yes, and the session neglected to
        subtract the data node before disconnecting, this method subtracts it.

        Parameters
        ----------
        ev : string
            The session ID.
        """

        n = [i for i in self.data_node]# if i[1] == ev]
        if len(n):
            self.log.info("Session \"%s\" controlling data node \"%s\" was "
                          "disconnected." % (ev, n[0][0]))
            if len(n) > 1:
                self.log.error("More than one data node was associated with " +\
                               "the session. Removing the first. This is an " +\
                               "error that needs to be debugged.")
            self.check_subtract_data_node(n[0][0], n[0][1])


    # --------------------------------------------------------------------------
    # RPC registrations.
    # --------------------------------------------------------------------------

    @wamp.register(sisock.uri("data_node.add"))
    def add_data_node(self, name, session_id):
        """Request the addition a new data node server.
        
        Parameters
        ----------
        name : string
            The unique name of the data node server.
        session_id : string
            The ID of the WAMP session running the server.

        Returns
        -------
        status : bool
            True on success; false if the data node server name has already been
            added.
        """
        self.log.info("Received request to add data node \"%s\"." % name)
        # Check that this data node has not yet been registered.
        if len([i for i in self.data_node if i[0] == name]):
            self.log.warn("Data node \"%s\" already exists. " % (name) +\
                          "Denying request.")
            return False

        self.data_node.append((name, session_id))
        self.log.info("Added data node \"%s\"." % name)
        return True


    @wamp.register(sisock.uri("data_node.subtract"))
    def subtract_data_node(self, name, session_id):
        """Request the removal of a data node server.

        Removes a data node server, if it exists.

        Parameters
        ----------
        name : string
            The unique name of the data node server.
        session_id : string
            The ID of the WAMP session running the server.
        """
        self.log.info("Received request to remove data node \"%s\"." % name)
        self.check_subtract_data_node(name, session_id)
        return


    # --------------------------------------------------------------------------
    # Helper methods.
    # --------------------------------------------------------------------------

    def check_subtract_data_node(self, name, session_id):
        """Remove a data node server if it exists.

        A convenience method to avoid repeating the same code in
        `subtract_data_node` and `check_data_node_leave`.

        Parameters
        ----------
        name : string
            The unique name of the data node server.
        session_id : string
            The ID of the WAMP session running the server.
        """
        if (name, session_id) in self.data_node:
            self.data_node.remove((name, session_id))
            self.log.info("Removed data node \"%s\"." % (name))
        else:
            self.log.warn("Data done \"%s\" was never added. Doing nothing." %\
                          (name))
