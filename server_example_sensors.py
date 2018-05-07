"""
An example data node server.
"""

import glob
import os
import sisock
import six
import subprocess
import time
import threading
from autobahn.twisted.component import Component, run
from autobahn.twisted.util import sleep
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.wamp.types import RegisterOptions
from autobahn import wamp
from twisted.python.failure import Failure
from twisted.internet.task import LoopingCall
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions
from OpenSSL import crypto

field = []
data = []

class sensors(sisock.data_node_server):
    """An example data node server, serving live data.

    Inhereits from :class:`sisock.data_node_server`.
    """
    # Here we set the name of this data node server.
    name = "sensors"
    description = "The results of the UNIX 'sensors' command."
    field = []
    field_filled = False
    data = []
    loop_running = False

    def get_sensors(self):
        """The data collection loop.
        """
        d = subprocess.check_output(["sensors", "-u"])
        group = None
        for dd in d.splitlines():
            if not group:
                group = dd.strip()
                if not self.field_filled:
                    self.field.append({})
            else:
                i = dd.find("_input")
                if i > 0:
                    f = "%s_%s" % (group, dd[0:i].strip())
                    if not self.field_filled:
                        self.field[-1]["name"] = f
                        self.field[-1]["description"] = ""
                        self.field[-1]["timeline"] = "t"
                        self.field[-1]["type"] = "number"
                        self.field[-1]["units"] = "unknown"
                # Continue HERE: add to the circular buffer.
        self.field_filled = True

    def after_onJoin(self, details):
        """Over-riding the parent class, in order to run our data collection
        loop once we have joined the session.
        """
        # Read the sensors every second.
        LoopingCall(self.get_sensors).start(1)

    def last_update(self, field):
        """Over-riding the parent class prototype; see the parent class for the
        API.

        This function is not implemented yet in this example.
        """
        raise RuntimeError("This class is not yet functional.")

    def get_data(self, field, start, length, min_step=None):
        """Over-riding the parent class prototype: see the parent class for the
        API.
        
        The `min_step` parameter is not implemented, and there is no bandwidth
        throttling implemented.
        """
        raise RuntimeError("This class is not yet functional.")

    def get_fields(self, t):
        """Over-riding the parent class prototype: see the parent class for the
        API."""
        raise RuntimeError("This class is not yet functional.")


if __name__ == "__main__":
    # Because we're using a self-signed certificate, we need to tell Twisted
    # that it is OK to trust it.
    cert_fname = (".crossbar/server_cert.pem")
    cert = crypto.load_certificate(crypto.FILETYPE_PEM,
                                   six.u(open(cert_fname, 'r').read()))

    opt = CertificateOptions(trustRoot=OpenSSLCertificateAuthorities([cert]))

    # Start reading the sensors

    # Start our component.
    runner = ApplicationRunner(sisock.WAMP_URI, sisock.REALM, ssl=opt)
    runner.run(sensors)
