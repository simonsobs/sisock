# sisock sensors server
# Example sisock server, serving CPU temperature data via `sensors`

# Use sisock base image
FROM sisock:latest

# Install any needed packages specified in requirements.txt
RUN apt-get update && apt-get install -y lm-sensors

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY server_example_sensors.py /app/

# Run app.py when the container launches
CMD ["python3", "-u", "server_example_sensors.py"]
