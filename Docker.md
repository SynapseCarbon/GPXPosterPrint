# Docker Setup

If you don't have Python installed but do have Docker running somewhere, you can run the script as a disposable Docker container

## Running the container

+ Create a folder and copy config.sample from the repo to config.toml
+ Configure the values in config.toml as covered in the main README.md
+ Assuming your config.toml and .gpx file is in your current folder, execute:

PowerShell
~~~PowerShell
docker run --rm \
  -v "${PWD}:/app/data" synapsecarbon/gpxposterprint:latest
~~~

Bash
~~~Bash
docker run --rm \ 
-v $(pwd):/app/data synapsecarbon/gpxposterprint:latest

~~~

Your PDF and PNG files should appear in your current folder once the script has finished.