from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger

from autobahn.twisted.util import sleep
from autobahn.twisted.wamp import ApplicationSession
from autobahn.wamp.exception import ApplicationError
from autobahn import wamp
from autobahn.wamp import auth

import numpy as np
import re

from spt3g import core as ser

WAMP_USER = "sisock_backend"
WAMP_SECRET = "r>0.001"
DATA_PATH = "/home/ahincks/code/sisock/dat/test.g3"

class backend_session(ApplicationSession):
    """The WAMPVsession for our live data server.

    Inherets from :class:`autobahn.twisted.wamp.ApplicationSession`

    Methods
    -------
    get_field
    get_field_list
    onJoin
    """

    log = Logger()

    @inlineCallbacks
    def onJoin(self, details):
        """Called when the server is started.

        Parameters
        ----------
        details : boh
        """
        reg = yield self.register(self)
        self.log.info("Procedures registered. Awesome!!!")

    def onConnect(self):
        self.log.info("Client session connected. Awesome!!!")
        self.join(self.config.realm, [u"wampcra"], WAMP_USER)


    def onChallenge(self, challenge):
        if challenge.method == u"wampcra":
            self.log.info("WAMP-CRA challenge received.")

            # compute signature for challenge, using the key
            signature = auth.compute_wcs(WAMP_SECRET,
                                         challenge.extra["challenge"])

            # return the signature to the router for verification
            return signature
        else:
            raise Exception("Invalid authmethod {}".format(challenge.method))
    
    @wamp.register(u"com.example.get_field")
    def get_field(self, field, start, n):
        """Get vectors of data.

        Currently, this naively assumes that there is only one frame of each
        type in a file; or better, it will keep overwriting the data of a field
        each time it finds a new frame of the same type ...

        Parameters
        ----------
        field : list of strings
            The fields for which to get the data. In the case of 
            G3TimestreamMap, the field name is "map[key]", where 
            "map" is the name of the timestream map and "key" is one of the
            timestreams in the map.
        start : list of integers
            The first sample number to return. (To read from the end of the
            vector, use a negative number. The length of this list should be the
            same as that of `field`.
        n : list of integers
            The number of samples to return. The length of this list should be
            the same as that of `field`.

        Returns
        -------
        A list of dictionaries, one dictionary for each field requested. Each
        dictionary is of the form {"field", "val", "error"}. Here, "field" is
        the name of the field being returned---the order of fields is not
        guaranteed to be the same as the order they were requested in; if
        "error" is set to :obj:`None', then "val" contains the values, otherwise
        "error" contains an error message.
        """
        ret = []
        field_base = [re.match("[^\[]*", f).group(0) for f in field]
        subfield = [re.findall("[^[]*\[([^]]*)\]", f) for f in field]
        try:
            fp = ser.G3File(DATA_PATH)
        except RuntimeError:
            self.log.error("Could not open %s." % (DATA_PATH))
            return False
        for ff in field:
            ret.append({"field" : ff,
                          "val" : False,
                        "error" : "field not found"})
        for frame in fp:
            for i in range(len(field)):
                if field_base[i] in frame.keys():
                    j = start[i]
                    k = start[i] + n[i]
                    if len(subfield[i]):
                        ff = frame[str(field_base[i])][str(subfield[i][0])]
                    else:
                        ff = frame[str(field_base[i])]
                    ret[i]["val"] = np.asarray(ff)[j:k].tolist()
                    ret[i]["error"] = None
        return ret
            
    @wamp.register(u"com.example.get_field_list")
    def get_field_list(self):
        """Get a list of available fields.

        For each frame type, return all the fields inside it. For
        G3TimestreamMaps, return one field for all elements, in the form
        "map[key]".

        Returns:
        A list of dictionaries, one dictionary per frame. Each dictionary has 
        two keys: "type" and "field". "Field" is an list of dictionaries,
        containing information on each of the members in the frame: as
        applicable, "name", "type", "rate" (in Hz), "n" (number of samples in
        frame) and "units".

        """
        self.log.info("Getting field list.")
        ret = []
        try:
            fp = ser.G3File(DATA_PATH)
        except RuntimeError:
            self.log.error("Could not open %s." % (DATA_PATH))
            return False
        for frame in fp:
            ret.append({"type": "%s" % frame.type, "field": []})
            for key in frame.keys():
                try:
                    f = frame[key]
                    try:
                        t = type(f)
                    except RuntimeError:
                        t = "Unregistered"
                    if t.__name__ == "G3Timestream":
                        ret[-1]["field"].append({"name": key,
                                                 "type": t.__name__,
                                                 "rate": f.sample_rate,
                                                 "n": len(f),
                                                 "units": str(f.units)})
                    elif t.__name__ == "G3TimestreamMap":
                        for ts in f.keys():
                            ff = f[ts]
                            ret[-1]["field"].append({"name": key + \
                                                             "[" + ts + "]",
                                                     "type": t.__name__,
                                                     "rate": ff.sample_rate,
                                                     "n": len(ff),
                                                     "units": str(ff.units)})
                    else:
                        ret[-1]["field"].append({"name": key,
                                                 "type": t.__name__})

                except RuntimeError:
                    self.log.debug("Skipping %s with unknown key type." % 
                                   key)
        return ret
