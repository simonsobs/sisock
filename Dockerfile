# sisock
# A containerized sisock installation.

# Build on so3g base image
FROM grumpy.physics.yale.edu/so3g:0.0.4

# Set timezone to UTC
ENV TZ=Etc/UTC

# Set the working directory to /app
WORKDIR /sisock

# Copy the current directory contents into the container at /app
ADD . /sisock

# Install any needed packages specified in requirements.txt
RUN pip3 install -r requirements.txt .
