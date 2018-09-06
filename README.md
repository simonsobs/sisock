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
