# -*- coding: utf-8 -*-
"""Package_Pokemon.py - Matchup Scoring Script

This script takes in all of the data surrounding Pokemon that are available for use
in the Dynamax Adventures and then determines
how well they perform in every possible matchup. This script may take
a considerable amount of time to run, so please be patient when running,
or just use the pre-processed pickle files available in the data/ directory.

Note:
    This script was written by Eric Donders (ercdndrs).
    The initial date was 2020-11-27
"""

import csv
import logging
import logging.handlers
import multiprocessing as mp
import os
import pickle
import sys
from copy import copy, deepcopy
from functools import partial

import tqdm

# automaxlair importing for this script is in the parent directory
sys.path.insert(1, os.path.join(sys.path[0], '..'))
from automaxlair import Move, Pokemon, evaluate_matchup, get_max_move_power

# this is the name of the logger, not the file that's created for logging purposes
LOG_NAME = "packagePokemon"

BASE_DATA_FOLDER = "data"

# one minus the max number of cores for efficiency
MAX_NUM_THREADS = mp.cpu_count() - 1

# enable the debug logs being saved to the logging file
# this does not affect the console data
ENABLE_DEBUG_LOGS = True


def package_spread_move_list():
    """Loads in spread move data from the text file

    Returns:
        list: A list of data regarding spread moves
    """

    logger = logging.getLogger(LOG_NAME)

    logger.info("Beginning to process spread move file.")

    spread_move_list = []
    # read the spread moves text file, and process all of the data
    with open(os.path.join(BASE_DATA_FOLDER, 'Spread_moves.txt'), newline='\n') as tsvfile:
        spamreader = csv.reader(tsvfile, delimiter='\t', quotechar='"')
        for row in spamreader:
            spread_move_list.append(row[0])

    logger.info('Read and processed spread move file.')

    return spread_move_list


def package_move_list(spread_move_list):
    """Loads in regular move data from the text file

    Requires the spread_move_list for further processing.

    Returns:
        dict: A dictionary of all moves
    """

    logger = logging.getLogger(LOG_NAME)

    logger.info('Beginning to process the move file.')

    move_list = {}
    # read the moves text file, and process the data by putting them in move data
    with open(os.path.join(BASE_DATA_FOLDER, 'Moves.csv'), newline='\n') as csvfile:
        spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in spamreader:
            Name = row[0]
            Type = row[1].title()
            Category = row[2]
            if row[3] == '?':
                Power = 0
            else:
                Power = int(row[3])
            if row[4] == '?':
                Accuracy = 1
            else:
                Accuracy = float(row[4])/100
            if row[5] == '?':
                PP = 0
            else:
                PP = int(row[5])
            TM = row[6]
            Effect = row[7]
            if row[8] == '?':
                Probability = 0
            else:
                Probability = int(row[8])
            multiplier = 1
            if 'the user, the stronger' in Effect:
                # Applies to Electro Ball, Heavy Slam, Gyro Ball, etc.
                Power = 65
            if ('on first turn' in Effect) or ('next turn' in Effect) or ('second turn' in Effect):
                multiplier *= 0.5
            if ('consumed' in Effect) or ('Fails' in Effect) or ('Can only be' in Effect):
                multiplier = 0
            if ('twice in one turn' in Effect) or ('twice in a row' in Effect):
                multiplier *= 2
            elif 'Hits 2-5 times' in Effect:
                multiplier *= 2.2575
            elif 'Attacks thrice with more power each time.' in Effect:
                multiplier *= 94.14/20/Accuracy
            elif '2 turns later' in Effect:
                multiplier *= 1/3
            move_list[Name] = Move(Name, Type, Category, Power, Accuracy, PP, TM, Effect, Probability, is_spread=(
                Name in spread_move_list), correction_factor=multiplier)

    logger.info('Read and processed move file.')

    return move_list


