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

class sensors(sisock.DataNodeServer):
    """An example data node server, serving live data.

    Inhereits from :class:`sisock.data_node_server`.
    """
    # Here we set the name of this data node server.
    name = "sensors"
    description = "The results of the UNIX 'sensors' command."
    field = {}
    field_filled = False
    data_depth = 1800
    data = {}
    interval = 2.5
    timeline = {"t": {"field": [],
                      "interval": interval}}
    t = [None for i in range(data_depth)]
    finalized_until = None
    loop_running = False

    def get_sensors(self):
        """The data collection loop.
        """
        d = subprocess.check_output(["sensors", "-u"])
        group = None
        self.t.pop(0)
        self.t.append(time.time())
        for dd in d.splitlines():
            l = dd.decode("ascii").strip()
            if not len(l):
              group = None
              continue
            if not group:
                group = l.strip()
            else:
                i = l.find("_input")
                if i > 0:
                    f = "%s_%s" % (group, l[0:i].strip())
                    if not self.field_filled:
                        self.field[f] = {}
                        self.field[f]["name"] = f
                        self.field[f]["description"] = ""
                        self.field[f]["timeline"] = "t"
                        self.field[f]["type"] = "number"
                        self.field[f]["units"] = "unknown"
                        self.data[f] = [None for i in range(self.data_depth)]
                        self.timeline["t"]["field"].append(f)
                    self.data[f].pop(0)
                    self.data[f].append(float(l.split()[1].strip()))
            if not self.finalized_until:
                self.finalized_until = self.t[-1]
            elif self.t[-1] - self.finalized_until > 10.0:
                self.finalized_until = self.t[-1]
        self.field_filled = True

    def after_onJoin(self, details):
        """Over-riding the parent class, in order to run our data collection
        loop once we have joined the session.
        """
        # Read the sensors every second.
        LoopingCall(self.get_sensors).start(self.interval)

    def get_data(self, field, start, end, min_stride=None):
        """Over-riding the parent class prototype: see the parent class for the
        API.
        
        There is no bandwidth throttling implemented.
        """
        ret = {"data": {}, "timeline": {}}
        if not self.finalized_until or field == None:
            return ret
        start = sisock.sisock_to_unix_time(start)
        end = sisock.sisock_to_unix_time(end)
        if min_stride:
            stride = int(min_stride / self.interval)
            if stride < 1:
                stride = 1
        else:
            stride = 1
        timeline_done = False
        for f in field:
            ret["data"][f] = []
            try:
                if not timeline_done:
                    ret["timeline"]["t"] = \
                      {"t": [], "finalized_until": self.finalized_until}
                i = -1
                for datum, t in zip(self.data[f], self.t):
                    i += 1
                    if i % stride != 0:
                        continue
                    if not t:
                        continue
                    if t >= start and t < self.finalized_until \
                                  and t < end:
                        ret["data"][f].append(datum)
                        if not timeline_done:
                            ret["timeline"]["t"]["t"].append(t)
                timeline_done = True
            except KeyError:
                # Silently pass over a requested field that doesn't exist.
                pass
        return ret


    def get_fields(self, start, end):
        """Over-riding the parent class prototype: see the parent class for the
        API."""
        if not self.finalized_until:
            return {}, {}

        start = sisock.sisock_to_unix_time(start)
        end = sisock.sisock_to_unix_time(end)
        for tt in self.t:
            if tt:
                if tt >= start and self.finalized_until >= start \
                               and tt < end:
                    return self.field, self.timeline
        return {}, {}


if __name__ == "__main__":
    # Because we're using a self-signed certificate, we need to tell Twisted
    # that it is OK to trust it.
    cert_fname = (".crossbar/server_cert.pem")
    cert = crypto.load_certificate(crypto.FILETYPE_PEM,
                                   six.u(open(cert_fname, 'r').read()))

    opt = CertificateOptions(trustRoot=OpenSSLCertificateAuthorities([cert]))

    # Start reading the sensors

    # Start our component.
    runner = ApplicationRunner('wss://sisock_crossbar:8080/ws', sisock.REALM, ssl=opt)
    runner.run(sensors)
