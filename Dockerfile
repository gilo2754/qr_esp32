FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the entrypoint script into the image
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

# Ensure the script is executable
RUN chmod +x /usr/local/bin/entrypoint.sh

# The command to run will be specified in docker-compose.yml
# ENTRYPOINT ["bash", "/usr/local/bin/entrypoint.sh"] 