def package_max_move_list():
    """Loads in max move data from the text file

    Returns:
        dict: A collection of all max moves
        Move: An object of move data for a status max move
    """

    logger = logging.getLogger(LOG_NAME)

    logger.info('Beginning to process max move file.')

    max_move_list = {}
    status_max_move = None
    with open(os.path.join(BASE_DATA_FOLDER, 'Max_moves.txt'), newline='\n') as tsvfile:
        spamreader = csv.reader(tsvfile, delimiter='\t', quotechar='"')
        for row in spamreader:
            Name = row[0]
            Type = row[1].title()
            Effect = row[2]
            # check for max guard
            if Name != 'Max Guard':
                max_move_list[Type] = Move(
                    Name, Type, 0, 0, 1, None, None, Effect, 100)
            # if it *is* max guard, our "status_max_move" is then just a plain move
            else:
                status_max_move = Move(Name, Type, 'Status',
                                       0, 1, None, None, Effect, 100)

    logger.info('Read and processed max move file.')

    return max_move_list, status_max_move


def package_pokemon_base_stats():
    """Loads in Pokemon base stats data from the text file

    Returns:
        dict: A dictinoary of all Pokemon and their stats
    """

    logger = logging.getLogger(LOG_NAME)

    logger.info('Beginning to process Pokemon base stats.')

    pokemon_base_stats = {}
    with open(os.path.join(BASE_DATA_FOLDER, 'All_Pokemon_stats.txt'), newline='\n') as tsvfile:
        spamreader = csv.reader(tsvfile, delimiter='\t', quotechar='"')
        for row in spamreader:
            Name = row[2]
            stats = (int(row[3]), int(row[4]), int(row[5]),
                     int(row[6]), int(row[7]), int(row[8]))
            pokemon_base_stats[Name] = stats

    logger.info('Read and processed Pokemon stats file.')

    return pokemon_base_stats


def package_pokemon_types():
    """Loads in pokemon types base data from the text file

    Returns:
        dict: A dictionary of all Pokemon and their types
    """

    logger = logging.getLogger(LOG_NAME)

    logger.info('Beginning to process Pokemon type data.')

    pokemon_types = {}
    with open(os.path.join(BASE_DATA_FOLDER, 'Pokemon_types.csv'), newline='\n') as csvfile:
        spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in spamreader:
            Name = row[0]
            types = (row[1], row[2])
            pokemon_types[Name] = types

    logger.info('Read and processed Pokemon types file.')

    return pokemon_types


def package_rental_pokemon_data(move_list, max_move_list, status_max_move, pokemon_types, pokemon_base_stats):
    """Takes the previously extracted Pokemon data, and gets only rentals

    Parameters:
        move_list (dict): The dictionary of all moves
        max_move_list (dict): The dictionary of all max moves
        status_max_move (Move): The object describing a status max move
        pokemon_types (dict): The dictionary of all Pokemon and their types
        pokemon_base_stats (dict): The dictionary of all Pokemon and their base stats

    Returns:
        dict: A complete dictionary of all Pokemon available for rental
    """

    logger = logging.getLogger(LOG_NAME)

    logger.info("Beginning to process rental Pokemon data.")

    rental_pokemon = {}
    with open(os.path.join(BASE_DATA_FOLDER, 'Rental_Pokemon.txt'), newline='\n') as file:
        spamreader = csv.reader(file)
        i = 0
        dump = []
        for row in spamreader:
            dump.append(row)
        while i < len(dump):
            while len(dump[i]) == 0:
                i += 1
            name = dump[i][0]
            i += 1
            while len(dump[i]) > 0:
                i += 1
            while len(dump[i]) == 0:
                i += 1
            ability = dump[i][0]
            i += 1
            level = int(dump[i][0].split()[1])
            i += 2
            moves = []
            max_moves = []
            while i < len(dump) and len(dump[i]) > 0:
                move = copy(move_list[dump[i][0]])
                moves.append(move)
                if ability == 'Skill Link' and 'Hits 2-5 times' in move.effect:
                    move.power *= 5/2.1575
                if move.base_power > 0:
                    max_move = copy(max_move_list[move.type])
                    max_move.power = get_max_move_power(move)
                else:
                    max_move = copy(status_max_move)
                max_move.category = move.category
                max_move.PP = move.PP
                max_moves.append(max_move)
                i += 1
            counter = 2
            if name in rental_pokemon:
                logger.warn('Duplicate entry found! - ' + name)
            rental_pokemon[name] = Pokemon(
                name, ability, pokemon_types[name], pokemon_base_stats[name], moves, max_moves, level)

    logger.info('Read and processed rental Pokemon file.')

    return rental_pokemon


