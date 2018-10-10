.PHONY : docker
docker: 
	docker build -t sisock .
	docker build -t sisock_crossbar ./components/hub/
	docker build -t sisock_grafana_http ./components/grafana_server/
	docker build -t weather_server ./components/data_node_servers/weather/
	docker build -t sensors_server ./components/data_node_servers/sensors/

.PHONY : clean
clean:
	docker image rm sisock
	docker image rm sisock_crossbar
	docker image rm sisock_grafana_http
	docker image rm weather_server
	docker image rm sensors_server

# vim: set expandtab!:
