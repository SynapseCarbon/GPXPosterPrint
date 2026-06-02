# Build GPXPosterPrint as a Docker Image
# Automated build into Docker Hub

# Step 1: Use an official lightweight Python image
FROM python:3.14.5-slim-bookworm

# Step 2: Set the working directory inside the container
WORKDIR /app

# Step 3: Copy and install dependencies from your repo
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 4: Copy your script and your fonts folder from your repo
COPY GeneratePoster.py .
COPY fonts/ ./fonts/

# Step 5: Command to run the script when the container starts
CMD ["python", "GeneratePoster.py"]c