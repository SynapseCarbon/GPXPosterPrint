# GPXPosterPrint
Python project to take a GPX recording from an activity (bike ride, run, walk etc) and make an A3 sized poster - a great way to remember an epic day out.

As a note: I leant on Google Gemini for some of this project as I know a little bit of Python but wanted to get it working quicker

## Features

+ Up to 6 data fields / metrics of your choice at the bottom of the poster
+ If the start & end points are under 100m apart, a single marker is used to mark the start / end point.  Otherwise, both points are marked
+ Uses standard Mapbox map styles, so easy to style the map to your choice of colour, roads, POIs etc

## Requirements

- Python 3.x (I used Python 3.14.5) with these packages installed (via pip3):
    - requests
    - reportlab
    - polyline
- Mapbox account with a valid access token (API Key)
    - The token scope should have three public scopes enabled:
        - Styles: Tiles
        - Styles: Read
        - Fonts: Read
- GPX file and relevant data from your activity
    - The GPX file can be easily exported from Garmin Connect, Strava etc

**Note**: When setting up a Mapbox account (if you don't already have one), you will be asked for credit card details.  There is a free tier for the Static Images API which (currently) provides up to 50,000 requests per month.  In development I've used less than 100 requests, so the chances of you being billed are pretty slim unless you make this availabile publicly and somebody rinses your access token.  Do that at your own peril - protect your access token like a password!

## Setup

- Clone or grab the files from this repository

Copy config.sample to config.toml and edit it, adding the relevant data including:
    - Path to GPX file
    - Mapbox access token
    - Ride metadata (distance, time etc)
 
If everything is in the same folder (Python code, config.toml and fonts), you should be able to enter that folder and run ```py GeneratePoster.py```.  The output should look something like:
```
Registering typography layers...
 -> Montserrat-Bold registered successfully.
 -> Inter-Regular registered successfully.
Parsing 16.7MB GPX file...
Success! Unified map tile asset rendered on layout plane.

Completed! Final poster compiled successfully at: cycling_ride_a3_map_poster.pdf
```

Hopefully you've ended up with a PDF file containing your poster.