def package_boss_pokemon(move_list, max_move_list, status_max_move, pokemon_types, pokemon_base_stats):
    """Processes the boss Pokemon data

    Parameters:
        move_list (dict): The dictionary of all moves
        max_move_list (dict): The dictionary of all max moves
        status_max_move (Move): The object describing a status max move
        pokemon_types (dict): The dictionary of all Pokemon and their types
        pokemon_base_stats (dict): The dictionary of all Pokemon and their base stats

    Returns:
        dict: A complete dictionary of all Pokemon available for rental
    """

    logger = logging.getLogger(LOG_NAME)

    logger.info("Beginning to process the Boss Pokemon")

    boss_pokemon = {}
    with open(os.path.join(BASE_DATA_FOLDER, 'Boss_Pokemon.txt'), newline='\n') as file:
        spamreader = csv.reader(file)
        i = 0
        dump = []
        for row in spamreader:
            dump.append(row)
        while i < len(dump):
            while len(dump[i]) == 0:
                i += 1
            name = dump[i][0]
            logger.debug(f"Found Pokemon: {name}")
            i += 1
            while len(dump[i]) > 0:
                i += 1
            while len(dump[i]) == 0:
                i += 1
            ability = dump[i][0]
            i += 1
            level = int(dump[i][0].split()[1])
            i += 2
            moves = []
            max_moves = []
            while i < len(dump) and len(dump[i]) > 0:
                move = move_list[dump[i][0]]
                moves.append(move)
                if move.power > 0:
                    max_move = copy(max_move_list[move.type])
                    max_move.power = get_max_move_power(move)
                else:
                    max_move = copy(status_max_move)
                max_move.category = move.category
                max_move.PP = move.PP
                max_moves.append(max_move)
                i += 1
            boss_pokemon[name] = Pokemon(
                name, ability, pokemon_types[name], pokemon_base_stats[name], moves, max_moves, level)

    logger.info('Read and processed boss Pokemon file.')

    return boss_pokemon


def iterate_through_defenders(defenders, rental_pokemon, attacker):
    """This is a wrapper function that matches up a list of defenders with an attacker

    Defenders is an iterable dictionary of all of the defender data.
    Please note that this function is primarily designed for use with 
    the Python multiprocessing package.

    Parameters:
        defenders (dict): The dictionary of all defending Pokemon for iteration
        rental_pokemon (dict): The collection of all rental Pokemon
        attacker (Pokemon): The object describing the attacker Pokemon

    Returns:
        dict: The dictionary containing all matchup scores
    """
    logger = logging.getLogger(LOG_NAME)

    logger.debug("Beginning processing for attacker: %s", attacker[0])

    matchups = {}
    for idefender, (_, defender) in enumerate(defenders.items()):
        # the 1 in attacker is because we're iterating over the items, and it passes in as a tuple
        matchups[defender.name] = evaluate_matchup(
            attacker[1], defender, rental_pokemon)
        logger.debug(
            f"  ({idefender+1:02d}/{len(defenders):02d}) %s vs %s gives {matchups[defender.name]:02.05f} -- Matchup complete!", defender.name, attacker[0], )

    logger.debug("Finished for attacker: %s", attacker[0])

    return matchups


