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
The image is called ``sisock-weather-server``, and should have the general
dependencies. It also communicates over the secure port with the crossbar
server, and so needs the bind mounted ``.crossbar`` directory.

.. code-block:: yaml

    weather:
      image: grumpy.physics.yale.edu/sisock-weather-server:latest
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
The image is called ``sisock-sensors-server``, and should have the general
dependencies. It also communicates over the secure port with the crossbar
server, and so needs the bind mounted ``.crossbar`` directory.

.. code-block:: yaml

    sensors:
      image: grumpy.physics.yale.edu/sisock-sensors-server:latest
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
The image is called ``sisock-apex-weather-server``, and should have the general
dependencies. It also communicates over the secure port with the crossbar
server, and so needs the bind mounted ``.crossbar`` directory. In addition, you
will need to mount the location that the data is stored on the host system.

There is an environment variable, ``MAX_POINTS``, that can be used to configure
the maximum number of points the server will return, this is useful for looking
at large time ranges, where fine resolution is not needed.

.. code-block:: yaml

    apex-weather:
      image: grumpy.physics.yale.edu/sisock-apex-weather-server:latest
      volumes:
        - ./.crossbar:/app/.crossbar:ro
        - /var/www/apex_weather:/data:ro
      environment:
          MAX_POINTS: 1000
      depends_on:
        - "sisock_crossbar"
        - "sisock_grafana_http"


data-feed
---------
A ``DataNodeServer`` which is able to subscribe to, cache, and serve live data
from an OCS agent which publishes to an OCS Feed. This ``DataNodeServer``
communicates with the crossbar server on an unencrypted port so as to enable
subscription to the OCS data feeds.

Data published by OCS Agents is cached in memory for up to an hour. Any data
with a timestamp older than an hour is removed from the cache.

Configuration
`````````````
The image is called ``sisock-data-feed-server``, and should have the general
dependencies. 

There are several environment variables which need to be set uniquely per
instance of the server:

.. table::
   :widths: auto

   ===========  ============
   Variable     Description
   ===========  ============
   TARGET       Used for data feed subscription, must match the "instance-id" for the Agent as configured in your site-config file.
   FEED         Used for data feed subscription. This must match the name of the ocs Feed which the ocs Agent publishes to.
   NAME         Used to uniquely identify the server in Grafana, appears in sisock in front of the field name.
   DESCRIPTION  Description for the device, is used by Grafana.
   ===========  ============

The "TARGET" and "FEED" variables are used to construct the full crossbar
address which is used for the subscription. This address ultimately looks like
"observatory.TARGET.feeds.FEED". Failure to match to an address which has data
published to it will result in no data being cached.

.. code-block:: yaml

    bluefors:
      image: grumpy.physics.yale.edu/sisock-data-feed-server:latest
      environment:
          TARGET: bluefors # match to instance-id of agent to monitor, used for data feed subscription
          NAME: 'bluefors' # will appear in sisock a front of field name
          DESCRIPTION: "bluefors logs"
          FEED: "bluefors"
      logging:
        options:
          max-size: "20m"
          max-file: "10"
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
The image is called ``sisock-radiometer-server``, and should have the general
dependencies. It also communicates over the secure port with the crossbar
server, and so needs the bind mounted ``.crossbar`` directory. In addition, you
will need to mount the location that the data is stored on the host system.

There is an environment variable, ``MAX_POINTS``, that can be used to configure
the maximum number of points the server will return, this is useful for looking
at large time ranges, where fine resolution is not needed.

.. code-block:: yaml

    ucsc-radiometer:
      image: grumpy.physics.yale.edu/sisock-radiometer-server:latest
      volumes:
        - ./.crossbar:/app/.crossbar:ro
        - /var/www/Skymonitor:/data:ro
      environment:
          MAX_POINTS: 1000
      depends_on:
        - "sisock-crossbar"
        - "sisock-http"

g3-reader
---------
A ``DataNodeServer`` which reads data from g3 files stored on disk. This
operates with the help of a MySQL database, which runs in a separate container.
This database stores information about the g3 files, such as the filename,
path, feed name, available fields and their associated start and end times.
This enables the g3-reader DataNodeServer to determine which fields are
available via a query to the database and to determine which files to open to
retrieve the requested data.

The server will cache any data opened from a .g3 file. The data cache takes the
form of a dictionary with the full path to the file as a key. The value is a
dictionary with structure related to the structure within the .g3 file. The
design of the cache allows loaded files to be popped out of the dictionary to
prevent the cache from growing too large (though currently a good cache
clearing scheme is not implemented).

Configuration
`````````````
The image is called ``sisock-g3-reader-server``, and should have the general
dependencies. It also communicates over the secure port with the crossbar
server, and so needs the bind mounted ``.crossbar`` directory. In addition, you
will need to mount the location that the data is stored on the host system.

There is an environment variable, ``MAX_POINTS``, that can be used to configure
the maximum number of points the server will return, this is useful for looking
at large time ranges, where fine resolution is not needed.

Additionally, there are environment variables for the SQL connection, which
will need to match those given to a mariadb instance. Both configurations will
look like:

.. code-block:: yaml

  g3-reader:
    image: grumpy.physics.yale.edu/sisock-g3-reader-server:latest
    volumes:
      - /home/koopman/data/yale:/data:ro
      - ./.crossbar:/app/.crossbar
    environment:
        MAX_POINTS: 1000
        SQL_HOST: "database"
        SQL_USER: "development"
        SQL_PASSWD: "development"
        SQL_DB: "files"
    depends_on:
      - "sisock-crossbar"
      - "sisock-http"
      - "database"

  database:
    image: mariadb:10.3
    environment:
      MYSQL_DATABASE: files
      MYSQL_USER: development
      MYSQL_PASSWORD: development
      MYSQL_RANDOM_ROOT_PASSWORD: 'yes'
    volumes:
      - database-storage-dev:/var/lib/mysql
