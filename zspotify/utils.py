import os
import platform
import re
import subprocess
import time
from enum import Enum
from typing import List, Tuple, Dict

import music_tag
import requests

from const import ARTIST, TRACKTITLE, ALBUM, YEAR, DISCNUMBER, TRACKNUMBER, ARTWORK, \
    WINDOWS_SYSTEM, ALBUMARTIST


class MusicFormat(str, Enum):
    MP3 = 'mp3',
    OGG = 'ogg',

class SongIdFields(Enum):
    ID = 0
    FILENAME = 1
    ALL = 2

def create_download_directory(download_path: str) -> None:
    """ Create directory and add a hidden file with song ids """
    os.makedirs(download_path, exist_ok=True)

    # add hidden file with song ids
    hidden_file_path = os.path.join(download_path, '.song_ids')
    if not os.path.isfile(hidden_file_path):
        with open(hidden_file_path, 'w', encoding='utf-8') as f:
            pass

def get_directory_song_id_info(download_path: str, fields: SongIdFields) -> List[str] | Dict[str, str]:
    """ Gets fields from song ids file directory """

    if fields == SongIdFields.ALL:
        data = {}
    else:
        data = []

    hidden_file_path = os.path.join(download_path, '.song_ids')
    if os.path.isfile(hidden_file_path):
        with open(hidden_file_path, 'r', encoding='utf-8') as file:
            # ',' is used as character to separate hash and filename because simplicity, but this character can be part
            # of a song name, we select  only first match to avoid issues
            if fields == fields.ID:
                data = [line.split(",", 1)[0].strip() for line in file.readlines()]
            elif fields == fields.FILENAME:
                data = [line.split(",", 1)[1].strip() for line in file.readlines()]
            else:
                data = {line.split(",", 1)[0].strip(): line.split(",", 1)[1].strip() for line in file.readlines()}

    return data

def get_directory_song_ids(download_path: str) -> List[str]:
    """ Gets song ids of songs in directory """
    return get_directory_song_id_info(download_path, SongIdFields.ID)

def get_directory_song_filenames(download_path: str) -> List[str]:
    """ Gets song filenames in directory """
    return get_directory_song_id_info(download_path, SongIdFields.FILENAME)

def get_other_directory_songs_info(root_path: str, download_path_to_exclude: str) -> Dict[str, Dict[str,str]]:
    """ Gets all song id data from other paths"""

    data = {}

    for root, dirs, files in os.walk(root_path):
        for d in dirs:
            complete_path = os.path.join(root_path, d)
            if complete_path != download_path_to_exclude:
                data[d] = get_directory_song_id_info(complete_path, SongIdFields.ALL)
    return data

def add_to_directory_song_ids(download_path: str, song_id: str, short_filename : str) -> None:
    """ Appends song_id to .song_ids file in directory """

    hidden_file_path = os.path.join(download_path, '.song_ids')
    # not checking if file exists because we need an exception
    # to be raised if something is wrong
    with open(hidden_file_path, 'a', encoding='utf-8') as file:
        file.write(f'{song_id},{short_filename}\n')

def purge_songs_id(download_path: str, song_ids: List[str]):
    """ Remove lines in .song_ids file if they aren't part of song_ids fetched from playlist """
    hidden_file_path = os.path.join(download_path, '.song_ids')
    hidden_file_path_tmp = os.path.join(download_path, '.song_ids_tmp')

    with open(hidden_file_path, 'r', encoding='utf-8') as fin, \
            open(hidden_file_path_tmp, 'w', encoding='utf-8') as fout:
        for line in fin:
            if line.split(",", 1)[0].strip() in song_ids:
                fout.write(line)

    os.replace(hidden_file_path_tmp, hidden_file_path)

def get_downloaded_song_duration(filename: str) -> float:
    """ Returns the downloaded file's duration in seconds """

    command = ['ffprobe', '-show_entries', 'format=duration', '-i', f'{filename}']
    output = subprocess.run(command, capture_output=True)

    duration = re.search(r'[\D]=([\d\.]*)', str(output.stdout)).groups()[0]
    duration = float(duration)

    return duration

def wait(seconds: int = 3) -> None:
    """ Pause for a set number of seconds """
    for second in range(seconds)[::-1]:
        print(f'\rWait for {second + 1} second(s)...', end='')
        time.sleep(1)


def split_input(selection) -> List[str]:
    """ Returns a list of inputted strings """
    inputs = []
    if '-' in selection:
        for number in range(int(selection.split('-')[0]), int(selection.split('-')[1]) + 1):
            inputs.append(number)
    else:
        selections = selection.split(',')
        for i in selections:
            inputs.append(i.strip())
    return inputs


def splash() -> None:
    """ Displays splash screen """
    print("""
███████ ███████ ██████   ██████  ████████ ██ ███████ ██    ██
   ███  ██      ██   ██ ██    ██    ██    ██ ██       ██  ██
  ███   ███████ ██████  ██    ██    ██    ██ █████     ████
 ███         ██ ██      ██    ██    ██    ██ ██         ██
███████ ███████ ██       ██████     ██    ██ ██         ██
    """)


def clear() -> None:
    """ Clear the console window """
    if platform.system() == WINDOWS_SYSTEM:
        os.system('cls')
    else:
        os.system('clear')


