Components
==========

There are currently three components that make up a functioning sisock stack
(in the context of live montioring, anyway). There's the crossbar server, the
intermediate web server, and then all the ``DataNodeServers``. This page
documents how to get containers of these components and configure them in your
``docker-config.yml``.

.. contents:: Components
    :local:

sisock-crossbar
---------------
The crossbar server, an implementation of a WAMP router, serves as the
communication channel between all the various components, as well as to parts
of the Observatory Control System (OCS). This is provided by an image at
``grumpy.physics.yale.edu/sisock-crossbar``.

Alongside this server runs the sisock Hub, which keeps track of all the running
``DataNodeSevers``.

Configuration
`````````````
.. table::
   :widths: auto

   ==============    ============
   Option            Description
   ==============    ============
   container_name    sisock_crossbar - a currently hardcoded value in sisock, used for DNS resolution within Docker
   ports             Exposes the crossbar container on localhost at port 8001,
                     used for OCS communication. The 127.0.0.1 is *critical* if
                     the computer you are running on is exposed to the internet.
   volumes           We need the TLS certs bind mounted.
   PYTHONBUFFERED    Force stdin, stdout, and stderr to be unbuffered. For logging in Docker.
   ==============    ============

.. code-block:: yaml

    sisock-crossbar:
      image: grumpy.physics.yale.edu/sisock-crossbar:0.1.0
      container_name: sisock_crossbar # required for proper name resolution in sisock code
      ports:
        - "127.0.0.1:8001:8001" # expose for OCS
      volumes:
        - ./.crossbar:/app/.crossbar
      environment:
           - PYTHONUNBUFFERED=1

sisock-http
-----------
Between Grafana and sisock sits an web server. This serves as a data source for
Grafana, translating the queries from Grafana into data and field requests in
sisock. The result is data from a ``DataNodeServer`` is passed through the
crossbar server to the sisock-http server and then to Grafana over http,
displaying in your browser.

Configuration
`````````````

The image is provided at ``grumpy.physics.yale.edu/sisock-http``, and depends
on the crossbar server running to function. Since it communicates over the
secure port on crossbar we need the TLS certificates mounted. The HTTP server
defaultly runs on port 5000, but you can change this with the environment
variable 'PORT', as shown in the example. There is also a 'LOGLEVEL'
environment variable which can be used to set the log level. This is useful for
debugging. txaio is used for logging.

.. code-block:: yaml

    sisock-http:
      image: grumpy.physics.yale.edu/sisock-http:0.1.0
      depends_on:
        - "sisock-crossbar"
      environment:
        PORT: "5001"
        LOGLEVEL: "info"
      volumes:
        - ./.crossbar:/app/.crossbar:ro

g3-file-scanner
---------------
This component will scan a directory for .g3 files, opening them and storing
information about them required for the g3-reader DataNodeServer in a MySQL
database. It scans at a given interval, defined as an environment variable. It
also requires connection parameters for the SQL database, and a top level
directory to scan.

Configuration
`````````````
The image is provided at ``grumpy.physics.yale.edu/sisock-g3-file-scanner``,
and only depends on the database we store file information in.

.. code-block:: yaml

  g3-file-scanner:
    image: grumpy.physics.yale.edu/sisock-g3-file-scanner:0.2.0
    volumes:
      - /home/koopman/data/yale:/data:ro # has to match the mount in g3-reader
    environment:
        SQL_HOST: "database"
        SQL_USER: "development"
        SQL_PASSWD: "development"
        SQL_DB: "files"
        DATA_DIRECTORY: '/data/'
        SCAN_INTERVAL: 3600 # seconds
    depends_on:
      - "database"

Common Configuration
--------------------
There are some environment variables which are common among all sisock
components. These mostly relate to connection settings for the crossbar server.
The defaults will work for a simple, single node, setup. However, moving to
multiple nodes, in most cases, will require setting some of these.

.. table::
   :widths: auto

   =================   ============
   Option              Description
   =================   ============
   WAMP_USER           The username configured for connecting to the crossbar
                       server. This is the "role" in the crossbar config.
   WAMP_SECRET         The associated secret for the WAMP_USER.
   CROSSBAR_HOST       IP or domain name for the crossbar server.
   CROSSBAR_TLS_PORT   The port configured for secure connection to the
                       crossbar server. In default SO configurations this is 8080.
   CROSSBAR_OCS_PORT   The port configured for open connection to the crossbar
                       server. In default SO configurations this is 8001.
   =================   ============

.. warning::
    The default `WAMP_SECRET` is not secure. If you are deploying your crossbar
    server in a public manner, you should not use the default secret.
