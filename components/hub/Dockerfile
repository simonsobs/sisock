# sisock_crossbar
# A containerized crossbar server.

# Use a locally built sisock container as a parent image
FROM sisock

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
ADD . /app

# Make port 80 available to the world outside this container
EXPOSE 8080

# Run app.py when the container launches
CMD ["crossbar", "start"]

