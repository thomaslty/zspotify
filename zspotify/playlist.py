import os

from tqdm import tqdm

from const import ITEMS, ID, TRACK, NAME, PREFIX, ROOT_PATH, SYNC_FILES_WITH_PLAYLIST
from track import download_track
from utils import fix_filename, get_directory_song_filenames, purge_songs_id
from zspotify import ZSpotify

MY_PLAYLISTS_URL = 'https://api.spotify.com/v1/me/playlists'
PLAYLISTS_URL = 'https://api.spotify.com/v1/playlists'


def get_all_playlists():
    """ Returns list of users playlists """
    playlists = []
    limit = 50
    offset = 0

    while True:
        resp = ZSpotify.invoke_url_with_params(MY_PLAYLISTS_URL, limit=limit, offset=offset)
        offset += limit
        playlists.extend(resp[ITEMS])
        if len(resp[ITEMS]) < limit:
            break

    return playlists


def get_playlist_songs(playlist_id):
    """ returns list of songs in a playlist """
    songs = []
    offset = 0
    limit = 100

    while True:
        resp = ZSpotify.invoke_url_with_params(f'{PLAYLISTS_URL}/{playlist_id}/tracks', limit=limit, offset=offset)
        offset += limit
        songs.extend(resp[ITEMS])
        if len(resp[ITEMS]) < limit:
            break

    return songs


def get_playlist_info(playlist_id):
    """ Returns information scraped from playlist """
    resp = ZSpotify.invoke_url(f'{PLAYLISTS_URL}/{playlist_id}?fields=name,owner(display_name)&market=from_token')
    return resp['name'].strip(), resp['owner']['display_name'].strip()


def download_playlist(playlist):
    """Downloads all the songs from a playlist"""

    playlist_songs = [song for song in get_playlist_songs(playlist[ID]) if song[TRACK][ID]]
    p_bar = tqdm(playlist_songs, unit='song', total=len(playlist_songs), unit_scale=True)
    enum = 1

    download_directory = os.path.join(os.path.dirname(__file__), ZSpotify.get_config(ROOT_PATH),
                                      fix_filename(playlist[NAME].strip()) + '/')

    actual_songs_ids = []

    for song in p_bar:
        downloaded_id = download_track(song[TRACK][ID], download_directory, prefix=ZSpotify.get_config(PREFIX),
                       prefix_value=str(enum) ,disable_progressbar=True)
        if downloaded_id is not None:
            actual_songs_ids.append(downloaded_id)
        p_bar.set_description(song[TRACK][NAME])
        enum += 1

    # Remove files that are not part of the playlist
    if ZSpotify.get_config(SYNC_FILES_WITH_PLAYLIST):
        # Remove entries that aren't part of the list anymore
        purge_songs_id(download_directory, actual_songs_ids)

        # Read filenames of actual playlist songs
        keep_files = get_directory_song_filenames(download_directory)
        keep_files.append('.song_ids')

        # Remove file if is not on keep_files
        for filename in os.listdir(download_directory):
            file_path = os.path.join(download_directory, filename)

            if os.path.isfile(file_path) and filename not in keep_files:
                print('\n###   DELETING:', filename, '(SONG NOT IN PLAYLIST)   ###')
                os.remove(file_path)


def download_from_user_playlist():
    """ Select which playlist(s) to download """
    playlists = get_all_playlists()

    count = 1
    for playlist in playlists:
        print(str(count) + ': ' + playlist[NAME].strip())
        count += 1

    print('\n> SELECT A PLAYLIST BY ID')
    print('> SELECT A RANGE BY ADDING A DASH BETWEEN BOTH ID\'s')
    print('> For example, typing 10 to get one playlist or 10-20 to get\nevery playlist from 10-20 (inclusive)\n')

    playlist_choices = map(int, input('ID(s): ').split('-'))

    start = next(playlist_choices) - 1
    end = next(playlist_choices, start + 1)

    for playlist_number in range(start, end):
        playlist = playlists[playlist_number]
        print(f'Downloading {playlist[NAME].strip()}')
        download_playlist(playlist)

    print('\n**All playlists have been downloaded**\n')
