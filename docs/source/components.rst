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
secure port on crossbar we need the TLS certificates mounted.

.. code-block:: yaml

    sisock-http:
      image: grumpy.physics.yale.edu/sisock-http:0.1.0
      depends_on:
        - "sisock-crossbar"
      volumes:
        - ./.crossbar:/app/.crossbar:ro
