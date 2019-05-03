# sisock
# A containerized sisock installation.

# Various parent images have been used, the latest being so3g
FROM grumpy.physics.yale.edu/so3g:0.0.4
#FROM spt3g:36d0c3d
#FROM python:3

# Set timezone to UTC
ENV TZ=Etc/UTC

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
ADD . /app

# Install any needed packages specified in requirements.txt
RUN pip3 install -r requirements.txt .
