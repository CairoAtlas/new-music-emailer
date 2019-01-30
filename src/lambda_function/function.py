"""Gets new music within the last week for artists saved to a dynamo table per user"""

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


def handler(event, context):
    LOGGER.debug(event)
    LOGGER.debug(context)
    records = get_users()
    artists = get_artists(records)

    spotify_authorization = authorize()
    spotify_responses = get_new_music_from_spotify(artists, spotify_authorization)

    for record in records:
        email_body = build_email_body_for_user(record['artists'], spotify_responses)
        send_email(email_body, record['email'])

    return json.dumps({'message': 'all done :)'})


def get_users():
    """Scan table for all users to get favorite artists' new music"""
    table_response = USER_FAVORITES_TABLE.scan()
    return table_response['Items']


def get_artists(records):
    """Get a set of artists so there is only one spotify call per artist"""
    artists = set()
    print(records)
    for record in records:
        print(record)
        artists.update(record['artists'])

    return artists


def authorize():
    encoded_auth = base64.b64encode((os.environ["SPOTIFY_CLIENT_ID"] + ':' + os.environ["SPOTIFY_CLIENT_SECRET"]).encode())
    print(str(encoded_auth))
    headers = {
        'Authorization': 'Basic {}'.format(encoded_auth.decode("utf-8") )
    }
    LOGGER.info(json.dumps(headers))
    data = {
        'grant_type': 'client_credentials'
    }

    response = requests.post(os.environ['SPOTIFY_AUTH_URL'], data={'grant_type': 'client_credentials'}, headers=headers).text
    LOGGER.info(response)
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
    spotify_artists = dict()
    url = os.environ['SPOTIFY_SEARCH_URL']
    headers = {
        'Authorization': f'Bearer {spotify_authorization["access_token"]}'
    }
    for artist in artists:
        params = f'?q={artist}&type=artist&items=1'
        url += params
        print(url)
        response = json.loads(requests.get(url + params, headers=headers).text)
        print(response)
        if not response['artists'].get('items', []):
            spotify_artists.update({artist: None})
        else:
            spotify_artists.update({response['artists']['items'][0]['id']: artist})

    return spotify_artists


def get_new_music_for_artist(artist_id, spotify_authorization):
    url = os.environ['SPOTIFY_ARTISTS_URL'].format(artist_id)
    headers = {
        'Authorization': f'Bearer {spotify_authorization["access_token"]}'
    }
    params = '?include_groups=single,album'

    response = json.loads(requests.get(url + params, headers=headers).text)

    return filter_music_for_last_seven_days(response)


def filter_music_for_last_seven_days(spotify_response):
    new_music = list()
    for item in spotify_response['items']:
        if item['release_date'] >= (datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y-%m-%d'):
            new_music.append({
                'name': item.pop('name'),
                'type': item.pop('type'),
                'releaseDate': item['release_date'],
                'url': item['external_urls'].pop('spotify')
            })

    return new_music


def build_email_body_for_user(artists, spotify_responses):
    """Build email body for new music or no new music for artists"""
    email_body = ''
    for artist in artists:
        if artist not in spotify_responses:
            email_body += 'No new music found for {} today\n'.format(artist)
        else:
            email_body += create_artist_new_music_line(artist, spotify_responses[artist])

    return email_body


def create_artist_new_music_line(artist, spotify_artist_music):
    body = f'{artist}\n'
    for item in spotify_artist_music:
        body += f'\t{spotify_artist_music["type"]} {spotify_artist_music["name"]} released on {spotify_artist_music["releaseDate"]}. {spotify_artist_music["url"]}\n'

    return body


def send_email(email_body, email_to):
    """Send email through SES"""
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
                    'Text': {
                        'Data': email_body,
                    }
                }
            }
        )

    except:
        traceback.print_exc()
        return False

    return True
