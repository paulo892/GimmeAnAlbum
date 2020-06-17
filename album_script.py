import sys
import six
import json
import click
import spotipy
import datetime
import colorama
import spotipy.util as util
from termcolor import colored
from pyfiglet import figlet_format
from PyInquirer import (Token, ValidationError, Validator, print_json, prompt,
                        style_from_dict)

# proportion of songs in album saved to consider it unviewed
SONGS_VIEWED_IN_ALBUM_CUTOFF = 0.3

# styles for CLI
style = style_from_dict({
    Token.QuestionMark: '#fac731 bold',
    Token.Answer: '#4688f1 bold',
    Token.Instruction: '',  # default
    Token.Separator: '#cc5454',
    Token.Selected: '#0abf5b',  # default
    Token.Pointer: '#673ab7 bold',
    Token.Question: '',
})


def show_tracks(tracks):
    for i, item in enumerate(tracks['items']):
        track = item['track']
        print("   %d %32.32s %s" % (i, track['artists'][0]['name'],
            track['name']))


# logs data to the command line
def log(string, color, font="slant", figlet=False):
    if colored:
        if not figlet:
            six.print_(colored(string, color))
        else:
            six.print_(colored(figlet_format(
                string, font=font), color))
    else:
        six.print_(string)

# asks user for username
def askUsername():
    questions = [
        {
            'type': 'input',
            'name': 'username',
            'message': 'Please enter your username or user id.'
    }]

    answers = prompt(questions, style=style)
    return answers

# asks user for request type
def askRequest():
    questions = [
        {
            'type': 'list',
            'name': 'request_type',
            'message': 'What would you like to do?',
            'choices': ['Initialize', 'Update', 'Surprise me!']
        }
    ]

    answers = prompt(questions, style=style)
    return answers

# initialize txt file with albums for user inspection
def init_albums(sp, username, token):

    # initialize dict of artists to albums to counts
    artists_to_albums = {}

    # gets user playlists
    res1 = sp.user_playlists(username)
    playlists = res1['items']
    while res1['next']:
        res1 = sp.next(res1)
        playlists.extend(res1['items'])

    # for each playlist...
    for i, playlist in enumerate(playlists):

        # gets the tracks in the playlist
        res2 = sp.playlist_tracks(playlist['id'])
        tracks = res2['items']

        while res2['next']:
            res2 = sp.next(res2)
            tracks.extend(res2['items'])

        # for each track...
        for j, track in enumerate(tracks):

            # extracts artists, album, name
            name = track['track']['id']
            album = track['track']['album']['id']
            artists = [x['id'] for x in track['track']['artists']]

            # skips problem tracks
            if name == 'None' or album == 'None' or None in artists:
                continue

            ## adds the entry to the dict

            # for each artist involved in track...
            for artist in artists:

                # if artist not in dict, adds new entry
                if artist not in artists_to_albums:
                    artists_to_albums[artist] = {}
                    artists_to_albums[artist][album] = [name]

                # if artist in dict...
                else:
                    albums = artists_to_albums[artist]

                    # if album not in dict, adds new entry
                    if album not in albums:
                        albums[album] = [name]

                    # if album in dict, appends track (if not in there already)
                    else:
                        if name not in albums[album]:
                            albums[album].append(name)

    ## builds out txt file with albums that need checking out

    albums_by_artist_to_rec = {}

    # for each artist in above list...
    for k, artist in enumerate(artists_to_albums):

        # extracts artist's name
        artist_name = sp.artist(artist)['name']

        # resets the Spotify object -> seemed to help dropped connections
        sp = spotipy.Spotify(auth=token, requests_timeout=20, retries=10)

        # extracts songs they've listened to, as well as albums
        songs_list_in_albums = artists_to_albums[artist]

        # gets albums from that artist
        res3 = sp.artist_albums(artist)
        all_albums = res3['items']
        ct = 0

        while res3['next']:
            ct += 1
            res3 = sp.next(res3)
            all_albums.extend(res3['items'])

        # TEMP - for debugging
        if (k % 50 == 0):
            print('step:', k)

        # for each of artist's albums...
        for album in all_albums:

            # if user has not saved any songs on album...
            if album['name'] not in songs_list_in_albums:

                # adds the album to the rec list
                if artist_name not in albums_by_artist_to_rec:
                    albums_by_artist_to_rec[artist_name] = [album['name']]
                else:
                    albums_by_artist_to_rec[artist_name].append(album['name'])

            # if user has saved some songs on the album...
            else:
                # counts number of tracks on album
                res4 = sp.album_tracks(album['name'])
                album_tracks = res4['items']

                while res4['next']:
                    res4 = sp.next(res4)
                    album_tracks.extend(res4['items'])

                ct_all = len(album_tracks)

                # counts tracks on album saved by used
                ct_svd = len(songs_list_in_albums[album['name']])

                # calculates proportion
                prop = float(ct_svd) / ct_all

                # if prop greater than threshold, skips the album
                if prop > SONGS_VIEWED_IN_ALBUM_CUTOFF:
                    continue

                # else, adds album to the rec list
                else:
                    if artist_name not in albums_by_artist_to_rec:
                        albums_by_artist_to_rec[artist_name] = [album['name']]
                    else:
                        albums_by_artist_to_rec[artist_name].append(album['name'])

    # logs the date of execution
    albums_by_artist_to_rec['_meta_date_updated'] = datetime.date.today()

    # writes the txt file
    with open('albums_to_listen.txt', 'w+') as file:
        file.write(json.dumps(albums_by_artist_to_rec))


def update_albums(sp, username, token):


@click.command()
def main():
    # CLI displays
    log("Gimme an Album", color="cyan", figlet=True)
    log("Welcome to \'Gimme an Album\'", "cyan")
    log("Press Ctrl^C to exit.", "cyan")

    # requests user ID / username on CLI
    username = askUsername()['username']

    # defines the scope and takes user token
    scope = 'playlist-read-private'
    token = util.prompt_for_user_token(username, scope)

    # if token invalid, returns
    if not token:
        print("Can't get token for", username)
        sys.exit()
    # else...
    else:
        # creates spotipy object for use
        sp = spotipy.Spotify(auth=token, requests_timeout=20, retries=10, )

    # after establishing connection, uses inf loop to take requests
    while (True):
        # takes in request
        request = askRequest()

        # if user requests to initialize list...
        if request['request_type'] == 'Initialize':

            # creates usable list
            init_albums(sp, username, token)

        # else if user requests to update list...
        if request['request_type'] == 'Update':

            # updates existing list
            update_albums(sp, username, token)


if __name__ == '__main__':
    main()