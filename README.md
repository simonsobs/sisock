# sisock
Engine for Simons Observatory data serving through websockets.

Current version does not have a working consumer yet (i.e., js/example.html
doesn't work and is from a legacy demo).

![Diagram of stuff](doc/diagram.png)

## Requirements
* python3, crossbar.io, spt3g

## Key Files
* .crossbar/config.json &mdash; the configuration for the crossbar.io router (see the README in .crossbar for information on TLS certificates).
* sisock.py &mdash; the data server
* js/example.html &mdash; a simple client
