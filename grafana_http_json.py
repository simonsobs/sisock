from autobahn.twisted.component import Component
import dateutil.parser
import json
from klein import Klein
from OpenSSL import crypto
import numpy as np
import sisock
import six
from twisted.internet.defer import inlineCallbacks, Deferred
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.web.server import Site
from twisted.internet.task import react
from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions

class WebApplication(object):
    """
    A simple Web application that publishes an event every time the
    url "/" is visited.
    """
    def __init__(self, app, wamp_comp):
        self._app = app
        self._wamp = wamp_comp
        self._session = None  # "None" while we're disconnected from WAMP router
        self._stored_field = {}

        # associate ourselves with WAMP session lifecycle
        self._wamp.on('join', self._initialize)
        self._wamp.on('leave', self._uninitialize)
        # hook up Klein routes
        self._app.route(u"/", branch=True)(self._ping)
        self._app.route(u"/search", branch=True)(self._search)
        self._app.route(u"/query", branch=True)(self._query)

    def _initialize(self, session, details):
        print("Connected to WAMP router")
        self._session = session

    def _uninitialize(self, session, reason):
        print(session, reason)
        print("Lost WAMP connection")
        self._session = None

    @inlineCallbacks
    def _query(self, request):
        if self._session is None:
            request.setResponseCode(500)
            return b"No WAMP session\n"
        print("Web client requested /query.")
        content = yield request.content.read()
        req = json.loads(content)
        t_start_d = dateutil.parser.parse(req["range"]["from"])
        t_start = float(t_start_d.strftime("%s"))
        t_end_d = dateutil.parser.parse(req["range"]["to"])
        t_end = float(t_end_d.strftime("%s"))
        poll = {}
        print("%s / %s :: %f --- %f" % (req["range"]["from"], req["range"]["to"], t_start, t_end))
        for target in req["targets"]:
            data_node, field = target["target"].split("::")
            if data_node not in poll.keys():
                poll[data_node] = []
            poll[data_node].append(field)

        res = []
        for data_node, field in poll.items():
            data = yield self._session.call(sisock.uri("consumer." + \
                                                       data_node + ".get_data"),
                                            field, t_start, t_end)
            for f in field:
                tl_name = self._stored_field[data_node][0][f]["timeline"]
                tl = np.array(data["timeline"][tl_name]["t"]) * 1000.0
                d = {"target": data_node + "::" + f,
                     "datapoints": list(zip(data["data"][f], tl))}
                res.append(d)
        ret = json.dumps(res)
        print(ret)
        return ret


    @inlineCallbacks
    def _search(self, request):
        if self._session is None:
            request.setResponseCode(500)
            return b"No WAMP session\n"
        print("Web client requested /search.")
        field = []
        data_node = yield \
          self._session.call(sisock.uri("consumer.get_data_node"))
        self._stored_field_list = {}
        for dn in data_node:
            f = yield self._session.call(sisock.uri("consumer." + dn["name"] + \
                                                    ".get_fields"), 1, 0)
            for field_name in f[0].keys():
                field.append(dn["name"] + "::" + field_name)
            self._stored_field[dn["name"]] = f
        ret = yield json.dumps(field)
        print("Result for /search: %s." % ret)
        return ret

    def _ping(self, request):
        if self._session is None:
            request.setResponseCode(500)
            return b"No WAMP session\n"
#        self._session.publish(u"com.myapp.request_served")
        return b"Published to 'com.myapp.request_served'\n"


@inlineCallbacks
def main(reactor):
    # Because we're using a self-signed certificate, we need to tell Twisted
    # that it is OK to trust it.
    cert_fname = (".crossbar/server_cert.pem")
    cert = crypto.load_certificate(crypto.FILETYPE_PEM,
                                   six.u(open(cert_fname, 'r').read()))

    opt = CertificateOptions(trustRoot=OpenSSLCertificateAuthorities([cert]))

    component = Component(
        transports=[
            {
                u"type": u"websocket",
                u"url": sisock.WAMP_URI,
                u"endpoint": {
                  u"type": u"tcp",
                  u"host": u"127.0.0.1",
                  u"port": 8080,
                  u"tls": opt
                }
            }
        ],
        authentication={
            u"wampcra": {
                u"authid": u"simonsobs",
                u"secret": u"yW4V2T^bPD&rGFwy"
            }
        },
        realm=sisock.REALM,
    )
    app = Klein()
    WebApplication(app, component)

    # have our Web site listen on 5000.
    site = Site(app.resource())
    server_ep = TCP4ServerEndpoint(reactor, 5000)
    port = yield server_ep.listen(site)
    print("Web application on {}".format(port))

    # we don't *have* to hand over control of the reactor to
    # component.run -- if we don't want to, we call .start()
    # The Deferred it returns fires when the component is "completed"
    # (or errbacks on any problems).
    comp_d = component.start(reactor)

    # When not using run() we also must start logging ourselves.
    import txaio
    txaio.start_logging(level='info')

    # If the Component raises an exception we want to exit. Note that
    # things like failing to connect will be swallowed by the
    # re-connection mechanisms already so won't reach here.

    def _failed(f):
        print("Component failed: {}".format(f))
        done.errback(f)
    comp_d.addErrback(_failed)

    # wait forever (unless the Component raises an error)
    done = Deferred()
    yield done


if __name__ == '__main__':
    react(main)
