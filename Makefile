.PHONY : docker
docker: 
	# sisock core components
	docker build -t sisock .
	docker build -t sisock-crossbar ./components/hub/
	docker build -t sisock-http ./components/grafana_server/
	# Data Node Servers (DaNS)
	docker build -t dans-example-weather ./components/data_node_servers/weather/
	docker build -t dans-example-sensors ./components/data_node_servers/sensors/
	docker build -t dans-apex-weather ./components/data_node_servers/apex_weather/
	docker build -t dans-thermometry ./components/data_node_servers/thermometry/
	docker build -t dans-ucsc-radiometer ./components/data_node_servers/radiometer/

.PHONY : clean
clean:
	docker image rm sisock
	docker image rm sisock-crossbar
	docker image rm sisock-http
	docker image rm dans-example-weather
	docker image rm dans-example-sensors
	docker image rm dans-apex-weather
	docker image rm dans-thermometry
	docker image rm dans-ucsc-radiometer

# vim: set expandtab!:
