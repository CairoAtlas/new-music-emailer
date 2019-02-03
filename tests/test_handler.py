import datetime
import json
import os

from moto import mock_dynamodb2, mock_ses
import boto3
import pytest
import requests

import lambda_function.function as code
from mocks import dynamodb_mocks
from mocks import Context

SPOTIFY_SAMPLE_ALBUMS = '../tests/events/spotifySampleResponse.json'


@pytest.fixture()
def spotify_albums_event(event_file=SPOTIFY_SAMPLE_ALBUMS):
    with open(event_file) as test_event:
        return json.load(test_event)


@mock_dynamodb2
def test_handler():
    # Code just runs through the handler and does nothing since all other functions are tested
    dynamodb_mocks.mock_user_favorites_table(os.environ['USER_FAVORITES_TABLE'])
    response = code.handler({}, Context(30))
    assert response['message'] == 'Nothing to search :/'


@mock_dynamodb2
def test_get_users():
    user1 = {
        'email': 'boybands@gmail.com',
        'artists': [
            'NSYNC*',
            'Backstreet Boys',
            '98 Degrees',
            'LFO',
            'Hanson'
        ]
    }

    user2 = {
        'email': 'freshofftheboat@gmail.com',
        'artists': [
            'Bel Biv Devoe',
            'Boyz II Men',
            'Dru Hill',
            'New Edition'
        ]
    }
    table = dynamodb_mocks.mock_user_favorites_table(os.environ['USER_FAVORITES_TABLE'])
    table.put_item(Item=user1)
    table.put_item(Item=user2)

    users = code.get_users()

    assert users[0]['email'] == 'boybands@gmail.com'
    assert len(users[0]['artists']) == 5

    assert users[1]['email'] == 'freshofftheboat@gmail.com'
    assert len(users[1]['artists']) == 4


def test_get_artists():
    user1 = {
        'email': 'boybands@gmail.com',
        'artists': [
            'NSYNC*',
            'Backstreet Boys',
            '98 Degrees',
            'LFO',
            'Hanson'
        ]
    }

    user2 = {
        'email': 'freshofftheboat@gmail.com',
        'artists': [
            'Bel Biv Devoe',
            'Boyz II Men',
            'Dru Hill',
            'New Edition',
            'Backstreet Boys'
        ]
    }

    artists = code.get_artists([user1, user2])

    # There are only 9 unique artists
    assert len(artists) == 9


def test_authorize(requests_mock):
    # Mock URL call
    requests_mock.post(os.environ['SPOTIFY_AUTH_URL'], text=json.dumps(
        {
            'access_token': 'access!',
            'token_type': 'bearer',
            'expires_in': 3600,
        }
    ))

    authorization = code.authorize()

    assert authorization['access_token'] == 'access!'
    assert authorization['token_type'] == 'bearer'
    assert authorization['expires_in'] == 3600


def test_get_new_music_from_spotify(requests_mock, spotify_albums_event):
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    spotify_albums_event['items'][0]['release_date'] = today
    requests_mock.get(os.environ['SPOTIFY_ARTISTS_URL'] + '?include_groups=single',
                 text=json.dumps(spotify_albums_event))
    requests_mock.get(os.environ['SPOTIFY_SEARCH_URL'] + '?q=shaggy&type=artist&items=1',
                 text=json.dumps({
                     'artists': {
                         'items': [
                             {
                                 'id': '123'
                             }
                         ]
                     }
                 }))

    response = code.get_new_music_from_spotify(['shaggy'], {'access_token': 'access'})
    assert 'shaggy' in response
    assert response['shaggy'] is not None


def test_get_artist_ids_from_spotify(requests_mock):
    requests_mock.get(os.environ['SPOTIFY_SEARCH_URL'] + '?q=shaggy&type=artist&items=1',
                 text=json.dumps({
                     'artists': {
                         'items': [
                             {
                                 'id': '123'
                             }
                         ]
                     }
                 }))

    response = code.get_artist_ids_from_spotify(['shaggy'], {'access_token': 'access'})
    assert response['123'] == 'shaggy'


