# GPXPosterPrint
Python project to take a GPX recording from an activity (bike ride, run, walk etc) and make an A3 sized poster - a great way to remember an epic day out.

As a note: I leant on Google Gemini for some of this project as I know a little bit of Python but wanted to get it working quicker

## Features

+ Up to 6 data fields / metrics of your choice at the bottom of the poster
  + Show average speed, elevation gain etc
+ If the start & end points are under 100m apart, a single marker is used to indicatemapbox the start / end point.  Otherwise, both points are marked
+ Uses standard Mapbox map styles, so easy to style the map to your choice of colour, level of detail (roads, POIs etc)
+ Easy customisation of font colours in the config file
+ Available as a pre-built Docker container if you don't have Python but do have Docker installed - see [Docker](Docker.md)

## Requirements

- Python 3.x (I used Python 3.14.5) with these packages installed (via pip3):
    - requests
    - reportlab
    - polyline
    - PyMuPDF
- Mapbox account with a valid access token (API Key)
    - The token scope should have three public scopes enabled:
        - Styles: Tiles
        - Styles: Read
        - Fonts: Read
- GPX file and relevant data from your activity
    - The GPX file can be easily exported from Garmin Connect, Strava etc

**Note**: When setting up a Mapbox account (if you don't already have one), you will be asked for credit card details.  There is a free tier for the Static Images API which (currently) provides up to 50,000 requests per month.  In development I've used less than 100 requests, so the chances of you being billed are pretty slim unless you make this project availabile publicly and somebody abuses your access token.

> [!CAUTION]
> Protect your Mapbox access token like an important password!  Do not put it in a public repository or share it with the Internet.

## Setup

- Clone the repository into a folder
- Copy of your chosen GPX file
- Rename or copy config.sample to config.toml and edit it, adding the relevant data including:
    - Path & name of the GPX file
    - Mapbox API access token
    - Ride details (title, date)
    - Between 1 to 6 ride metadata fields (distance, time, elevation gain, power, average speed etc)
 
If everything is in the same folder (Python script, config.toml and fonts), you should be able to enter that folder and run ```py GeneratePoster.py```.  The output should look something like:

```
GPXPosterPrint started - processing configuration
Registering typography layers...
 -> Montserrat-Bold registered successfully.
 -> Inter-Regular registered successfully.
Parsing 6.7MB GPX file...
 -> Loop detected (58.9m gap). Rendering a single start/end marker.
Success! Unified map tile asset rendered on layout plane.

PDF poster compiled successfully at: Github Sample.pdf
Converting PDF to high-res PNG via PyMuPDF (300 DPI)...
```

At that point you've hopefully ended up with PDF and PNG files containing your poster ready to print.
