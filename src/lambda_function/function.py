"""Lambda that reads from a table and sends emails out for new music within the last 7 days. Invoked daily"""

# Standard library imports
import base64
import datetime
import json
import logging.config
import os
import traceback

# Third party library imports
import boto3
import requests

USER_FAVORITES_TABLE = boto3.resource('dynamodb').Table(os.environ['USER_FAVORITES_TABLE'])
SES_CLIENT = boto3.client('ses')
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)
HTML_START = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Title</title>
</head>
<body>
"""

HTML_END = """
</body>
</html>
"""


def handler(event, context):
    """Handler function that acts as a controller function"""
    LOGGER.debug(event)
    LOGGER.debug(context)
    records = get_users()
    artists = get_artists(records)
    if not artists:
        return {'message': 'Nothing to search :/'}

    spotify_authorization = authorize()
    spotify_responses = get_new_music_from_spotify(artists, spotify_authorization)

    for record in records:
        email_body = build_email_body_for_user(record['artists'], spotify_responses)
        send_email(email_body, record['email'])

    return {'message': 'all done :)'}


def get_users():
    """Scan table for all users to get favorite artists' new music"""
    table_response = USER_FAVORITES_TABLE.scan()
    return table_response['Items']


def get_artists(records):
    """Get a set of artists so there is only one spotify call per artist"""
    artists = set()
    for record in records:
        artists.update(record['artists'])

    return artists


def authorize():
    """Get spotify authorization token"""
    encoded_auth = base64.b64encode(
        (os.environ["SPOTIFY_CLIENT_ID"] + ':' + os.environ["SPOTIFY_CLIENT_SECRET"]).encode())
    headers = {
        'Authorization': 'Basic {}'.format(encoded_auth.decode("utf-8"))
    }

    response = requests.post(os.environ['SPOTIFY_AUTH_URL'], data={'grant_type': 'client_credentials'},
                             headers=headers).text
    return json.loads(response)


def get_new_music_from_spotify(artists, spotify_authorization):
    """Get new music for all artists"""
    spotify_responses = dict()
    spotify_artists = get_artist_ids_from_spotify(artists, spotify_authorization)

    for artist_id, artist in spotify_artists.items():
        new_music = get_new_music_for_artist(artist_id, spotify_authorization)
        spotify_responses.update({artist: new_music})

    return spotify_responses


def get_artist_ids_from_spotify(artists, spotify_authorization):
    """Get artist IDs to search for artists in Spotify"""
    spotify_artists = dict()
    url = os.environ['SPOTIFY_SEARCH_URL']
    headers = {
        'Authorization': f'Bearer {spotify_authorization["access_token"]}'
    }
    for artist in artists:
        params = '?q={}&type=artist&items=1'.format(artist)
        response = json.loads(requests.get(url + params, headers=headers).text)
        if not response['artists'].get('items', []):
            spotify_artists.update({artist: None})
        else:
            spotify_artists.update({response['artists']['items'][0]['id']: artist})

    return spotify_artists


def get_new_music_for_artist(artist_id, spotify_authorization):
    """Use Spotify ID to collect new singles for artists"""
    url = os.environ['SPOTIFY_ARTISTS_URL'].format(artist_id)
    headers = {
        'Authorization': f'Bearer {spotify_authorization["access_token"]}'
    }
    params = '?include_groups=single'

    response = json.loads(requests.get(url + params, headers=headers).text)

    return filter_music_for_last_seven_days(response)


def filter_music_for_last_seven_days(spotify_response):
    """Filters music from last seven days and builds a response"""
    new_music = list()
    for item in spotify_response['items']:
        if item['release_date'] >= (datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y-%m-%d'):
            images = item['images']
            thumbnail = [image for image in images if is_image_size_64(image)]
            new_music.append({
                'name': item.pop('name'),
                'type': item.pop('type'),
                'releaseDate': item['release_date'],
                'url': item['external_urls'].pop('spotify'),
                'thumbnail': thumbnail
            })

    return new_music


def is_image_size_64(image):
    """Checks for 64x64 pixel image, returns boolean"""
    return image['height'] == 64 and image['width'] == 64


def build_email_body_for_user(artists, spotify_responses):
    """Build email body for new music or no new music for artists"""
    email_body = ''
    for artist in artists:
        if artist in spotify_responses:
            email_body += create_artist_new_music_line(spotify_responses[artist])

    return email_body


def create_artist_new_music_line(spotify_artist_music):
    """Build HTML line with image and text for email"""
    body = ''
    for item in spotify_artist_music:
        if item['thumbnail']:
            artist_string = '<p><img src="{}" width="{}" height="{}" /> {} released on {}--{}</p>\n'
            body += artist_string.format(item['thumbnail'][0]['url'], item['thumbnail'][0]['width'],
                                         item['thumbnail'][0]['height'], item['name'], item['releaseDate'], item['url'])
    return body


def send_email(email_body, email_to):
    """Send email through SES"""
    html = f'{HTML_START}{email_body}{HTML_END}'
    try:
        SES_CLIENT.send_email(
            Source=os.environ['SENDER_EMAIL'],
            Destination={
                'ToAddresses': [
                    email_to
                ]
            },
            Message={
                'Subject': {
                    'Data': 'Newest Music in Last 7 Days (Spotify)',
                },
                'Body': {
                    'Html': {
                        'Data': html,
                    }
                }
            }
        )

    except:
        traceback.print_exc()
        return False

    return True
