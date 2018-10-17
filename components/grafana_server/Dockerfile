# grafana_http_json
# Layer connecting grafana with sisock.

# Use a locally built sisock container as a parent image
FROM sisock_crossbar

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
ADD . /app

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run app.py when the container launches
CMD ["python3", "-u", "grafana_http_json.py"]
