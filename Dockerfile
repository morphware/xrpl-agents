# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /src
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r /app/src/requirements.txt

EXPOSE 5050

# Run file_agent_main.py when the container launches
CMD ["python", "src/app.py"]