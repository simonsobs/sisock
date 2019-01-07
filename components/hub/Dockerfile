# sisock hub
# A containerized crossbar server.

# Use sisock base image
FROM sisock:latest

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app/
COPY hub.py /app/

# Run app.py when the container launches
CMD ["crossbar", "start"]
