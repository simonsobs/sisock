from autobahn.twisted.component import Component
import dateutil
import dateutil.parser
import json
from klein import Klein
from OpenSSL import crypto
import numpy as np
import pytz
import sisock
import six
from twisted.internet.defer import inlineCallbacks, Deferred
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.web.server import Site
from twisted.internet.task import react
from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions

def iso_to_unix_time(t):
    t_d = dateutil.parser.parse(t)
    t_dl = t_d.astimezone(dateutil.tz.tzlocal())
    return float(t_dl.strftime("%s"))

class GrafanaSisockDatasrc(object):
    """
    A web server to provide Grafana with data from sisock.
    """
    def __init__(self, app, wamp_comp):
        self._app = app
        self._wamp = wamp_comp
        self._session = None  # "None" while not connected to WAMP.
        self._field = {} # The current field list.
        self._json_field_list = ""

        # Associate ourselves with WAMP session lifecycle
        self._wamp.on('join', self._initialize)
        self._wamp.on('leave', self._uninitialize)

        # Our addresses hosted by Klein.
        self._app.route(u"/", branch=True)(self._ping)
        self._app.route(u"/search", branch=True)(self._search)
        self._app.route(u"/query", branch=True)(self._query)

    @inlineCallbacks
    def _initialize(self, session, details):
        print("Connected to WAMP router.")
        self._session = session

        # Populate the field list.
        self._field = {}

        # Get list of all data nodes connected to sisock.
        data_node = yield \
          self._session.call(sisock.uri("consumer.get_data_node"))
        print("Found %d data node%s: getting fields." % (len(data_node),
              "s" if len(data_node) != 1 else ""))

        for dn in data_node:
            # Get all fields for this data_node. We search for all times (start
            # = 1, end = 0) to get all possible fields.
            f = yield self._session.call(sisock.uri("consumer." + dn["name"] + \
                                                    ".get_fields"), 1, 0)
            self._field[dn["name"]] = f
        self._remake_json_field_list()

        # Subscribe to notifications from sisock hub.
        try:
            yield self._session.subscribe(self._data_node_added,
                      sisock.uri("consumer.data_node_added"))
            print("Subscribed to consumer.data_node_added.")
            yield self._session.subscribe(self._data_node_subtracted,
                      sisock.uri("consumer.data_node_subtracted"))
            print("Subscribed to consumer.data_node_subtracted.")
        except Exception as e:
            print("Could not subscribe to topic: %s." % e)

    def _uninitialize(self, session, reason):
        print(session, reason)
        print("Lost WAMP connection")
        self._session = None

    def _remake_json_field_list(self):
        field = []
        for dn, f in self._field.items():
            for field_name in f[0].keys():
                field.append(dn + "::" + field_name)
        self._json_field_list = json.dumps(field)

    @inlineCallbacks
    def _data_node_added(self, data_node):
        print("Data node \"%s\" added: adding its fields." % \
              (data_node["name"]))
        self._field[data_node["name"]] = yield \
           self._session.call(sisock.uri("consumer." + data_node["name"] + \
                                         ".get_fields"), 1, 0)
        self._remake_json_field_list()

    def _data_node_subtracted(self, data_node):
        print("Data node \"%s\" added: removing its fields." % \
              (data_node["name"]))
        try:
            del(self._field[data_node["name"]])
        except KeyError:
            print("Warning: data node \"%s\" had never been added to my " \
                  "list." % data_node["name"])
        self._remake_json_field_list()

    @inlineCallbacks
    def _query(self, request):
        if self._session is None:
            request.setResponseCode(500)
            return b"No WAMP session\n"
        print("Web client requested /query.")
        content = yield request.content.read()
        req = json.loads(content)
        t_start = iso_to_unix_time(req["range"]["from"])
        t_end = iso_to_unix_time(req["range"]["to"])
        poll = {}
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
                tl_name = self._field[data_node][0][f]["timeline"]
                tl = np.array(data["timeline"][tl_name]["t"]) * 1000.0
                d = {"target": data_node + "::" + f,
                     "datapoints": list(zip(data["data"][f], tl))}
                res.append(d)
        ret = json.dumps(res)
        print(ret)
        return ret


    def _search(self, request):
        if self._session is None:
            request.setResponseCode(500)
            return b"No WAMP session\n"
        print("Web client requested /search.")
        return self._json_field_list

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

    # Set up our sisock component.
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

    # Create our klein webserver, and then our datasource (which also connects
    # our component to the WAMP server).
    app = Klein()
    GrafanaSisockDatasrc(app, component)

    # Have our webserver listen on 5000, for Grafana requests.
    site = Site(app.resource())
    server_ep = TCP4ServerEndpoint(reactor, 5000)
    port = yield server_ep.listen(site)
    print("Web application on {}".format(port))

    # We don't *have* to hand over control of the reactor to
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

    # Wait forever (unless the Component raises an error).
    done = Deferred()
    yield done


if __name__ == '__main__':
    react(main)
