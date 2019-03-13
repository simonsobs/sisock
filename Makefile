.PHONY : build
build:
	docker build -t sisock .
	docker tag sisock:latest grumpy.physics.yale.edu/sisock:latest

.PHONY : tag
tag:
	docker tag sisock:latest grumpy.physics.yale.edu/sisock:latest

.PHONY : clean
clean:
	docker image rm sisock:latest
	docker image rm grumpy.physics.yale.edu/sisock:latest

# vim: set expandtab!:
