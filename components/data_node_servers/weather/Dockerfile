# sisock weather server
# Example sisock data node server, serving APEX weather data.

# Use sisock base image
FROM sisock:latest

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app/

# Run app.py when the container launches
CMD ["python3", "-u", "server_example_weather.py"]
