import os
import re
import shutil
import time
from typing import Any, Tuple, List

from librespot.audio.decoders import AudioQuality
from librespot.metadata import TrackId
from ffmpy import FFmpeg
from pydub import AudioSegment
from tqdm import tqdm

from const import TRACKS, ALBUM, NAME, ITEMS, DISC_NUMBER, TRACK_NUMBER, IS_PLAYABLE, ARTISTS, IMAGES, URL, \
    RELEASE_DATE, ID, TRACKS_URL, SAVED_TRACKS_URL, TRACK_STATS_URL, DOWNLOAD_FORMAT, \
    CHUNK_SIZE, SKIP_EXISTING_FILES, ANTI_BAN_WAIT_TIME, OVERRIDE_AUTO_WAIT, BITRATE, CODEC_MAP, EXT_MAP, \
    DOWNLOAD_REAL_TIME, DURATION_MS, SKIP_FILE_WITHOUT_ID, GENERAL_ERROR_RETRIES, ROOT_PATH
from utils import fix_filename, set_audio_tags, set_music_thumbnail, create_download_directory, \
    get_directory_song_ids, add_to_directory_song_ids, get_other_directory_songs_info
from zspotify import ZSpotify


def get_saved_tracks() -> list:
    """ Returns user's saved tracks """
    songs = []
    offset = 0
    limit = 50

    while True:
        resp = ZSpotify.invoke_url_with_params(
            SAVED_TRACKS_URL, limit=limit, offset=offset)
        offset += limit
        songs.extend(resp[ITEMS])
        if len(resp[ITEMS]) < limit:
            break

    return songs


def get_song_info(song_id) -> Tuple[List[str], str, str, Any, Any, Any, Any, Any, Any]:
    """ Retrieves metadata for downloaded songs """
    info = ZSpotify.invoke_url(f'{TRACKS_URL}?ids={song_id}&market=from_token')

    artists = []
    for data in info[TRACKS][0][ARTISTS]:
        artists.append(data[NAME])
    album_name = info[TRACKS][0][ALBUM][NAME]
    name = info[TRACKS][0][NAME]
    image_url = info[TRACKS][0][ALBUM][IMAGES][0][URL]
    release_year = info[TRACKS][0][ALBUM][RELEASE_DATE].split('-')[0]
    disc_number = info[TRACKS][0][DISC_NUMBER]
    track_number = info[TRACKS][0][TRACK_NUMBER]
    scraped_song_id = info[TRACKS][0][ID]
    is_playable = info[TRACKS][0][IS_PLAYABLE]
    duration_ms = info[TRACKS][0][DURATION_MS]

    return artists, album_name, name, image_url, release_year, disc_number, track_number, scraped_song_id, is_playable, duration_ms

def get_song_duration(song_id: str) -> float:
    """ Retrieves duration of song in second as is on spotify """

    resp = ZSpotify.invoke_url(f'{TRACK_STATS_URL}{song_id}')

    # get duration in miliseconds
    ms_duration = resp['duration_ms']
    # convert to seconds
    duration = float(ms_duration)/1000

    # debug
    # print(duration)
    # print(type(duration))

    return duration

# noinspection PyBroadException
def download_track(track_id: str, download_directory:str, prefix=False, prefix_value='', disable_progressbar= False) \
        -> str|None:
    """ Downloads raw song audio from Spotify """

    try:
        (artists, album_name, name, image_url, release_year, disc_number,
         track_number, scraped_song_id, is_playable, duration_ms) = get_song_info(track_id)

        song_name = fix_filename(artists[0]) + ' - ' + fix_filename(name)
        if prefix:
            song_name = f'{prefix_value.zfill(2)} - {song_name}' if prefix_value.isdigit(
            ) else f'{prefix_value} - {song_name}'

        short_filename = f'{song_name}.{EXT_MAP.get(ZSpotify.get_config(DOWNLOAD_FORMAT).lower())}'
        filename = os.path.join(download_directory, short_filename)

        check_name = os.path.isfile(filename) and os.path.getsize(filename)
        check_id = scraped_song_id in get_directory_song_ids(download_directory)

        resolved_by_copy = False

        if ZSpotify.get_config(SKIP_EXISTING_FILES) and not check_name and not check_id:
            # Look if we have this song in another folder
            data_other_folders = get_other_directory_songs_info(ZSpotify.get_config(ROOT_PATH),download_directory)

            for folder, song_id_info in data_other_folders.items():
                if scraped_song_id in song_id_info:
                    # If we have it, copy it and stop further process
                    source_file = os.path.join(ZSpotify.get_config(ROOT_PATH),folder, song_id_info[scraped_song_id])
                    shutil.copy2(source_file, filename)
                    print('\n###   SKIPPING:', song_name, '(SONG COPIED FROM OTHER FOLDER)   ###')
                    resolved_by_copy = True
                    break

        # a song with the same name is installed but not present on id file
        if not resolved_by_copy and not check_id and check_name:
            # Two options: add id to the file and skip it, or download it under different filename
            if ZSpotify.get_config(SKIP_FILE_WITHOUT_ID):
                add_to_directory_song_ids(download_directory, scraped_song_id, short_filename)
                check_id = True
            else:
                c = len([file for file in os.listdir(download_directory)
                         if re.search(f'^{song_name}_', file)]) + 1

                filename = os.path.join(
                    download_directory, f'{song_name}_{c}.{EXT_MAP.get(ZSpotify.get_config(DOWNLOAD_FORMAT))}')


    except Exception as e:
        print('###   SKIPPING SONG - FAILED TO QUERY METADATA   ###')
        print(e)
    else:
        if not is_playable:
            print('\n###   SKIPPING:', song_name, '(SONG IS UNAVAILABLE)   ###')
        else:
            if check_id and check_name and ZSpotify.get_config(SKIP_EXISTING_FILES):
                print('\n###   SKIPPING:', song_name, '(SONG ALREADY EXISTS)   ###')
                return scraped_song_id
            else:
                if track_id != scraped_song_id:
                    track_id = scraped_song_id

                if perform_download(track_id, download_directory, filename, song_name, duration_ms,
                                    disable_progressbar):
                    set_audio_tags(filename, artists, name, album_name,
                                   release_year, disc_number, track_number)
                    set_music_thumbnail(filename, image_url)

                    # add song id to download directory's .song_ids file
                    if not check_id:
                        add_to_directory_song_ids(download_directory, scraped_song_id, short_filename)

                    if not ZSpotify.get_config(OVERRIDE_AUTO_WAIT):
                        time.sleep(ZSpotify.get_config(ANTI_BAN_WAIT_TIME))

                    return scraped_song_id
                else:
                    print('\n###   SKIPPING:', song_name, '(NUMBER OF RETRIES EXCEEDED)   ###')
