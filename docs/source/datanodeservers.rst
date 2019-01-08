DataNodeServers
===============

sisock components are made up of individual DataNodeServers which know how to
retrieve a specific set of data. Each DataNodeServer (abbreviated DaNS, so as
to avoid the commonly known DNS acryonym) runs within its own Docker container.
To use a DaNS you simply add a copy of its configuration to your
``docker-compose.yml`` file and edit it accordingly. Below you will find
details for how to configure each DaNS.

.. note::
    A quick note about versions for the Docker images. The version number, as of
    this writing, corresponds to the tagged version of sisock. You can view the
    tags on Github under `releases`_. It is perhaps most safe, from a stability
    standpoint, to use a specific version number (i.e. 0.1.0), rather than
    "latest", which changes its underlying version number as new releases are
    made. The version number in these examples might not reflect the latest
    release, so you should check the `releases`_ page.

.. _releases: https://github.com/simonsobs/sisock/releases

.. contents:: DataNodeServers
    :local:

example-weather
---------------
An example ``DataNodeServer`` for demonstrating reading data from disk. A good
choice to include for debugging your live monitor.

This container includes a small set of raw text files that contain weather data
from the APEX telescope. The dataset runs from 2017-07-13 to 2017-07-27, so be
sure to set your date range accordingly.

Configuration
`````````````
The image is called ``dans-example-weather``, and should have the general
dependencies. It also communicates over the secure port with the crossbar
server, and so needs the bind mounted ``.crossbar`` directory.

.. code-block:: yaml

    weather:
      image: grumpy.physics.yale.edu/dans-example-weather:0.1.0
      depends_on:
        - "sisock-crossbar"
        - "sisock-http"
      volumes:
        - ./.crossbar:/app/.crossbar:ro

example-sensors
---------------
An example ``DataNodeServer`` for demonstrating the use of live data. The data
is generated within the container through use of the lm-sensors program, which
is already installed in the container. This returns the tempearture of your
computer's CPU cores.

.. warning::
    There are some known problems getting this to run on some systems. It
    should work on an Ubuntu 18.04 box, but if you're having trouble and really
    want to get it running get in touch with someone from the DAQ group.

This is a fun early demo, but probably won't be useful to many users.

Configuration
`````````````
The image is called ``dans-example-sensors``, and should have the general
dependencies. It also communicates over the secure port with the crossbar
server, and so needs the bind mounted ``.crossbar`` directory.

.. code-block:: yaml

    sensors:
      image: grumpy.physics.yale.edu/dans-example-sensors:0.1.0
      depends_on:
        - "sisock-crossbar"
        - "sisock-http"
      volumes:
        - ./.crossbar:/app/.crossbar:ro

apex-weather
------------
A ``DataNodeServer`` based on the ``example-weather`` server, which reads
weather data from the APEX telescope as archived by the ACT team. Used in
production at the ACT site.

Configuration
`````````````
The image is called ``dans-apex-weather``, and should have the general
dependencies. It also communicates over the secure port with the crossbar
server, and so needs the bind mounted ``.crossbar`` directory. In addition, you
will need to mount the location that the data is stored on the host system.

There is an environment variable, ``MAX_POINTS``, that can be used to configure
the maximum number of points the server will return, this is useful for looking
at large time ranges, where fine resolution is not needed.

.. code-block:: yaml

    apex-weather:
      image: grumpy.physics.yale.edu/dans-apex-weather:0.1.0
      volumes:
        - ./.crossbar:/app/.crossbar:ro
        - /var/www/apex_weather:/data:ro
      environment:
          MAX_POINTS: 1000
      depends_on:
        - "sisock_crossbar"
        - "sisock_grafana_http"


thermometry
-----------
A ``DataNodeServer`` which is able to cache and serve live thermometry data
from either a Lakeshore 372 or a Lakeshore 240. This ``DataNodeServer``
communicates with the crossbar server on an unencrypted port so as to enable
subscription to the OCS data feeds.

Data published by OCS thermometry Agents is cached in memory for up to an hour.
Retrieval of data written to disk is a work in progress.

Configuration
`````````````
The image is called ``dans-thermometry``, and should have the general
dependencies. 

There are several environment variables which need to be set uniquely per
instance of the server:

.. table::
   :widths: auto

   ===========  ============
   Variable     Description
   ===========  ============
   TARGET       Used for data feed subscription, must match the "instance-id" for the Agent as configured in your site-config file.
   NAME         Used to uniquely identify the server in Grafana, appears in sisock in front of the field name.
   DESCRIPTION  Description for the device, is used by Grafana.
   ===========  ============

.. code-block:: yaml

    LSA23JD:
      image: grumpy.physics.yale.edu/dans-thermometry:0.1.0
      environment:
          TARGET: LSA23JD # match to instance-id of agent to monitor, used for data feed subscription
          NAME: 'LSA23JD' # will appear in sisock a front of field name
          DESCRIPTION: "LS372 in the Bluefors control cabinet."
      depends_on:
        - "sisock-crossbar"
        - "sisock-http"

ucsc-radiometer
---------------
A ``DataNodeServer`` based on the ``example-weather`` server, which reads
weather data from the UCSC radiometer located on Cerro Toco. Used in production
at the ACT site.

Configuration
`````````````
The image is called ``dans-ucsc-radiometer``, and should have the general
dependencies. It also communicates over the secure port with the crossbar
server, and so needs the bind mounted ``.crossbar`` directory. In addition, you
will need to mount the location that the data is stored on the host system.

There is an environment variable, ``MAX_POINTS``, that can be used to configure
the maximum number of points the server will return, this is useful for looking
at large time ranges, where fine resolution is not needed.

.. code-block:: yaml

    ucsc-radiometer:
      image: grumpy.physics.yale.edu/dans-ucsc-radiometer:0.1.0
      volumes:
        - ./.crossbar:/app/.crossbar:ro
        - /var/www/Skymonitor:/data:ro
      environment:
          MAX_POINTS: 1000
      depends_on:
        - "sisock-crossbar"
        - "sisock-http"
