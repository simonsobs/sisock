# sisock weather server
# Example sisock data node server, serving APEX weather data.

# Use a locally built sisock container as the parent image
FROM sisock_crossbar

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
ADD . /app

# Run app.py when the container launches
CMD ["python3", "-u", "apex_weather_server.py"]