def calculate_boss_matchup_LUT(rental_pokemon, boss_pokemon, queue):
    """Processes the boss matchup data

    Parameters:
        rental_pokemon (dict): The dictionary of all rental Pokemon for iteration
        boss_pokemon (dict): The collection of all boss Pokemon for iteration
        queue (multiprocessing.Queue): The queue object used for logging

    Returns:
        dict: The dictionary containing all matchup scores for bosses
    """

    logger = logging.getLogger(LOG_NAME)

    logger.info("Processing the boss matchup data with all rental pokemon")
    logger.info(
        f"There are {len(boss_pokemon)} Boss Pokemon to iterate through")
    logger.info(
        f"There are {len(rental_pokemon)} Rental Pokemon that will be accounted for")
    logger.info(
        f"That means there are a total of {len(boss_pokemon) * len(rental_pokemon)} iterations!")

    partial_func = partial(iterate_through_defenders,
                           boss_pokemon, rental_pokemon)

    # set up parallel pool for easy processing, also call our initialization and give it our queue
    pool = mp.Pool(MAX_NUM_THREADS, worker_init, [queue])

    # then we can have the pool iterate through the whole shebang
    all_matchups = list(tqdm.tqdm(
        pool.imap(partial_func, rental_pokemon.items()),
        ncols=80, total=len(rental_pokemon),
        desc="Boss Matchup"
    ))

    pool.close()
    pool.join()

    logger.info(
        "Finished processing matchup data. Now extracting calculations and assigning to Pokémon")

    # then we just unpack from the list into a dictionary from the rental pokemon names
    boss_matchup_LUT = {}

    for iattacker, (_, attacker) in enumerate(rental_pokemon.items()):
        boss_matchup_LUT[attacker.name] = all_matchups[iattacker]

    logger.info('Created boss matchup LUT.')

    return boss_matchup_LUT


def calculate_rental_mathcup_LUT(rental_pokemon, queue):
    """Calculates the rental matchup scores for all possible rental Pokemon

    Parameters:
        rental_pokemon (dict): The dictionary of all rental Pokemon for iteration
        queue (multiprocessing.Queue): The queue object used for logging

    Returns:
        dict: The dictionary containing all matchup scores for rental Pokemon
    """

    logger = logging.getLogger(LOG_NAME)

    logger.info("Calculating the rental matchups")
    logger.info(f"There are {len(rental_pokemon)} Pokemon to iterate through")
    logger.info(
        f"That means there will be {(len(rental_pokemon)-1)**2} iterations total!")

    # rental pokemon iterate through rental pokemon
    # use deep copy to make sure it's an actual copy of the array that won't get messed with
    partial_func = partial(iterate_through_defenders,
                           deepcopy(rental_pokemon), rental_pokemon)  # {})

    # set up parallel pool for easy processing, also call our initialization and give it our queue
    pool = mp.Pool(MAX_NUM_THREADS, worker_init, [queue])

    # then we can have the pool iterate through the whole shebang
    all_matchups = list(tqdm.tqdm(
        pool.imap(partial_func, rental_pokemon.items()),
        ncols=80, total=len(rental_pokemon),
        desc="Rental Matchup"
    ))

    pool.close()
    pool.join()

    logger.info(
        "Finished processing matchup data. Now extracting calculations and assigning to Pokémon")

    # then we just unpack from the list into a dictionary from the rental pokemon names
    rental_matchup_LUT = {}
    rental_pokemon_scores = {}
    total_score = 0

    for iattacker, (_, attacker) in enumerate(rental_pokemon.items()):
        # get the results for the attacker, which is the index of the pokemon
        results = all_matchups[iattacker]
        rental_matchup_LUT[attacker.name] = results

        # the attacker score is then just the sum of all of the value results
        attacker_score = sum(results.values())
        rental_pokemon_scores[attacker.name] = attacker_score

        # the total score is then given the attacker score
        total_score += attacker_score

    # modify the rental pokemon scores by the total score
    for key in rental_pokemon_scores:
        rental_pokemon_scores[key] /= (total_score/len(rental_pokemon))

    logger.info('Computed rental matchup LUT.')

    # then return!
    return rental_matchup_LUT, rental_pokemon_scores


