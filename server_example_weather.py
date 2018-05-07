"""
An example data node server.
"""

import glob
import os
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

class apex_weather(sisock.data_node_server):
    """An example data node server, serving historic data.

    This example serves APEX weather data over a couple of weeks of July 2017
    from simple text files.

    Inhereits from :class:`sisock.data_node_server`.
    """
    # Here we set the name of this data node server.
    name = "apex_archive"
    description = "Archived APEX weather."

    def last_update(self, field):
        """Over-riding the parent class prototype; see the parent class for the
        API.

        This function is not implemented yet in this example.
        """
        raise RuntimeError("Not implemented.")

    def get_data(self, field, start, length, min_step=None):
        """Over-riding the parent class prototype: see the parent class for the
        API.
        
        The `min_step` parameter is not implemented, and there is no bandwidth
        throttling implemented.
        """
        ret = {"data": {}, "timeline": {}}
        print(field)
        for f in field:
            ret["data"][f] = []
            try:
                with open("./example_data/%s.dat" % f) as fp:
                    i = 0
                    timeline = None
                    for l in fp.readlines():
                        if i == 1:
                            tl = l.replace("# ", "").strip()
                            try:
                                dummy = ret["timeline"][tl]
                            except KeyError:
                                timeline = tl
                                ret["timeline"][timeline] = []
                        i += 1
                        if l[0] == "#":
                            continue
                        t = float(l.split()[0])
                        if t >= start and t <= start + length:
                            if timeline:
                                ret["timeline"][timeline].append(t)
                            ret["data"][f].append(float(l.split()[1]))
            except IOError:
                pass
        return ret


    def get_fields(self, t):
        """Over-riding the parent class prototype: see the parent class for the
        API."""
        ret = []
        for path in glob.glob("./example_data/*.dat"):
            field = {"name": os.path.split(path)[1].replace(".dat", ""),
                     "type": "number"}
            print(path)
            with open(path) as fp:
                i = 0
                t_less = False
                field_available = False
                for l in fp.readlines():
                    if i == 0:
                        field["description"] = l.replace("# ", "").strip()
                    if i == 1:
                        field["timeline"] = l.replace("# ", "").strip()
                    if i == 2:
                        field["units"] = l.replace("# ", "").strip()
                    i += 1
                    if l[0] == "#":
                      continue
                    if not t_less:
                        if float(l.split()[0]) < t:
                            t_less = True
                    else:
                        if float(l.split()[0]) > t:
                            field_available = True
                            break
                    i += 1
            if field_available:
                ret.append(field)
        print(ret)
        return ret


if __name__ == "__main__":
    # Because we're using a self-signed certificate, we need to tell Twisted
    # that it is OK to trust it.
    cert_fname = (".crossbar/server_cert.pem")
    cert = crypto.load_certificate(crypto.FILETYPE_PEM,
                                   six.u(open(cert_fname, 'r').read()))

    opt = CertificateOptions(trustRoot=OpenSSLCertificateAuthorities([cert]))

    # Start our component.
    runner = ApplicationRunner(sisock.WAMP_URI, sisock.REALM, ssl=opt)
    runner.run(apex_weather)
