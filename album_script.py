import os
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
from spotipy.oauth2 import SpotifyOAuth

# proportion of songs in album saved to consider it unviewed
SONGS_VIEWED_IN_ALBUM_CUTOFF = 0.75

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
    return answers['username']

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
def init_albums(sp, username, usr_info):

    # initialize dicts of recommended albums and of saved track counts by album
    albums_to_listen_by_artist = usr_info['albums_to_listen_by_artist']
    tracks_saved_within_albums_by_artist = usr_info['tracks_saved_within_albums_by_artist']

    # gets user's playlists
    playlist_objects = sp.user_playlists(username)
    playlists = playlist_objects['items']

    while playlist_objects['next']:
        playlist_objects = sp.next(playlist_objects)
        playlists.extend(playlist_objects['items'])
    
    # for each playlist...
    for i, playlist in enumerate(playlists):

        # gets the tracks in the playlist
        track_objects = sp.playlist_tracks(playlist['id'])
        tracks = track_objects['items']

        while track_objects['next']:
            track_objects = sp.next(track_objects)
            tracks.extend(track_objects['items'])

        # for each track...
        for j, track in enumerate(tracks):

            # extracts artists, album, name
            name = track['track']['id']
            album = track['track']['album']['id']
            artists = [x['id'] for x in track['track']['artists']]

            # skips problem tracks
            if name == 'None' or album == 'None' or (None in artists) or len(artists) == 0:
                continue

            ## adds the track to the 'tracks_saved_within_albums_by_artist' dict

            # for each artist involved in track...
            for artist in artists:

                # if artist has not been seen, adds new entry
                if artist not in tracks_saved_within_albums_by_artist:
                    tracks_saved_within_albums_by_artist[artist] = {album: [name]}

                # else if artist has been seen...
                else:
                    # if album has not been seen, adds new entry to 'tracks_saved_within_albums_by_artist' dict entry
                    if album not in tracks_saved_within_albums_by_artist[artist]:
                        tracks_saved_within_albums_by_artist[artist][album] = [name]

                    # else if album has been seen...
                    else:
                        # if song has not yet been seen, adds it to the list
                        if name not in tracks_saved_within_albums_by_artist[artist][album]:
                            tracks_saved_within_albums_by_artist[artist][album].append(name)

    # updates the user info JSON dict with the dictionary of albums saved
    usr_info['tracks_saved_within_albums_by_artist'] = tracks_saved_within_albums_by_artist

    ## initializes the dict of albums to recommend to the user

    # for each artist in the list of saved artists...
    for k, artist in enumerate(tracks_saved_within_albums_by_artist):

        # extracts artist's name, using the artist ID as a param
        artist_name = sp.artist(artist)['name']

        # resets the Spotify object -> seemed to help dropped connections
        if (k % 50 == 0):
            sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope='playlist-read-private', username=username), requests_timeout=20, retries=10)


        # extracts songs they've listened to, as well as albums
        songs_by_album = tracks_saved_within_albums_by_artist[artist]

        # gets artist albums
        album_objects = sp.artist_albums(artist)
        all_artist_albums = album_objects['items']

        while album_objects['next']:
            album_objects = sp.next(album_objects)
            all_artist_albums.extend(album_objects['items'])

        # TEMP - for debugging
        if (k % 10 == 0):
            print('step:', k)

        # for each of artist's albums...
        for album in all_artist_albums:
            ####

            # if user has not saved any songs on album...
            if album['name'] not in songs_by_album:

                # adds the album to recommendation dict if not already inside
                if artist_name not in albums_to_listen_by_artist:
                    albums_to_listen_by_artist[artist_name] = [album['name']]
                elif album['name'] not in albums_to_listen_by_artist[artist_name]:
                    albums_to_listen_by_artist[artist_name].append(album['name'])

            # if user has saved some songs on the album...
            else:
                # counts number of tracks on album
                album_track_objects = sp.album_tracks(album['name'])
                album_tracks = album_track_objects['items']

                while album_track_objects['next']:
                    album_track_objects = sp.next(album_track_objects)
                    album_tracks.extend(album_track_objects['items'])

                ct_all = len(album_tracks)

                # counts tracks on album saved by user
                ct_svd = len(songs_by_album[album['name']])

                # calculates proportion of songs saved
                prop = float(ct_svd) / ct_all

                # if proportion greater than threshold, skips the album
                if prop > SONGS_VIEWED_IN_ALBUM_CUTOFF:
                    continue

                # else, adds album to recommendation dict if not already in it
                else:
                    if artist_name not in albums_to_listen_by_artist:
                        albums_to_listen_by_artist[artist_name] = [album['name']]
                    elif album['name'] not in albums_to_listen_by_artist[artist_name]:
                        albums_to_listen_by_artist[artist_name].append(album['name'])

    # logs the date of update
    usr_info['albums_to_listen_by_artist'] = albums_to_listen_by_artist

    # returns the updated user info
    return usr_info

