"""
An example data node server.
"""

import sisock
import six
from autobahn.twisted.component import Component, run
from autobahn.twisted.util import sleep
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.wamp.types import RegisterOptions
from autobahn import wamp
from twisted.python.failure import Failure
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions
from OpenSSL import crypto

class example1(sisock.data_node_server):
    """The example1 data node server.

    Inhereits from :class:`sisock.data_node_server`.
    """
    # Here we set the name of this data node server.
    name = "example1"
    

if __name__ == "__main__":
    # Because we're using a self-signed certificate, we need to tell Twisted
    # that it is OK to trust it.
    cert_fname = (".crossbar/server_cert.pem")
    cert = crypto.load_certificate(crypto.FILETYPE_PEM,
                                   six.u(open(cert_fname, 'r').read()))

    opt = CertificateOptions(trustRoot=OpenSSLCertificateAuthorities([cert]))

    # Start our component.
    runner = ApplicationRunner(sisock.WAMP_URI, sisock.REALM, ssl=opt)
    runner.run(example1)