def perform_download(track_id: str, download_directory:str, filename: str, song_name: str, duration_ms: int,
                     disable_progressbar=False, intent = 1):
    if intent > ZSpotify.get_config(GENERAL_ERROR_RETRIES):
        return False

    try:
        track_id = TrackId.from_base62(track_id)
        stream = ZSpotify.get_content_stream(
            track_id, ZSpotify.DOWNLOAD_QUALITY)
        create_download_directory(download_directory)
        total_size = stream.input_stream.size
        time_start = time.time()
        download_size = 0

        with open(filename, 'wb') as file, tqdm(
                desc=song_name,
                total=total_size,
                unit='B',
                unit_scale=True,
                unit_divisor=1024,
                disable=disable_progressbar
        ) as p_bar:
            for chunk in range(int(total_size / ZSpotify.get_config(CHUNK_SIZE)) + 1):
                data = stream.input_stream.stream().read(ZSpotify.get_config(CHUNK_SIZE))
                p_bar.update(file.write(data))
                download_size += len(data)
                if ZSpotify.get_config(DOWNLOAD_REAL_TIME):
                    delta_real = time.time() - time_start
                    delta_want = (download_size / total_size) * (duration_ms / 1000)
                    if delta_want > delta_real:
                        real_time = delta_want - delta_real
                        time.sleep(real_time)

        convert_audio_format(filename)
        return True

    except Exception as e:
        print('###   SKIPPING:', song_name,
              '(GENERAL DOWNLOAD ERROR)   ###')
        print(e)
        if os.path.exists(filename):
            os.remove(filename)

        if not ZSpotify.get_config(OVERRIDE_AUTO_WAIT):
            # Increment wait time to avoid permanent failure.
            # time = base anti ban time * 2^n-1, based on BEB (Binary Exponential Backoff)
            failure_wait_time = ZSpotify.get_config(ANTI_BAN_WAIT_TIME) * (2 ** (intent - 1))
            time.sleep(failure_wait_time)

        intent = intent + 1
        return perform_download(track_id, download_directory, filename, song_name, duration_ms, disable_progressbar,
                                intent)
def get_segment_duration(segment):
    """ Returns playback duration of given audio segment """
    sound = AudioSegment(
        data = segment,
        sample_width = 2,
        frame_rate = 44100,
        channels = 2
    )
    duration = len(sound) / 5000
    return duration


def convert_audio_format(filename) -> None:
    """ Converts raw audio into playable file """
    temp_filename = f'{os.path.splitext(filename)[0]}.tmp'
    os.replace(filename, temp_filename)

    download_format = ZSpotify.get_config(DOWNLOAD_FORMAT).lower()
    file_codec = CODEC_MAP.get(download_format, "copy")
    if file_codec != 'copy':
        bitrate = ZSpotify.get_config(BITRATE)
        if not bitrate:
            if ZSpotify.DOWNLOAD_QUALITY == AudioQuality.VERY_HIGH:
                bitrate = '320k'
            else:
                bitrate = '160k'
    else:
        bitrate = None

    output_params = ['-c:a', file_codec]
    if bitrate:
        output_params += ['-b:a', bitrate]

    ff_m = FFmpeg(
        global_options=['-y', '-hide_banner', '-loglevel error'],
        inputs={temp_filename: None},
        outputs={filename: output_params}
    )
    ff_m.run()
    if os.path.exists(temp_filename):
        os.remove(temp_filename)
