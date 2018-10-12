# sisock sensors server
# Example sisock server, serving CPU temperature data via `sensors`

# Use an official Python runtime as a parent image
FROM sisock_crossbar

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
ADD . /app

# Install any needed packages specified in requirements.txt
RUN apt-get update
RUN apt-get install -y lm-sensors

# Run app.py when the container launches
CMD ["python3", "server_example_sensors.py"]
