# sisock radiometer server
# sisock data server serving UCSC radiometer data.

# Use sisock base image
FROM sisock:latest

# Copy the current directory contents into the container at /app
COPY requirements.txt /tmp/

# Install any extra requirements
RUN pip3 install -r /tmp/requirements.txt

# Set timezone to UTC
ENV TZ=Etc/UTC

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY radiometer_server.py /app/

# Run app.py when the container launches
CMD ["python3", "-u", "radiometer_server.py"]
