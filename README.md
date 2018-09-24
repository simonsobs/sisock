# sisock
Engine for Simons Observatory data serving through websockets.

![Diagram of stuff](doc/diagram.png)

## Requirements
* python3, crossbar.io

## Key components to-date
* <tt>.crossbar/config.json</tt> &mdash; The WAMP configuration file
  * See the README in the <tt>.crossbar</tt> directory for information on TLS
    certificates).
* <tt>hub.py</tt> &mdash; The <tt>sisock</tt> hub for tracking which data node
  servers are available.
  * Data node servers report availability using the 
    `data_node.add` and `data_node.subtract` RPC.
  * Consumers query for available data node servers using the
    `consumer.get_data_node` RPC; they can also subscribe to the
    `consumer.data_node_added` and `consumer.data_node_subtracted` topics to be
    informed on any changes.
* <tt>sisock.py</tt> &mdash; Module containing parent classes and common utility
  functions.
  * It contains the parent class `data_node_server`. Actual data node
    servers inherit it and override most of the methods.
* <tt>sisock_example_weather.py</tt> &mdash; A working, toy example of a data 
  node server, taking its data from the files in the directory
  <tt>example_data</tt>.
* <tt>sisock_example_sensors.py</tt> &mdash; A toy example of a data node serve
  serving live data: viz., the output of the Linux command-line utility <tt>sensors</tt>.
* <tt>js/example.html</tt> &mdash; A simple client browser-based client showing 
  how to communicate with the hub and with data node servers.
* <tt>grafana_http_json.py</tt> &mdash; A webserver that is a <tt>grafana</tt> data source that forwards data from <tt>sisock</tt>.

## Running with Docker
The demo for showing off sisock communication in grafana depends on Docker.
You'll need Docker installed for the following to work. We'll be creating five
containers in total.

We'll first create a network to connect all the containers, we'll call it
`sisock-net`.

```bash
$ docker network create --driver bridge sisock-net
```

Next, we'll create a container for grafana, this also installs the simple
json-datasource plugin and a plotly-panel plugin for some more plotting
features.

```bash
$ docker run -d -p 3000:3000 --name=sisock_grafana -e "GF_INSTALL_PLUGINS=grafana-simple-json-datasource, natel-plotly-panel" grafana/grafana
```

Add the grafana container to sisock-net:

```bash
$ docker network connect sisock-net sisock_grafana
```

From within this repo, we'll build the crossbar server (this assumes you've
setup the certs/keys for crossbar already.)

```bash
$ docker build -t sisock_crossbar .
$ docker run -d --name=sisock_crossbar --network sisock-net sisock_crossbar
```

Next we build the `grafana_http_json.py` server's container:

```bash
$ docker build -t sisock_grafana_http -f Dockerfile_grafana_http_json .
$ docker run -d --name=sisock_grafana_http --network sisock-net sisock_grafana_http
```

Now for the data servers, first the weather server:

```bash
$ docker build -t weather_server -f Dockerfile_weather_server .
$ docker run --name=weather_server --network sisock-net -d weather_server
```

Finally, the sensors server (note the needed host network for DNS resolution
for apt-get'ing the `lm-sensors` package),

```bash
$ docker build -t sensors_server --network=host -f Dockerfile_sensors_server .
$ docker run --name=sensors_server --network sisock-net -d sensors_server
```

Your running containers should now look something like this:

```bash
bjk49@grumpy:~/git/sisock$ docker ps
CONTAINER ID        IMAGE                 COMMAND                  CREATED             STATUS              PORTS                    NAMES
6f096af2f38e        sensors_server        "python3 server_exam…"   4 seconds ago       Up 2 seconds                                 sensors_server
fa8e22a9371a        weather_server        "python3 server_exam…"   7 minutes ago       Up 7 minutes                                 weather_server
15487116c7d8        sisock_grafana_http   "python3 grafana_htt…"   12 minutes ago      Up 12 minutes       5000/tcp                 sisock_grafana_http
db4ce214e733        sisock_crossbar       "crossbar start"         18 minutes ago      Up 18 minutes       8080/tcp                 sisock_crossbar
28c49db6220f        grafana/grafana       "/run.sh"                12 days ago         Up 5 hours          0.0.0.0:3000->3000/tcp   sisock_grafana
```

Navigating to `localhost:3000` will get you to grafana. 

You'll need to configure the Grafana data source as the SimpleJson type with a
URL of `http://sisock_grafana_http:5000`. The user defined bridge network,
sisock-net, enables DNS resolution by container name, in this case
`sisock_grafana_http`.

### Clean-up
To clean up the Docker containers when done with the demo:

```
$ docker container stop sensors_server weather_server sisock_grafana_http sisock_crossbar sisock_grafana
$ docker container rm sensors_server weather_server sisock_grafana_http sisock_crossbar sisock_grafana
$ docker network rm sisock-net
```
