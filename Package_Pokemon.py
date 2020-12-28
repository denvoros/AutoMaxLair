# Package_Pokemon
#   Eric Donders
#   2020-11-27
#   Read information on Pokemon and construct sets of rental and boss Pokemon used in Dynamax Adventures

import csv
import logging
import logging.handlers
import os
import pickle
from copy import copy

from automaxlair import Move, Pokemon, evaluate_matchup, get_max_move_power

logger = logging.getLogger("packagePokemon")

BASE_DATA_FOLDER = "data"


def package_spread_move_list():
    """Loads in spread move data from the text file
    """

    global logger

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
    """

    global logger

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
            move_list[Name] = Move(Name, Type, Category, Power, Accuracy, PP, TM, Effect, Probability, is_spread=(
                Name in spread_move_list), correction_factor=multiplier)

    logger.info('Read and processed move file.')

    return move_list


def package_max_move_list():
    """Loads in max move data from the text file
    """

    global logger

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
    """

    global logger

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
    """

    global logger

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
    """

    global logger

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
    """

    global logger

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


def calculate_boss_matchup_LUT(rental_pokemon, boss_pokemon):
    """Processes the boss matchup data
    """

    global logger

    logger.info("Processing the boss matchup data with all rental pokemon")
    logger.info(f"There are {len(boss_pokemon)} Boss Pokemon to iterate through")
    logger.info(f"There are {len(rental_pokemon)} Rental Pokemon that will be accounted for")
    logger.info(f"That means there are a total of {len(boss_pokemon) * len(rental_pokemon)} iterations!")

    boss_matchup_LUT = {}

    # iterate through attackers (rental pokemon)
    for iattacker, (_, attacker) in enumerate(rental_pokemon.items()):
        matchups = {}

        logger.debug(f"({iattacker+1:03d}/{len(rental_pokemon):03d}) Attacker is: {attacker}")

        # then iterate through the defenders (bosses)
        for idefender, (_, defender) in enumerate(boss_pokemon.items()):

            logger.debug(f"  ({idefender+1:02d}/{len(boss_pokemon):02d}) Defender is: {defender}")

            matchups[defender.name] = evaluate_matchup(
                attacker, defender, rental_pokemon)

        boss_matchup_LUT[attacker.name] = matchups

        logger.info('Finished computing matchups for ' + str(attacker))

    logger.info('Computed boss matchup LUT.')

    return boss_matchup_LUT


def calculate_rental_mathcup_LUT(rental_pokemon):
    """Calculates the rental matchup scores for all possible rental Pokemon
    """

    global logger

    rental_matchup_LUT = {}
    rental_pokemon_scores = {}
    total_score = 0

    logger.info("Calculating the rental matchups")
    logger.info(f"There are {len(rental_pokemon)} Pokemon to iterate through")

    # double iteration of the rental pokemon to determine matchups
    for _, attacker in rental_pokemon.items():
        matchups = {}
        attacker_score = 0

        logger.info("Computing matchups for " + str(attacker))

        for _, defender in rental_pokemon.items():
            matchups[defender.name] = evaluate_matchup(
                attacker, defender, rental_pokemon)
            attacker_score += matchups[defender.name]

        rental_matchup_LUT[attacker.name] = matchups
        rental_pokemon_scores[attacker.name] = attacker_score
        total_score += attacker_score

        logger.info('Finished computing matchups for ' + str(attacker))

    for key in rental_pokemon_scores:
        rental_pokemon_scores[key] /= (total_score/len(rental_pokemon))

    logger.info('Computed rental matchup LUT.')

    return rental_matchup_LUT, rental_pokemon_scores


def main():
    """This main function just runs through the functions in the right order

    Putting this here allows us to potentially call functions later for easier
    usage later.
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
    boss_matchup_LUT = calculate_boss_matchup_LUT(rental_pokemon, boss_pokemon)

    # save the boss matchup data
    logger.info("Saving the Boss Matchup Data")
    with open(os.path.join(BASE_DATA_FOLDER, '_Boss_Matchup_LUT.pickle'), 'wb') as file:
        pickle.dump(boss_matchup_LUT, file)
    
    # then calculate the rental matchups
    rental_matchup_LUT, rental_pokemon_scores = calculate_rental_mathcup_LUT(
        rental_pokemon)

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

    # set the base logging level to the lowest possible!
    logger.setLevel(logging.DEBUG)

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
    fileHandler.setLevel(logging.DEBUG)

    # then add the file handlers
    logger.addHandler(console)
    logger.addHandler(fileHandler)

    # call main
    print("Initializing the program...")
    main()

    # then we're done
    print("Program complete. Pickle files are now in the data/ folder")
