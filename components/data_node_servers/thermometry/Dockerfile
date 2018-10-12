# sisock OCS comms server
# sisock server, serving data from OCS, specifically at first Lakeshore 372 or 240 data

# Use an official Python runtime as a parent image
FROM sisock_crossbar

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
ADD . /app

# Run app.py when the container launches
CMD ["python3", "thermometry_server.py"]