def set_audio_tags(filename, artists, name, album_name, release_year, disc_number, track_number) -> None:
    """ sets music_tag metadata """
    tags = music_tag.load_file(filename)
    tags[ALBUMARTIST] = artists[0]
    tags[ARTIST] = conv_artist_format(artists)
    tags[TRACKTITLE] = name
    tags[ALBUM] = album_name
    tags[YEAR] = release_year
    tags[DISCNUMBER] = disc_number
    tags[TRACKNUMBER] = track_number
    tags.save()


def conv_artist_format(artists) -> str:
    """ Returns converted artist format """
    return ', '.join(artists)


def set_music_thumbnail(filename, image_url) -> None:
    """ Downloads cover artwork """
    img = requests.get(image_url).content
    tags = music_tag.load_file(filename)
    tags[ARTWORK] = img
    tags.save()


def regex_input_for_urls(search_input) -> Tuple[str, str, str, str, str, str]:
    """ Since many kinds of search may be passed at the command line, process them all here. """
    track_uri_search = re.search(
        r'^spotify:track:(?P<TrackID>[0-9a-zA-Z]{22})$', search_input)
    track_url_search = re.search(
        r'^(https?://)?open\.spotify\.com/track/(?P<TrackID>[0-9a-zA-Z]{22})(\?si=.+?)?$',
        search_input,
    )

    album_uri_search = re.search(
        r'^spotify:album:(?P<AlbumID>[0-9a-zA-Z]{22})$', search_input)
    album_url_search = re.search(
        r'^(https?://)?open\.spotify\.com/album/(?P<AlbumID>[0-9a-zA-Z]{22})(\?si=.+?)?$',
        search_input,
    )

    playlist_uri_search = re.search(
        r'^spotify:playlist:(?P<PlaylistID>[0-9a-zA-Z]{22})$', search_input)
    playlist_url_search = re.search(
        r'^(https?://)?open\.spotify\.com/playlist/(?P<PlaylistID>[0-9a-zA-Z]{22})(\?si=.+?)?$',
        search_input,
    )

    episode_uri_search = re.search(
        r'^spotify:episode:(?P<EpisodeID>[0-9a-zA-Z]{22})$', search_input)
    episode_url_search = re.search(
        r'^(https?://)?open\.spotify\.com/episode/(?P<EpisodeID>[0-9a-zA-Z]{22})(\?si=.+?)?$',
        search_input,
    )

    show_uri_search = re.search(
        r'^spotify:show:(?P<ShowID>[0-9a-zA-Z]{22})$', search_input)
    show_url_search = re.search(
        r'^(https?://)?open\.spotify\.com/show/(?P<ShowID>[0-9a-zA-Z]{22})(\?si=.+?)?$',
        search_input,
    )

    artist_uri_search = re.search(
        r'^spotify:artist:(?P<ArtistID>[0-9a-zA-Z]{22})$', search_input)
    artist_url_search = re.search(
        r'^(https?://)?open\.spotify\.com/artist/(?P<ArtistID>[0-9a-zA-Z]{22})(\?si=.+?)?$',
        search_input,
    )

    if track_uri_search is not None or track_url_search is not None:
        track_id_str = (track_uri_search
                        if track_uri_search is not None else
                        track_url_search).group('TrackID')
    else:
        track_id_str = None

    if album_uri_search is not None or album_url_search is not None:
        album_id_str = (album_uri_search
                        if album_uri_search is not None else
                        album_url_search).group('AlbumID')
    else:
        album_id_str = None

    if playlist_uri_search is not None or playlist_url_search is not None:
        playlist_id_str = (playlist_uri_search
                           if playlist_uri_search is not None else
                           playlist_url_search).group('PlaylistID')
    else:
        playlist_id_str = None

    if episode_uri_search is not None or episode_url_search is not None:
        episode_id_str = (episode_uri_search
                          if episode_uri_search is not None else
                          episode_url_search).group('EpisodeID')
    else:
        episode_id_str = None

    if show_uri_search is not None or show_url_search is not None:
        show_id_str = (show_uri_search
                       if show_uri_search is not None else
                       show_url_search).group('ShowID')
    else:
        show_id_str = None

    if artist_uri_search is not None or artist_url_search is not None:
        artist_id_str = (artist_uri_search
                         if artist_uri_search is not None else
                         artist_url_search).group('ArtistID')
    else:
        artist_id_str = None

    return track_id_str, album_id_str, playlist_id_str, episode_id_str, show_id_str, artist_id_str


def fix_filename(name):
    """
    Replace invalid characters on Linux/Windows/MacOS with underscores.
    List from https://stackoverflow.com/a/31976060/819417
    Trailing spaces & periods are ignored on Windows.
    >>> fix_filename("  COM1  ")
    '_ COM1 _'
    >>> fix_filename("COM10")
    'COM10'
    >>> fix_filename("COM1,")
    'COM1,'
    >>> fix_filename("COM1.txt")
    '_.txt'
    >>> all('_' == fix_filename(chr(i)) for i in list(range(32)))
    True
    """
    return re.sub(r'[/\\:|<>"?*\0-\x1f]|^(AUX|COM[1-9]|CON|LPT[1-9]|NUL|PRN)(?![^.])|^\s|[\s.]$', "_", name, flags=re.IGNORECASE)