def update_albums(sp, username, usr_info):

    # loads list of recommended albums by artist
    albums_to_listen_by_artist = usr_info['albums_to_listen_by_artist']

    # loads list of tracks saved by album and artist
    tracks_saved_within_albums_by_artist = usr_info['tracks_saved_within_albums_by_artist']

    # extracts date of last update
    last_update = usr_info['last_updated']

    # gets user playlists
    # TODO - perform reset as above to minimize chances of connection failing
    res1 = sp.user_playlists(username)
    playlists = res1['items']
    while res1['next']:
        res1 = sp.next(res1)
        playlists.extend(res1['items'])

    trx_to_process = []

    # for each playlist...
    for i, playlist in enumerate(playlists):

        # TODO - if possible, retrieve sorted by addition date to reduce overhead

        # gets the tracks in the playlist
        # TODO - perform reset as above to minimize chances of connection failing
        res2 = sp.playlist_tracks(playlist['id'])
        tracks = res2['items']
        while res2['next']:
            res2 = sp.next(res2)
            tracks.extend(res2['items'])

        # for each track...
        for j, track in enumerate(tracks):

            # extracts the time the track was added
            date_added = track['added_at'].split('T')[0]

            # if addition date > update date
            if date_added > last_update:

                # adds track ID to list of tracks to be processed
                iden = track['track']['id']
                trx_to_process.append(iden)

    # for each track to be processed:
    for iden in trx_to_process:

        # resets the Spotify object
        # TODO - determine if necessary for EVERY new track, or if can be spaced out
        sp = spotipy.Spotify(auth=token, requests_timeout=20, retries=10)

        track = sp.track(iden)

        # extracts album and artists id's
        album = track['album']
        artists = [x['id'] for x in track['artists']]

        # for each artist...
        for artist in artists:

            artist_obj = sp.artist(artist)
            artist_name = artist_obj['name']

            # if the user hasn't saved any of the artist's music...
            if artist not in tracks_saved_within_albums_by_artist:

                # TODO - modularize - create function for adding artist discography to this list

                # gets albums from that artist
                res3 = sp.artist_albums(artist)
                all_albums = res3['items']

                while res3['next']:
                    res3 = sp.next(res3)
                    all_albums.extend(res3['items'])

                listened = False

                # if the track in question is a single, adds it to the "listened" dict
                if len(sp.album_tracks(album['id'])) == 1:
                    tracks_saved_within_albums_by_artist[artist] = [album['id']]
                    listened = True

                # if artist not in rec dict...
                if artist_name not in albums_to_listen_by_artist:
                    # adds all of artist's albums to rec dict
                    albums_to_listen_by_artist[artist_name] = [x['name'] for x in all_albums]

                    # removes single from rec dict
                    if listened and album['id'] in albums_to_listen_by_artist[artist_name]:
                        albums_to_listen_by_artist[artist_name].remove(album['id'])
                
                # if artist in rec dict...
                else:
                    # adds albums that are not already in rec dict 
                    for alb in all_albums:
                        if alb not in albums_to_listen_by_artist[artist_name]:
                            albums_to_listen_by_artist[artist_name].append(alb)
                    
                    # removes single from rec dict
                    # TODO - determine if necessary
                    if listened and album['id'] in albums_to_listen_by_artist[artist_name]:
                        albums_to_listen_by_artist[artist_name].remove(album['id'])

            # if user has saved some of the artist's music...
            else:

                # if user has not saved enough of this album, asks them whether they've listened to it recently
                if album['id'] not in tracks_saved_within_albums_by_artist[artist]:
                    ans = askListen(album['name'], artist_name)['answer']

                    # if they have, adds it to "listened" list and removes from rec list (if needed)
                    if ans == 'Yes':
                        tracks_saved_within_albums_by_artist[artist].append(album['id'])

                        if album['name'] in albums_to_listen_by_artist[artist_name]:
                            albums_to_listen_by_artist[artist_name].remove(album['name'])

                    # if they have not, adds the album to their rec list
                    else:
                        # this should not be reached
                        # TODO - is this true? correct it
                        if album['name'] in albums_to_listen_by_artist[artist_name]:
                            print(album['name'], 'already in recommendation list!')

                        if artist_name in albums_to_listen_by_artist:
                            albums_to_listen_by_artist[artist_name].append(album['name'])
                        else:
                            albums_to_listen_by_artist[artist_name] = [album['name']]

                # if user has "listened" to this album before, continues!
    

    # updates the last updated field
    # TODO - make sure the date looks right after
    albums_to_listen_by_artist['last_updated'] = str(datetime.date.today()

    # updates the user info
    usr_info['albums_to_listen_by_artist'] = albums_to_listen_by_artist
    usr_info['tracks_saved_within_albums_by_artist'] = tracks_saved_within_albums_by_artist

    # returns the updated user info
    return usr_info

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

	# requests user ID from user
    username = askUsername()

    if not bool(username):
        # TODO - process this error
        return

	# defines scope and uses Spotipy authenticator to sign in user
    scope = 'playlist-read-private'
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope, username=username), requests_timeout=20, retries=10)

    # logs the current album that the user is listening to
    log('Current album: ' + usr_info['current_album'], 'cyan')
    
    # after establishing connection, uses infinite loop to take requests
    while (True):

        usr_filename = './user_info/' + username + '_ref.txt'

        # takes in user request
        request = askRequest()['request_type']

        # if request empty, returns
        if not bool(request):
            # TODO - process this outcome
            return

        # if user requests to initialize...
        if request == 'Initialize':

            # if user already has a usr_info file on system, returns
            if os.path.exists('user_info') and os.path.isfile(usr_filename):
                # TODO - process
                return
            
            # creates user info directory if necessary
            elif not os.path.exists('user_info'):
                os.makedirs('./user_info')

            # initializes user info object
            usr_info = {'current_album': '', 'last_updated': str(datetime.date.today()), 'albums_to_listen_by_artist': {}, 'tracks_saved_within_albums_by_artist': {}}

            # performs initializations necessary for the app to work, returning the updated user info
            updated_usr_info = init_albums(sp, username, usr_info)

            # updates user info file
            with open(usr_filename, 'w+') as file:
                file.write(json.dumps(updated_usr_info))

        # else if user requests to update list...
        if request == 'Update':

            # opens the user file to create user info object
            with open(usr_filename, 'w+') as usr_file:

                # if file is empty, initializes it
                if (usr_file.read() == ""):
                    # SHOULDNT GET HERE
                    # TODO - resolve
                else:
                    usr_info = ast.literal_eval(usr_file.read())

            # performs updates to user, returning the updated user info
            updated_usr_info = update_albums(sp, username, usr_info)

            # updates user info file
            with open(usr_filename, 'w+') as file:
                file.write(json.dumps(updated_usr_info))

        ### START HERE
        # else if user requests an album...
        if request == 'Gimme an album!':

            # asks the user if they've finished the previous album
            if rec_albums['_meta_current_album'] != "":
                finished = ask_fin(rec_albums['_meta_current_album'])

                if not bool(finished):
                    return

                finished = finished['fin']

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