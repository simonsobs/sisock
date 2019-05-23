# sisock OCS comms server
# sisock server, serving data from OCS, specifically at first Lakeshore 372 or 240 data

# Use sisock base image
FROM sisock:latest

# Set timezone to UTC
ENV TZ=Etc/UTC

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY data_feed_server.py /app/

# Run app.py when the container launches
CMD ["python3", "-u", "data_feed_server.py"]
