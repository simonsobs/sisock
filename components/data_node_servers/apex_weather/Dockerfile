# apex weather server
# DataNodeServer serving APEX weather data for ACT.

# Use sisock base image
FROM sisock:latest

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY apex_weather_server.py /app/

# Run app.py when the container launches
CMD ["python3", "-u", "apex_weather_server.py"]