def worker_init(q):
    """Basic function that initializes the thread workers to know where to send logs to.

    Parameters:
        q (multiprocessing.Queue): The queue object used for the multiprocessing
    """
    # all records from worker processes go to qh and then into q
    qh = logging.handlers.QueueHandler(q)
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if ENABLE_DEBUG_LOGS else logging.INFO)
    logger.addHandler(qh)


def main(queue):
    """This main function just runs through the functions in the right order

    Putting this here allows us to potentially call functions in this file later 
    for easier usage later.

    Parameters:
        q (multiprocessing.Queue): The queue object used for the multiprocessing
    """

    # first call the spread move list function
    spread_move_list = package_spread_move_list()

    # then call the regular move list
    move_list = package_move_list(spread_move_list)

    # then call the max move list
    max_move_list, status_max_move = package_max_move_list()

    # then call pokemon base stats
    pokemon_base_stats = package_pokemon_base_stats()

    # then call pokemon types
    pokemon_types = package_pokemon_types()

    # then get the rental pokemon data
    rental_pokemon = package_rental_pokemon_data(
        move_list, max_move_list, status_max_move, pokemon_types, pokemon_base_stats)

    # save the rental pokemon
    logger.info("Saving the rental Pokemon!")
    with open(os.path.join(BASE_DATA_FOLDER, '_Rental_Pokemon.pickle'), 'wb') as file:
        pickle.dump(rental_pokemon, file)

    # then get the boss pokemon data
    boss_pokemon = package_boss_pokemon(
        move_list, max_move_list, status_max_move, pokemon_types, pokemon_base_stats)

    # save the boss pokemon
    logger.info("Saving the Boss Pokémon")
    with open(os.path.join(BASE_DATA_FOLDER, '_Boss_Pokemon.pickle'), 'wb') as file:
        pickle.dump(boss_pokemon, file)

    # then calculate the boss matchups
    boss_matchup_LUT = calculate_boss_matchup_LUT(
        rental_pokemon, boss_pokemon, queue)

    # save the boss matchup data
    logger.info("Saving the Boss Matchup Data")
    with open(os.path.join(BASE_DATA_FOLDER, '_Boss_Matchup_LUT.pickle'), 'wb') as file:
        pickle.dump(boss_matchup_LUT, file)

    # then calculate the rental matchups
    rental_matchup_LUT, rental_pokemon_scores = calculate_rental_mathcup_LUT(
        rental_pokemon, queue)

    # save the rental pokemon matchup data
    logger.info("Saving the Rental Matchup Data")
    with open(os.path.join(BASE_DATA_FOLDER, '_Rental_Matchup_LUT.pickle'), 'wb') as file:
        pickle.dump(rental_matchup_LUT, file)
    # and then save the rental pokemon scores
    logger.info("Saving the Rental Pokemon Scores")
    with open(os.path.join(BASE_DATA_FOLDER, '_Rental_Pokemon_Scores.pickle'), 'wb') as file:
        pickle.dump(rental_pokemon_scores, file)

    logger.info("All data has been saved!")


if __name__ == "__main__":

    logger = logging.getLogger(LOG_NAME)

    q = mp.Queue()

    # set the base logging level to the lowest possible!
    logger.setLevel(logging.DEBUG if ENABLE_DEBUG_LOGS else logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s | %(name)s |  %(levelname)s: %(message)s')

    # quickconfig the logger for all info to control the output
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)

    # spit out debug info to the log file
    fileHandler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join('logs', 'packagePokemonScript.log'),
        when='midnight',
        backupCount=30)
    fileHandler.setFormatter(formatter)
    fileHandler.setLevel(logging.DEBUG if ENABLE_DEBUG_LOGS else logging.INFO)

    # add these handlers to the queue listener
    ql = logging.handlers.QueueListener(q, fileHandler)
    ql.start()

    # then add the file handlers
    logger.addHandler(console)
    logger.addHandler(fileHandler)

    # call main
    print("Initializing the program...")
    main(q)

    # quit the queue listener
    ql.stop()

    # then we're done
    print("Program complete. Pickle files are now in the data/ folder")
