# sisock

## Brief Overview

**Sisock** is a suite of software for serving **Si**mons Observatory data over
web**sock**ets.

The key components are:
- *A WAMP server* &mdash; This runs on just one computer; all data are routed
  through it.
- *Data node servers* &mdash; These can be spread across the internet, located
  on machines from which data are to be served (*data nodes*).
- A *hub* &mdash; The hub keeps track of which data node servers are online.
  Only one hub is run, by default on the computer running the WAMP server).
- *Consumers* &mdash; These are clients that request data from data node
  servers. They connect to the hub in order to know which data node servers are
  available and how to access them.
  - The `components/grafana_server` is an example of a consumer. It reads data
    via `sisock` and then passes it to Grafana over HTTP.

The following diagram illustrates the above:
![Diagram of stuff](docs/_static/diagram.png)

## Installing and Running

### 1. Setting Up Crossbar

First, we need to set up the crossbar configuration. For this, you need access
to the [ocs-site-configs](https://github.com/simonsobs/ocs-site-configs)
repository. From that repo, copy the following into the root of your `sisock`
directory:
- `templates/.crossbar/`
- `templates/setup-tls.sh`

Now that you have these files, you need to generate certificates so that our
websocket communication is secure. Run the `setup-tls.sh` script.

> **Important**: when you are prompted for the ‘common name’ (CN), enter
> `localhost` if you are doing local development, or else the hostname of your
> server if you are in production mode and will be serving over the internet.
> The certificates will be rejected if their CN does not match the real-life
> hostname.

The `.crossbar/config.json` file should work out of the box, but advanced users
can tweak settings as they see fit.

### 2. Setting up to use docker

#### Get Dependencies

You will need to have `docker` and `docker-compose` installed on your system.
There are plenty of websites online that give instructions on how to do so, but

```bash
$ pip install docker docker-compose
```

should do the trick.

#### Create `docker-compose.yaml`

We will presume that you want to do local development in the following
instructions.
> If not, instead of using `templates/docker-compose_dev-mode.yaml` from
> `ocs-site-configs`, you could use
> `templates/docker-compose_production-mode.yaml`. In this case, you actually
> don't need any of the `sisock` code locally, since it pulls all the docker 
> images from `grumpy.physics.yale.edu`: see below for how to access images
> from this computer.

Sisock is normally run in `docker` containers using `docker-compose`. You will
need to create a YAML file for configuring this. Again, you can find an example
in the [ocs-site-configs](https://github.com/simonsobs/ocs-site-configs) in
`templates/docker-compose_dev-mode.yaml`, which you should copy to
`docker-compose.yaml` in the root of your `sisock` directory and customise.

In particular, there are a few lines that you will need to or may need to
customise.
- Under `ports` in the `database` service, you may need to select a port that
  differs from `3306` if it is already being used by a local SQL server.
- If you want to serve local g3 files, the entry under `volumes` under *both* 
  the `g3-file-scanner` and the `g3-file-reader` services needs to point to
  the location of your g3 files.
- Similar to the previous point, if you want to serve local APEX or radiometer
  data, the `source` under `volumes` needs to be set.

##### Make Sure You Have Access to the `so3g` Docker Image

The `g3_reader` data node server uses the `so3g` library, whose image is pulled
by `components/g3_file_scanner/Dockerfile`. By default, this image is pulled
from `grumpy` at Yale. You will need to do the following to enable this:

```bash
$ docker login grumpy.physics.yale.edu
```

The username/password is a SO standard: ask Brian Koopman if you don't know it.

Alternatively, you can create your own image locally and alter
`components/g3file_scanner/Dockerfile` as appropriate.

### 3. Go!

#### Firing Things Up

If it doesn't yet exist, create the overarching network for the system:

```bash
$ docker network create --driver bridge sisock-net
```

To run *all* the services, simply do:

```bash
$ docker-compose up
```

Or, you can select which services listed in `docker-compose.yaml` you want to
run. For instance, the following is a nice, minimal check that things are
working:

```bash
$ docker-compose up grafana sisock-http sensors-server
```

> The commands above attach the `stdout` of all the containers to your
> terminal; you can terminate with good ol' ctrl-c. This mode is helpful for
> debugging. However, if you'd like to background this, throw the `-d` flag.

Grafana should now be running: access it at `localhost:3000`. You'll need to 
configure the Grafana data source as the SimpleJson type with a URL of
`http://sisock-http:5000`. (The user defined bridge network, `sisock-net`,
enables DNS resolution by container name, in this case `sisock-http`, as is 
defined in the `docker-compose.yaml` file.)

#### Rebuilding

If you make modifications to the code, `docker-compose up` won't automatically
update the images. You will need to do this yourself with `docker-compose
build`. For instance, if you were working on the code in
`components/data_node_servers/sensors/`, you would do:

```bash
$ docker-compose build sensors-server
```

To rebuild *all* the images (normally not necessary), just do:

```bash
$ docker-compose build
```

#### Clean-up

To shutdown and cleanup, run:

```bash
$ docker-compose down
```

If you'd like to remove the images as well run:

```bash
$ docker-compose down --rmi all
```

This will not remove `sisock-net`. To do so:

```bash
$ docker network rm sisock-net
```

Furthermore, if you really don't want your saved grafana configuration, you can
remove the grafana-storage container:

```bash
$ docker volume rm grafana-storage
```

## Running Without Docker Compose (possibly deprecated)

> This section has not been updated for some time and is likely out-of-date.

If we want to build and run the containers separatly we can avoid use of Docker
Compose. You still need to create the sisock-net network and run the grafana
container as done above.

Then, we'll build the sisock container image. This will form the base image for
all containers requiring sisock. From the top of the repo, run:

```bash
$ docker build -t sisock .
```

The `components/` directory contains each of the components we'll need to build
a container for, starting with the `hub`, which also starts the crossbar router.
Before we proceed, be sure to generate the required TLS certificates in
`components/hub/.crossbar`. See the README there for details.

#### Building with `make`
We can use the provided `Makefile` to build all the Docker images, simply run:

```bash
$ make docker
```

#### Building Individually

From within `components/hub` we'll build the crossbar router (the router
automatically starts up the hub component when it begins):

```bash
$ cd components/hub/
$ docker build -t sisock_crossbar .
```

Next we build the `grafana_http_json.py` component's container:

```bash
$ cd components/grafana_server/
$ docker build -t sisock_grafana_http .
```

Now for the data node servers, first the weather server:

```bash
$ cd components/data_node_servers/weather/
$ docker build -t weather_server .
```

Finally, the sensors server (note the needed host network for DNS resolution
for apt-get'ing the `lm-sensors` package),

```bash
$ cd components/data_node_servers/sensors/
$ docker build -t sensors_server --network=host .
```

#### Running the Containers
We can run all four components' containers now:

```bash
$ docker run -d --name=sisock_crossbar --network sisock-net sisock_crossbar
$ docker run -d --name=sisock_grafana_http --network sisock-net sisock_grafana_http
$ docker run -d --name=weather_server --network sisock-net weather_server
$ docker run -d --name=sensors_server --network sisock-net sensors_server
```

If you want to run the crossbar server and have locally run programs (such as
OCS agents) interact with it (rather than exclusively those in other
containers), you'll need to expose the ports. You can do so by adding the `-p`
flag, for example:

```bash
$ docker run -d --name=sisock_crossbar -p 8001:8001 -p 8080:8080 --network sisock-net sisock_crossbar
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

If you exposed the ports for the `sisock_crossbar` server, you should see `->8001/tcp` and `->8080/tcp` under `PORTS`.

```bash
CONTAINER ID        IMAGE               COMMAND             CREATED             STATUS              PORTS                                            NAMES
32ebe256fc98        sisock_crossbar     "crossbar start"    2 seconds ago       Up 1 second         0.0.0.0:8001->8001/tcp, 0.0.0.0:8080->8080/tcp   sisock_crossbar
```

Navigating to `localhost:3000` will get you to grafana. 

You'll need to configure the Grafana data source as the SimpleJson type with a
URL of `http://sisock_grafana_http:5000`. The user defined bridge network,
sisock-net, enables DNS resolution by container name, in this case
`sisock_grafana_http`.

#### Clean-up
To clean up the Docker containers when done with the demo:

```
$ docker container stop sensors_server weather_server sisock_grafana_http sisock_crossbar sisock_grafana
$ docker container rm sensors_server weather_server sisock_grafana_http sisock_crossbar sisock_grafana
$ docker network rm sisock-net
```

At this point we need to delete the built images. You can either run `make clean` or:
```bash
$ docker image rm sensors_server weather_server sisock_grafana_http sisock_crossbar sisock_grafana
```

This is included in the `Makefile`, as it is commonly done during testing.
