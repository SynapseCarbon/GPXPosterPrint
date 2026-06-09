# Build GPXPosterPrint as a Docker image
# Used for automated build into Docker Hub image

# Step 1: Use an official lightweight Python image
FROM python:3.14.5-slim-bookworm

# Step 2: Set the working directory inside the container
WORKDIR /app

# Step 3: Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 4: Copy the script and your fonts folder
COPY GeneratePoster.py .
COPY fonts/ ./fonts/

# Link config.toml location to same folder as script (to allow a single Docker mount)
# RUN ln -s /app/data/config.toml /app/config.toml

# Step 5: Command to run the script when the container starts
CMD ["python", "/app/GeneratePoster.py"]