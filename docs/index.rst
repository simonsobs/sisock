sisock - SImons observatory data over webSOCKets
=================================================

sisock is a python library and collection of components for serving quicklook
data over websockets, designed initially for the Simons Observatory. The goal
is to define an API for implementing a ``DataNodeServer``, which returns the
desired data, whether from memory or from disk. Data is passed through a
crossbar server using the WebSockets protocol.

sisock plays a key role in the Simons Observatory housekeeping live monitor,
which is based on the open source analytics and monitoring platform Grafana. A
simple webserver sits between sisock and Grafana, allowing Grafana to query the
sisock DataNodeServers.

User's Guide
------------

Start here for information about the design and use of sisock.

.. toctree::
   :maxdepth: 2

   source/datanodeservers

API Reference
-------------
If you are looking for information on a specific function, class or method, this part of the documentation is for you.

.. toctree::
   :maxdepth: 2

   source/api

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
