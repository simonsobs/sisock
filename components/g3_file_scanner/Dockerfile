# g3_file_scanner
# Periodically scan the data directory, parse g3 files, and add information
# about them to a MySQL database.

# Use spt3g base image.
FROM grumpy.physics.yale.edu/so3g:0.0.4

# Copy the current directory contents into the container at /app
COPY requirements.txt /tmp/

# Install any extra requirements
RUN pip3 install -r /tmp/requirements.txt

# Set timezone to UTC
ENV TZ=Etc/UTC

# Setup environment, else it's not setup to import spt3g in container
ENV SPT3G_SOFTWARE_PATH /root/spt3g_software
ENV SPT3G_SOFTWARE_BUILD_PATH /root/spt3g_software/build

ENV PATH="/root/spt3g_software/build/bin:${PATH}"
ENV LD_LIBRARY_PATH="/root/spt3g_software/build/spt3g:${LD_LIBRARY_PATH}"
ENV PYTHONPATH="/root/spt3g_software/build:${PYTHONPATH}"

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY scan.py /app/

# Run scan.py when the container launches
CMD ["python3", "-u", "scan.py"]
