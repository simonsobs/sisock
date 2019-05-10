NAME=sisock-apex-weather-server

build :
	docker build -t ${NAME} .
	docker tag ${NAME}:latest grumpy.physics.yale.edu/${NAME}:latest

tag :
	docker tag ${NAME}:latest grumpy.physics.yale.edu/${NAME}:latest

push :
	docker push grumpy.physics.yale.edu/$(NAME):latest

# vim: set expandtab!:
