# sisock radiometer server
# sisock DataNodeServer serving UCSC radiometer data.

# Use a locally built sisock container as the parent image
FROM sisock_crossbar

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
ADD . /app

# Run app.py when the container launches
CMD ["python3", "-u", "radiometer_server.py"]
