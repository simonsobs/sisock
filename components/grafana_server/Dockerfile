# grafana_http_json
# Layer connecting grafana with sisock.

# Use sisock base image
FROM sisock:latest

# Copy the current directory contents into the container at /app
COPY requirements.txt /tmp/

# Install any extra requirements
RUN pip3 install -r /tmp/requirements.txt

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY grafana_http_json.py /app/

# Run app.py when the container launches
CMD ["python3", "-u", "grafana_http_json.py"]
