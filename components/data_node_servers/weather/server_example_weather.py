"""
An example data node server.
"""

import glob
import os
import six
import time

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

import sisock

class apex_weather(sisock.base.DataNodeServer):
    """An example data node server, serving historic data.

    This example serves APEX weather data over a couple of weeks of July 2017
    from simple text files.

    Inhereits from :class:`sisock.base.data_node_server`.
    """
    # Here we set the name of this data node server.
    name = "apex_archive"
    description = "Archived APEX weather."

    def get_data(self, field, start, end, min_stride=None):
        """Over-riding the parent class prototype: see the parent class for the
        API.
        
        The `min_step` parameter is not implemented, and there is no bandwidth
        throttling implemented.
        """
        ret = {"data": {}, "timeline": {}}
        start = sisock.base.sisock_to_unix_time(start)
        end = sisock.base.sisock_to_unix_time(end)
        for f in field:
            ret["data"][f] = []
            try:
                with open("./example_data/%s.dat" % f) as fp:
                    i = 0
                    timeline = None
                    t_last = None
                    for l in fp.readlines():
                        if i == 1:
                            tl = l.replace("# ", "").strip()
                            try:
                                dummy = ret["timeline"][tl]
                            except KeyError:
                                timeline = tl
                                ret["timeline"][timeline] = {"t": []}
                        i += 1
                        if l[0] == "#":
                            continue
                        t = float(l.split()[0])
                        if t >= start and t < end:
                            if timeline:
                                ret["timeline"][timeline]["t"].append(t)
                            ret["data"][f].append(float(l.split()[1]))
                        t_last = t
                    if timeline:
                        ret["timeline"][timeline]["finalized_until"] = t_last
            except IOError:
                # Silently pass over a requested field that doesn't exist.
                pass
        return ret


    def get_fields(self, start, end):
        """Over-riding the parent class prototype: see the parent class for the
        API."""
        field = {}
        timeline = {}
        start = sisock.base.sisock_to_unix_time(start)
        end = sisock.base.sisock_to_unix_time(end)
        for path in glob.glob("./example_data/*.dat"):
            name = os.path.split(path)[1].replace(".dat", "")
            f = {"type": "number"}
            with open(path) as fp:
                i = 0
                field_available = False
                last_t = 0
                for l in fp.readlines():
                    if i == 0:
                        f["description"] = l.replace("# ", "").strip()
                    if i == 1:
                        f["timeline"] = l.replace("# ", "").strip()
                    if i == 2:
                        f["units"] = l.replace("# ", "").strip()
                    i += 1
                    if l[0] == "#":
                      continue
                    t = float(l.split()[0])
                    if t >= start and t < end:
                        field_available = True
                        break
                    last_t = t
            if field_available:
                field[name] = f
                try:
                    timeline[f["timeline"]]["field"].append(name)
                except KeyError:
                    timeline[f["timeline"]] = {"interval": t - last_t,
                                               "field": [name]}
        return field,timeline


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
    runner = ApplicationRunner("wss://%s:%d/ws" % (sisock.base.SISOCK_HOST, \
                                                   sisock.base.SISOCK_PORT), \
                               sisock.base.REALM, ssl=opt)
    runner.run(apex_weather)
