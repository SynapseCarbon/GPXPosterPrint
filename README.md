# GPXPosterPrint
Python project to take a GPX recording from an activity (bike ride, run, walk etc) and make a poster - a great way to remember an epic day (or days!) out.

As a note: I leant on Google Gemini for some of this project as I know a little bit of Python but wanted to get it working quicker

## Requirements

- Python 3.x (I used Python 3.13) with these packages installed (via pip3):
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

- Edit the config.toml with relevant data including:
    - Path to GPX file
    - Mapbox access token
    - Ride metadata (distance, time etc)
 