def test_get_new_music_for_artist(requests_mock, spotify_albums_event):
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    spotify_albums_event['items'][0]['release_date'] = today
    requests_mock.get(os.environ['SPOTIFY_ARTISTS_URL'] + '?include_groups=single',
                  text=json.dumps(spotify_albums_event))

    new_music = code.get_new_music_for_artist('123,', {'access_token': 'access'})
    assert len(new_music) == 1
    assert new_music[0]['name'] == 'Shut Up Lets Dance (Vol. II)'
    assert new_music[0]['type'] == 'album'
    assert new_music[0]['releaseDate'] == today
    assert new_music[0]['url'] == 'https://open.spotify.com/album/43977e0YlJeMXG77uCCSMX'
    assert new_music[0]['thumbnail'][0]['url'] == 'https://i.scdn.co/image/779dd6d6a0e124e03a5143d2be729ee4bab3f15f'
    assert new_music[0]['thumbnail'][0]['height'] == 64
    assert new_music[0]['thumbnail'][0]['width'] == 64


def test_music_for_last_seven_days(spotify_albums_event):
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    spotify_albums_event['items'][0]['release_date'] = today
    new_music = code.filter_music_for_last_seven_days(spotify_albums_event)
    assert len(new_music) == 1
    assert new_music[0]['name'] == 'Shut Up Lets Dance (Vol. II)'
    assert new_music[0]['type'] == 'album'
    assert new_music[0]['releaseDate'] == today
    assert new_music[0]['url'] == 'https://open.spotify.com/album/43977e0YlJeMXG77uCCSMX'
    assert new_music[0]['thumbnail'][0]['url'] == 'https://i.scdn.co/image/779dd6d6a0e124e03a5143d2be729ee4bab3f15f'
    assert new_music[0]['thumbnail'][0]['height'] == 64
    assert new_music[0]['thumbnail'][0]['width'] == 64


def test_is_image_size_64():
    big_image = {'height': 360, 'width': 360}
    small_image = {'height': 64, 'width': 64}
    assert code.is_image_size_64(big_image) is False
    assert code.is_image_size_64(small_image) is True


def test_build_email_body_for_user():
    artist = {
        'name': 'album name',
        'type': 'album',
        'releaseDate': '2019-02-02',
        'url': 'spotify.com',
        'thumbnail': [{
            'height': 64,
            'width': 64,
            'url': 'https://usatftw.files.wordpress.com/2019/01/super-bowl-vs-banner-rams-patriots.jpg?w=1000'

        }]
    }
    artists = ['abc', '123', 'xyz', 'lol']
    spotify_responses = {'abc': [artist]}
    body = code.build_email_body_for_user(artists, spotify_responses)
    assert body == """<p><img src="https://usatftw.files.wordpress.com/2019/01/super-bowl-vs-banner-rams-patriots.jpg?w=1000" width="64" height="64" /> album name released on 2019-02-02--spotify.com</p>\n"""


def test_create_artist_new_music_line():
    artist = {
        'name': 'album name',
        'type': 'album',
        'releaseDate': '2019-02-02',
        'url': 'spotify.com',
        'thumbnail': [{
            'height': 64,
            'width': 64,
            'url': 'https://usatftw.files.wordpress.com/2019/01/super-bowl-vs-banner-rams-patriots.jpg?w=1000'

        }]
    }

    body_line = code.create_artist_new_music_line([artist])
    assert body_line == """<p><img src="https://usatftw.files.wordpress.com/2019/01/super-bowl-vs-banner-rams-patriots.jpg?w=1000" width="64" height="64" /> album name released on 2019-02-02--spotify.com</p>\n"""


@mock_ses
def test_send_email():
    ses_client = boto3.client('ses')
    ses_client.verify_email_identity(EmailAddress=os.environ['SENDER_EMAIL'])
    html = "<p>you say i'm just a test</p>"
    email = 'sbobspants@nick.com'
    assert code.send_email(html, email) is True
