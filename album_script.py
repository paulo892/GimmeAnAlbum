import sys
import six
import ast
import json
import click
import spotipy
import datetime
import colorama
import spotipy.util as util
import numpy as np
from termcolor import colored
from pyfiglet import figlet_format
from PyInquirer import (Token, ValidationError, Validator, print_json, prompt,
                        style_from_dict)

# proportion of songs in album saved to consider it unviewed
SONGS_VIEWED_IN_ALBUM_CUTOFF = 0.5

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
            'choices': ['Initialize', 'Update', 'Gimme an album!']
        }
    ]

    answers = prompt(questions, style=style)
    return answers

# asks user for search algorithm
def askAlgo():
    questions = [
        {
            'type': 'list',
            'name': 'algo',
            'message': 'How would you like us to pick it?',
            'choices': ['Inverse sampling w.r.t. album count']
        }
    ]

    answers = prompt(questions, style=style)
    return answers

# asks user whether they've listened to an album recently
def askListen(album, artist):
    questions = [
        {
            'type': 'list',
            'name': 'answer',
            'message': 'Have you listened to \'' + album + '\' by \'' + artist + '\' recently?',
            'choices': ['Yes', 'No']
        }
    ]

    answers = prompt(questions, style=style)
    return answers

# asks user whether they've finished their current album
def ask_fin(cur):
    questions = [
        {
            'type': 'list',
            'name': 'fin',
            'message': 'Have you finished listening to ' + cur[0] + '?',
            'choices': ['Yes', 'No']
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

    # writes the dict of id's to a file
    with open('ids_artists_albums_tracks_saved.txt', 'w+') as file:
        file.write(json.dumps(artists_to_albums))

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

        while res3['next']:
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
    albums_by_artist_to_rec['_meta_date_updated'] = str(datetime.date.today())

    # writes the txt file
    with open('albums_to_listen.txt', 'w+') as file:
        file.write(json.dumps(albums_by_artist_to_rec))


def update_albums(sp, username, token):

    # loads list of recommended albums
    info = open("albums_to_listen.txt", "r")
    contents = info.read()
    rec_albums = ast.literal_eval(contents)
    info.close()

    # loads list of saved albums
    info = open("ids_artists_albums_tracks_saved.txt", "r")
    contents = info.read()
    saved_albums = ast.literal_eval(contents)
    info.close()

    # extracts date of last update
    last_update = rec_albums['_meta_date_updated']

    # gets user playlists
    res1 = sp.user_playlists(username)
    playlists = res1['items']
    while res1['next']:
        res1 = sp.next(res1)
        playlists.extend(res1['items'])

    trx_to_process = []

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

            # extracts the time the track was added
            date_added = track['added_at']
            time_added = date_added.split('T')[0]

            

            # if addition date > update date
            if time_added > last_update:

                # adds track ID to list of tracks to be processed
                iden = track['track']['id']
                trx_to_process.append(iden)

    # DEBUG
    #lst = [sp.track(x)['name'] for x in trx_to_process]
    #print(lst)

    # for each track to be processed:
    for iden in trx_to_process:

        # resets the Spotify object -> seemed to help dropped connections
        sp = spotipy.Spotify(auth=token, requests_timeout=20, retries=10)

        track = sp.track(iden)

        # extracts album and artists id's
        album = track['album']
        artists = [x['id'] for x in track['artists']]

        # for each artist...
        for artist in artists:

            artist_obj = sp.artist(artist)
            artist_name = artist_obj['name']

            # if the user hasn't "listened" to any of the artist's music...
            if artist not in saved_albums:

                # gets albums from that artist
                res3 = sp.artist_albums(artist)
                all_albums = res3['items']

                while res3['next']:
                    res3 = sp.next(res3)
                    all_albums.extend(res3['items'])

                listened = False

                # if the track is a single, adds it to the "listened" dict
                if len(sp.album_tracks(album['id'])) == 1:
                    saved_albums[artist] = [album['id']]
                    listened = True

                # adds all of the appropriate albums to the rec list
                if artist_name not in rec_albums:
                    rec_albums[artist_name] = [x['name'] for x in all_albums]
                    if listened and album['id'] in rec_albums[artist_name]:
                        rec_albums[artist_name].remove(album['id'])
                else:
                    for alb in all_albums:
                        if alb not in rec_albums[artist_name]:
                            rec_albums[artist_name].append(alb)
                    if listened and album['id'] in rec_albums[artist_name]:
                        rec_albums[artist_name].remove(album['id'])

            # if user has "listened" to some of the artist's music...
            else:

                # if user has not "listened" to this album before, 
                # asks them whether they've listened to it recently
                if album['id'] not in saved_albums[artist]:
                    ans = askListen(album['name'], artist_name)['answer']

                    # if they have, adds it to "listened" list and removes from rec list (if needed)
                    if ans == 'Yes':
                        saved_albums[artist].append(album['id'])

                        if album['name'] in rec_albums[artist_name]:
                            rec_albums[artist_name].remove(album['name'])

                    # if they have not, adds the album to their rec list
                    else:
                        # this should not be reached
                        if album['name'] in rec_albums[artist_name]:
                            print('ERROR')

                        if artist_name in rec_albums:
                            rec_albums[artist_name].append(album['name'])
                        else:
                            rec_albums[artist_name] = [album['name']]

                # if user has "listened" to this album before, continues!

    # updates the last updated field
    #rec_albums['_meta_date_updated'] = str(datetime.date.today())
    rec_albums['_meta_date_updated'] = '2020-06-15'

    # writes the txt files
    with open('albums_to_listen.txt', 'w+') as file:
        file.write(json.dumps(rec_albums))

    with open('ids_artists_albums_tracks_saved.txt', 'w+') as file:
        file.write(json.dumps(saved_albums))

def sample_inverse_freq():

    # loads list of recommended albums
    info = open("albums_to_listen.txt", "r")
    contents = info.read()
    rec_albums = ast.literal_eval(contents)
    info.close()

    # creates dict of artist weights
    weight_dict = {k:len(v) for (k,v) in rec_albums.items() if isinstance(rec_albums[k], list)}
    inv_weight_dict = {k:1/v for (k,v) in weight_dict.items()}

    # sums the inverse weights
    inv_weight_sum = sum([inv_weight_dict[x] for x in inv_weight_dict])

    # creates the weighted dict
    weighted_dict = {k:v/inv_weight_sum for (k,v) in inv_weight_dict.items()}

    # samples artist from weighted dict
    sample = np.random.choice(list(weighted_dict.keys()), p=list(weighted_dict.values()))
    
    # generates random album uniformly for sampled artist
    album = np.random.choice(rec_albums[sample])

    # adds album as current listen
    rec_albums['_meta_current_album'] = [album, sample]

    # updates recommended albums file
    with open('albums_to_listen.txt', 'w+') as file:
        file.write(json.dumps(rec_albums))










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

        # loads list of recommended albums
        info = open("albums_to_listen.txt", "r")
        contents = info.read()
        rec_albums = ast.literal_eval(contents)
        info.close()

        if rec_albums['_meta_current_album'] == "":
            log("Current album: ", "cyan")
        else:
            log("Current album: \"" + rec_albums['_meta_current_album'][0] + "\" - " + rec_albums['_meta_current_album'][1], "cyan")

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

        # else if user requests an album...
        if request['request_type'] == 'Gimme an album!':

            # asks the user if they've finished the previous album
            if rec_albums['_meta_current_album'] != "":
                finished = ask_fin(rec_albums['_meta_current_album'])['fin']

                # if they have not, logs and returns
                if finished == 'No':
                    log("This version does not support multiple current albums. Please finish this one and then return!", "cyan")
                    continue

                # else, updates the dict accordingly
                album_list = rec_albums[rec_albums['_meta_current_album'][1]]
                album_list.remove(rec_albums['_meta_current_album'][0])
                rec_albums[rec_albums['_meta_current_album'][1]] = album_list

                # updates recommended albums file
                with open('albums_to_listen.txt', 'w+') as file:
                    file.write(json.dumps(rec_albums))

            # asks user for selection algorithm
            algo = askAlgo()['algo']

            # returns album based on algorithm chosen
            if algo == 'Inverse sampling w.r.t. album count':
                album = sample_inverse_freq()



if __name__ == '__main__':
    main()