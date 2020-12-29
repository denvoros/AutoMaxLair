#   AutoMaxLair
#       v0.4.2
#       Eric Donders
#       2020-12-26

import cv2
import time
import serial
import numpy
import pytesseract
import pickle
import enchant
import configparser
from datetime import datetime
from copy import copy, deepcopy
from MaxLairInstance import MaxLairInstance
from Pokemon_Data import matchup_scoring

# Load configuration from config file
config = configparser.ConfigParser()
config.read('Config.ini')

COM_PORT = config['default']['COM_PORT']
VIDEO_INDEX = int(config['default']['VIDEO_INDEX'])
BOSS = config['default']['BOSS']
BASE_BALL = config['default']['BASE_BALL']
BASE_BALLS = int(config['default']['BASE_BALLS'])
LEGENDARY_BALL = config['default']['LEGENDARY_BALL']
LEGENDARY_BALLS = int(config['default']['LEGENDARY_BALLS'])
MODE = config['default']['MODE']
DYNITE_ORE = int(config['default']['DYNITE_ORE'])
pytesseract.pytesseract.tesseract_cmd = config['default']['TESSERACT_PATH']

boss_pokemon_path = config['pokemon_data_paths']['Boss_Pokemon']
rental_pokemon_path = config['pokemon_data_paths']['Rental_Pokemon']
boss_matchup_LUT_path = config['pokemon_data_paths']['Boss_Matchup_LUT']
rental_matchup_LUT_path = config['pokemon_data_paths']['Rental_Matchup_LUT']
rental_pokemon_scores_path = config['pokemon_data_paths']['Rental_Pokemon_Scores']

# Define button press sequences for different stages of the Dynamax Adventure
join_sequence = ((0, 0, b'a'),  # Initiate conversation with scientist
                 (0.5, 1, b'a'),  # Click again in case the first click was needed to connect the controller
                 (1.5, 2, b'a'),  # Click through conversation
                 (3, 3, b'a'),  # "Yes, please!"
                 (4.5, 4, b'a'),  # Click through conversation
                 (6, 5, b'a'),  # Click through conversation
                 (7.5, 6, b'a'),  # Select Pokemon (top of the list)
                 (8.5, 7, b'a'),  # "Do you want to save your adventure so far?"
                 (10, 8, b'a'),  # Yes
                 (14, 9, b'v'),  # Move down to "Don't invite others"
                 (15, 10, b'a'),  # Confirm
                 (20, 11, b'0'))  # End this sequence and choose a Pokemon

path_sequence = ((0, 0, b'a'),  # Select a path
                 (4, 1, b'0'))


def join(inst):
    """Join a Dynamax Adventure and choose a Pokemon."""
    stage_time = time.time() - inst.timer
    for step in join_sequence:
        if stage_time > step[0] and inst.substage == step[1]:
            inst.com.write(step[2])
            # print(step[2])
            inst.substage += 1

    # Pokemon selection subroutine
    if stage_time > join_sequence[-1][0] and inst.substage == join_sequence[-1][1] + 1:
        # Read Pokemon names from specified regions
        pokemon_list = inst.read_selectable_pokemon('join')
        pokemon_scores = []
        for pokemon in pokemon_list:
            # Match each name to a rental Pokemon object with preconfigured moves, stats, etc.
            name = pokemon.name
            inst.log(name)
            # Score each Pokemon by its average performance against the remaining path
            rental_weight = 3
            boss_weight = 2
            score = (rental_weight * inst.rental_scores[name] + boss_weight * inst.boss_matchups[name][inst.boss]) / (
                        rental_weight + boss_weight)
            pokemon_scores.append(score)
            inst.log('Score for ' + name + ':\t%0.2f' % score)
        selection_index = pokemon_scores.index(max(pokemon_scores))
        inst.pokemon = pokemon_list[selection_index]
        inst.reset_stage()
        inst.substage = 99 - selection_index  # Go to the appropriate stage for navigating to the desired Pokemon
    elif inst.substage == 97 and stage_time > 1:
        inst.com.write(b'v')
        inst.reset_stage()
        inst.substage = 98
    elif inst.substage == 98 and stage_time > 1:
        inst.com.write(b'v')
        inst.reset_stage()
        inst.substage = 99
    elif inst.substage == 99 and stage_time > 1:
        inst.com.write(b'a')
        inst.reset_stage()
        inst.substage = 100
    elif inst.substage == 100 and stage_time > 30:
        inst.reset_stage()
        inst.log('Choosing a path...')
        return 'path'
    return 'join'  # If not finished this stage, run it again next loop


def path(inst) -> str:
    """Choose a path to follow."""
    stage_time = time.time() - inst.timer
    for step in path_sequence:
        if stage_time > step[0] and inst.substage == step[1]:
            inst.com.write(step[2])
            # print(step[2])
            inst.substage += 1
    if stage_time > path_sequence[-1][0]:
        inst.timer = time.time()
        inst.substage = 0
        print('Detecting where the path led...')
        return 'detect'
    return 'path'  # If not finished this stage, run it again next loop


def detect(inst) -> str:
    """Detect whether the chosen path has led to a battle, scientist, backpacker, or fork in the path.
    :type inst: MaxLairInstance
    """
    text = inst.read_text(((0, 0.6), (1, 1)), invert=True)
    if 'Fight' in text or 'appeared' in text:
        # Battle has started and the move selection screen is up
        inst.log('Battle starting...')
        return 'battle'
    elif 'backpacker' in text:
        # Backpacker encountered so choose an item
        inst.log('Backpacker encountered...')
        return 'backpacker'
    elif 'swapping' in text:
        # Scientist appeared to deal with that
        inst.log('Scientist encountered...')
        return 'scientist'
    elif 'path' in text:
        # Fork in the path appeared to choose where to go
        inst.log('Choosing a path...')
        return 'path'
    return 'detect'  # If not finished this stage, run it again next loop


def battle(inst) -> str:
    """Choose moves during a battle and detect whether the battle has ended."""
    stage_time = time.time() - inst.timer

    # Initialize subroutine
    if inst.substage == 0:
        inst.timer = time.time()
        inst.substage += 1

    # Detection subroutine
    elif inst.substage == 1:
        text = inst.read_text(((0, 0.6), (1, 1)), invert=True)  # Read text from the bottom section of the screen
        inst.timer = time.time()
        # print(text)
        if 'Fight' in text:
            inst.substage = 2  # Go to move selection sequence
        elif 'Cheer On' in text:
            inst.dmax_timer = -1
            inst.dynamax_available = False
            if inst.pokemon.dynamax:
                inst.pokemon.dynamax = False
                inst.move_index = 0
            inst.substage = 8
        elif 'Catch' in text:
            inst.reset_stage()
            inst.log('Catching boss...')
            return 'catch'  # Go to catch sequence
        elif 'blown' in text:
            inst.reset_stage()
            inst.log('You lose :(. Quitting...')
            return 'select_pokemon'  # Go to quit sequence
        elif 'gathered around' in text:
            inst.dynamax_available = True
            inst.pokemon.dynamax = False
            inst.dmax_timer = -1
        elif 'can dynamax now' in text.lower():
            inst.dynamax_available = False
            inst.pokemon.dynamax = False
            inst.dmax_timer = -1

    # Move selection subroutine
    elif inst.substage == 2 and stage_time > 1:
        # Fight
        if inst.opponent == None:
            # Try to detect the opponent if it wasn't already detected
            if inst.num_caught < 3:
                inst.substage = 30
                inst.timer = time.time()
                return 'battle'
            else:
                inst.opponent = inst.boss_pokemon[BOSS]
        inst.com.write(b'a')
        # Handle the Dynamax timer
        if inst.dmax_timer == 0:
            inst.dmax_timer = -1
            inst.move_index = 0
            inst.pokemon.dynamax = False
        elif inst.dmax_timer > 0:
            inst.dmax_timer -= 1
        # Choose the best move to use, and whether or not to Dynamax (if it's available)
        best_move_index = matchup_scoring.select_best_move(
            inst.pokemon, inst.opponent, inst.rental_pokemon)
        move = inst.pokemon.max_moves[best_move_index] if inst.pokemon.dynamax else inst.pokemon.moves[best_move_index]
        if inst.dynamax_available:
            default_score = matchup_scoring.calculate_move_score(inst.pokemon, best_move_index, inst.opponent,
                                                                 teammates=inst.rental_pokemon)
            inst.pokemon.dynamax = True  # Temporary
            best_max_move_index = matchup_scoring.select_best_move(inst.pokemon, inst.opponent, inst.rental_pokemon)
            if matchup_scoring.calculate_move_score(inst.pokemon, best_max_move_index, inst.opponent,
                                                    teammates=inst.rental_pokemon) > default_score:
                best_move_index = best_max_move_index
                move = inst.pokemon.max_moves[best_max_move_index]
            else:
                inst.dynamax_available = False  # Choose not to Dynamax this time
                move = inst.pokemon.moves[best_move_index]
            inst.pokemon.dynamax = False  # Revert previous temporary change
        inst.log('Best move against ' + inst.opponent.name + ': ' + move.name + ' (index ' + str(best_move_index) + ')')
        # Go to the appropriate stage for navigating to the correct move
        while inst.move_index > 3:
            inst.move_index -= 4
        to_move = (best_move_index - inst.move_index)
        while to_move < 0:  # Cycle back through the bottom to a previous move
            to_move += 4
        if inst.dynamax_available:
            inst.substage = 15 - to_move  # Goto dynamax
        else:
            inst.substage = 6 - to_move  # Goto move
        # Reset timer
        inst.timer = time.time() + 0.5

    elif 3 <= inst.substage <= 5 and stage_time > 0.75:
        # Navigate to the correct move
        inst.com.write(b'v')
        inst.move_index += 1
        inst.timer = time.time()
        inst.substage += 1
    elif inst.substage == 6 and stage_time > 1.5:
        inst.com.write(b'a')
        inst.substage += 1
        inst.timer = time.time()
    elif inst.substage == 7 and stage_time > 1.5:
        inst.com.write(b'a')
        # Reduce PP accordingly
        if inst.move_index > 3:
            inst.move_index -= 4
        inst.pokemon.PP[inst.move_index] -= 1
        if inst.opponent and inst.opponent.ability == 'Pressure':
            inst.pokemon.PP[inst.move_index] -= 1
        inst.substage += 1
    elif inst.substage == 8 and stage_time > 2.5:
        inst.com.write(b'a')
        inst.substage += 1
    # Attempt to escape to the "Fight" screen in case something (no PP, choice lock) went wrong
    elif inst.substage == 9 and stage_time > 3.5:
        inst.com.write(b'b')
        inst.substage += 1
    elif inst.substage == 10 and stage_time > 4.5:
        inst.com.write(b'b')
        inst.substage = 1  # Return to substage 1 which will decide what needs to be done next

    # Dynamax initiation subroutine
    elif 12 <= inst.substage <= 15 and stage_time > 3:
        inst.com.write(b'<')
        inst.substage += 4
    elif 16 <= inst.substage <= 19 and stage_time > 4:
        inst.com.write(b'a')
        inst.substage += 4
    elif 20 <= inst.substage <= 23 and stage_time > 5:
        # Dynamax and then choose a move as usual
        inst.dmax_timer = 2
        inst.pokemon.dynamax = True
        inst.dynamax_available = False
        inst.timer = time.time() + 0.5
        to_move = 23 - inst.substage
        inst.substage = 6 - to_move

    # Opponent detection subroutine (called only when the boss name is not detected at the start of the battle)
    elif inst.substage == 30 and stage_time > 1:
        inst.com.write(b'y')
        inst.substage += 1  # Navigate to the pokemon status screen
    elif inst.substage == 31 and stage_time > 2:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 32 and stage_time > 3:
        inst.com.write(b'l')
        inst.substage += 1
    elif inst.substage == 33 and stage_time > 4:
        inst.opponent = inst.read_selectable_pokemon('battle')[0]
        inst.com.write(b'b')
        inst.timer = time.time()
        inst.substage += 1
    elif inst.substage == 34 and stage_time > 1.5:
        inst.com.write(b'b')
        inst.substage = 35
    elif inst.substage == 35 and stage_time > 2:
        inst.com.write(b'b')
        inst.substage = 1

    # If not finished this stage, run it again next loop
    return 'battle'


def catch(inst):
    """Catch each boss after defeating it."""
    stage_time = time.time() - inst.timer
    if inst.substage == 0:  # Initialize
        inst.com.write(b'a')
        inst.timer = time.time() + 0.5
        inst.substage = 20 if inst.get_target_ball() == 'DEFAULT' else 10

    # Ball selection subroutine
    elif inst.substage == 10 and stage_time > 1:
        # print(inst.check_ball()) # DEBUG
        if inst.get_target_ball() in inst.check_ball():
            # Target ball reached; go to capture subroutine
            inst.substage = 20
        else:
            # Go to the next ball and check again
            inst.com.write(b'<')
            inst.timer = time.time()

    # Capture subroutine
    if inst.substage == 20 and stage_time > 1:
        inst.timer = time.time()
        inst.com.write(b'a')
        inst.record_ball_use()
        inst.substage = 30 if inst.num_caught < 4 else 100

    # Pokemon checking subroutine
    elif inst.substage == 30 and stage_time > 30:
        # Choose whether to keep the Pokemon if it's one of the first 3 bosses, or wrap up the run otherwise
        pokemon = inst.read_selectable_pokemon('catch')[0]
        # Give the new and existing Pokemon a score based on their performance against the remainder of the run (including the boss)
        rental_weight = 3 - inst.num_caught
        boss_weight = 2
        score = (rental_weight * inst.rental_scores[pokemon.name] + boss_weight * inst.boss_matchups[pokemon.name][
            inst.boss]) / (rental_weight + boss_weight)
        existing_score = inst.HP * (rental_weight * inst.rental_scores[
            inst.pokemon.name] + boss_weight * matchup_scoring.evaluate_matchup(inst.pokemon,
                                                                                inst.boss_pokemon[inst.boss],
                                                                                inst.rental_pokemon)) / (
                                     rental_weight + boss_weight)
        inst.log('Score for ' + pokemon.name + ':\t%0.2f' % score)
        inst.log('Score for ' + inst.pokemon.name + ':\t%0.2f' % existing_score)
        if score > existing_score:
            # Choose to swap your existing Pokemon for the new Pokemon
            inst.com.write(b'a')
            inst.pokemon = pokemon
        else:
            # Choose not to take the new Pokemon
            inst.com.write(b'b')
        inst.reset_stage()
        inst.log('Detecting where the path led...')
        return 'detect'

    elif inst.substage == 100 and stage_time > 35:
        # Run was successful; wrap up and check the caught Pokemon
        inst.log('Congratulations! Checking the haul from this run...')
        inst.reset_stage()
        return 'select_pokemon'
    return 'catch'  # If not finished this stage, run it again next loop


def backpacker(inst):
    """Choose an item from the backpacker."""
    stage_time = time.time() - inst.timer
    if inst.substage == 0:
        inst.timer = time.time()
        inst.substage += 1
    elif inst.substage == 1 and stage_time > 5:
        inst.com.write(b'a')  # Pick whatever the first item is
        inst.substage += 1
    elif inst.substage == 2 and stage_time > 10:
        inst.reset_stage()
        inst.log('Detecting where the path led...')
        return 'detect'
    return 'backpacker'  # If not finished this stage, run it again next loop


def scientist(inst):
    """Take (or not) a Pokemon from the scientist."""
    stage_time = time.time() - inst.timer
    if inst.substage == 0:
        inst.timer = time.time()
        inst.substage += 1
    elif inst.substage == 1 and stage_time > 3:
        inst.com.write(b'b')  # Don't take a new Pokemon for now
        inst.substage += 1
    elif inst.substage == 2 and stage_time > 4:
        inst.reset_stage()
        inst.log('Detecting where the path led')
        return 'detect'
    return 'scientist'  # If not finished this stage, run it again next loop


def select_pokemon(inst):
    """Check Pokemon caught during the run and keep one if it's shiny."""
    stage_time = time.time() - inst.timer
    if inst.substage == 0 and stage_time > 5:
        inst.log('Checking caught Pokemon...')
        inst.com.write(b'^')  # Put cursor on last Pokemon
        inst.substage += 1
    elif inst.substage == 1 and stage_time > 6:
        inst.com.write(b'a')  # Click Pokemon
        inst.substage += 1
    elif inst.substage == 2 and stage_time > 7:
        inst.com.write(b'v')  # Move the cursor down
        inst.substage += 1
    elif inst.substage == 3 and stage_time > 8:
        inst.com.write(b'a')  # Summary screen
        inst.timer = time.time()
        inst.substage += (5 - inst.num_caught)
    elif (4 <= inst.substage <= 7) and stage_time > 2:
        # Check for shininess and move to the next Pokemon if not
        if inst.check_shiny():
            inst.timer = time.time()
            inst.log('******************************\n\nShiny found!\n\n******************************')
            display_results(inst, '', time.time(), log=True)
            inst.shinies_found += 1
            if inst.substage == 4:
                return 'done'  # End whenever a shiny legendary is found
            else:
                inst.substage = 50  # Goto take Pokemon
        elif stage_time > 3:
            # Is using ball saver mode, reset the game if the legendary was caught and it wasn't shiny
            if 'ball saver' in inst.mode.lower() and inst.num_caught == 4:
                if inst.check_sufficient_ore(inst.consecutive_resets + 2):
                    inst.substage = 420
                    inst.timer = time.time()
                    return 'select_pokemon'
                else:
                    inst.log('Insufficient Dynite Ore to reset again. Quitting...')
                    return 'done'
            # Otherwise continue to check the other Pokemon
            elif inst.substage < 7:
                inst.com.write(b'^')  # Check next Pokemon
            inst.timer = time.time()
            inst.substage += 1
    elif inst.substage == 8 and stage_time > 1:
        # Reset the game if the seed should be preserved
        if ('strong boss' in inst.mode.lower()) and (inst.num_caught == 4) and inst.check_sufficient_ore(inst.consecutive_resets + 1):
            inst.substage = 420
            inst.timer = time.time()
            return 'select_pokemon'
        # Don't take any Pokemon
        inst.com.write(b'b')
        inst.substage += 1
    elif inst.substage == 9 and stage_time > 4:
        inst.com.write(b'b')
        inst.substage += 1
    elif inst.substage == 10 and stage_time > 5:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 11 and stage_time > 7:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 12 and stage_time > 9:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 13 and stage_time > 21:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 14 and stage_time > 22:
        inst.com.write(b'a')
        inst.consecutive_resets = 0
        inst.dynite_ore += inst.num_caught + (2 if inst.num_caught == 4 else 0)
        # Depending on how well the run went, the dialogue changes. Adjust the stage to account for this behaviour
        if inst.num_caught < 1:
            return 'done'  # Debug; winning 0 battles currently breaks the bot
        if inst.num_caught < 3:
            inst.substage = 100
        elif inst.num_caught < 4:
            inst.substage = 18
        else:
            inst.substage += 2
        inst.timer = time.time()
    elif inst.substage == 15 and stage_time > 2:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 16 and stage_time > 4:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 17 and stage_time > 6:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 18 and stage_time > 8:
        inst.com.write(b'a')
        inst.substage = 100
        inst.timer = time.time()

    # Reset game suboutine
    #   Added with the help of user fawress on the Pokemon Automation Discord
    elif inst.substage == 420 and stage_time > 1:
        inst.log('Resetting game...')
        inst.com.write(b'h')  # Go Home
        inst.base_balls += 3
        inst.legendary_balls += 1
        inst.consecutive_resets += 1
        inst.dynite_ore -= inst.calculate_ore_cost(inst.consecutive_resets)
        inst.substage += 1
    elif inst.substage == 421 and stage_time > 3:
        inst.com.write(b'x')  # Close game
        inst.substage += 1
    elif inst.substage == 422 and stage_time > 5:
        inst.com.write(b'a')  # Close Game, add delay
        inst.substage += 1
    elif inst.substage == 423 and stage_time > 8:
        inst.com.write(b'a')  # Start Game
        inst.substage += 1
    elif inst.substage == 424 and stage_time > 10:
        inst.com.write(b'a')  # Select Profile
        inst.substage += 1
    elif inst.substage == 425 and stage_time > 30:
        inst.com.write(b'a')  # Load Save after a long delay
        inst.substage += 1
    elif inst.substage == 426 and stage_time > 40:
        inst.com.write(b'a')  # Interact with scientist, delay before this too
        inst.substage += 1
    elif inst.substage == 427 and stage_time > 43:
        inst.com.write(b'b')  # Seems you keep
        inst.substage += 1
    elif inst.substage == 428 and stage_time > 46:
        inst.com.write(b'b')  # Hard On Teammates
        inst.substage += 1
    elif inst.substage == 429 and stage_time > 49:
        inst.com.write(b'b')  # Before I
        inst.substage += 1
    elif inst.substage == 430 and stage_time > 52:
        inst.com.write(b'b')  # Can you do that
        inst.substage += 1
    elif inst.substage == 431 and stage_time > 55:
        inst.com.write(b'a')  # Yes/No
        inst.substage += 1
    elif inst.substage == 432 and stage_time > 58:
        inst.com.write(b'b')  # To the end
        inst.substage = 100
        inst.timer = time.time()

    # Take selected Pokemon subroutine
    elif inst.substage == 50 and stage_time > 1:
        inst.com.write(b'b')
        inst.substage += 1
    elif inst.substage == 51 and stage_time > 4:
        display_results(inst, '', time.time(), log=True)
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 52 and stage_time > 5:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 53 and stage_time > 6:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 54 and stage_time > 7:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 55 and stage_time > 8:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 56 and stage_time > 12:
        inst.com.write(b'a')
        inst.substage += 1
    elif inst.substage == 57 and stage_time > 22:
        inst.substage = 13
        inst.timer = time.time()

    # Wrap up and prepare for the next run (or quit if out of balls)
    elif inst.substage == 100 and stage_time > 2:
        if inst.num_caught == 4:
            inst.wins += 1
        inst.runs += 1
        inst.reset_run()
        if inst.check_sufficient_balls():
            inst.log('Preparing for another run...')
            return 'initialize'
        else:
            inst.log('Out of balls. Quitting...')
            return 'done'
    return 'select_pokemon'  # If not finished this stage, run it again next loop


def display_results(inst, stage, frame_start, log=False):
    """Display video from the Switch alongside some annotations describing the run sequence."""
    # Calculate some statistics for display
    elapsed_time = time.time() - frame_start
    fps = 'High' if elapsed_time <= 0 else '%0.1f' % (1 / (elapsed_time))
    
    win_percent = None if inst.runs == 0 else round(100 * inst.wins / inst.runs)
    time_per_run = None if inst.runs == 0 else (datetime.now() - inst.start_date) / inst.runs

    # Expand the image with blank space for writing results
    frame = cv2.copyMakeBorder(inst.get_frame(
        stage=stage), 0, 0, 0, 200, cv2.BORDER_CONSTANT)
    height, width, channels = frame.shape

    # Construct arrays of text and values to display
    labels = (
    'Run #', 'Stage: ', 'Substage: ', 'FPS: ', 'Base balls: ', 'Legendary balls: ', 'Pokemon caught: ', 'Pokemon: ',
    'Opponent: ', 'Win percentage: ', 'Time per run: ', 'Shinies found: ', 'Dynite Ore: ')
    values = (str(inst.runs + 1), stage, str(inst.substage), fps, str(inst.base_balls), str(inst.legendary_balls),
              str(inst.num_caught), str(inst.pokemon), str(inst.opponent), str(win_percent) + '%', str(time_per_run),
              str(inst.shinies_found), str(inst.dynite_ore))

    for i in range(len(labels)):
        cv2.putText(frame, labels[i] + values[i], (width - 195, 25 + 25 * i), cv2.FONT_HERSHEY_PLAIN, 1,
                    (255, 255, 255), 2, cv2.LINE_AA)
        if log:
            inst.log(labels[i] + values[i])

    # Display
    cv2.imshow('Output', frame)
    if log:
        # Save a copy of the final image
        cv2.imwrite(inst.filename[:-8] + '_cap.png', frame)


def main_loop():
    """Main loop. Runs until a shiny is found or the user manually quits by pressing 'Q'."""

    # Connect to the Teensy over a serial port
    com = serial.Serial(COM_PORT, 9600, timeout=0.05)
    print('Connecting to ' + com.port + '...')
    while not com.is_open:
        try:
            com.open()
        except SerialException:
            pass
    print('Connected!')

    # Open the video capture
    print('Opening the video connection...')
    cap = cv2.VideoCapture(VIDEO_INDEX)
    if str(cap) is None:
        print(
            'Failed to open the video connection. Check the config file and ensure no other application is using the video input.')
        return

    # Create a Max Lair Instance object to store information about each run and the entire sequence of runs
    instance = MaxLairInstance(BOSS, (BASE_BALL, BASE_BALLS, LEGENDARY_BALL, LEGENDARY_BALLS), com, cap, datetime.now(),
                               (boss_pokemon_path, rental_pokemon_path, boss_matchup_LUT_path, rental_matchup_LUT_path,
                                rental_pokemon_scores_path), MODE, DYNITE_ORE)

    stage = 'initialize'

    # DEBUG overrides for starting the script mid-run
    ##    instance.pokemon = instance.rental_pokemon['Swampert']
    ##    instance.num_caught = 1
    ##    stage = 'detect'
    ##    instance.consecutive_resets = 1

    # Map stages to the appropriate function to execute when in each stage
    actions = {'join': join, 'path': path, 'detect': detect, 'battle': battle, 'catch': catch, 'backpacker': backpacker,
               'scientist': scientist, 'select_pokemon': select_pokemon}

    # Start event loop after initializing the timer
    frame_start = time.time()
    while stage != 'done':
        if stage == 'initialize':
            instance.com.write(b'b')
            # Instantiate a new Max Lair instance
            instance.log('Run #' + str(instance.runs + 1) + ' started!')
            time.sleep(1)
            instance.reset_stage()
            stage = 'join'

        # Execute the appropriate function for the current stage, and store the returned stage for the next loop
        stage = actions[stage](instance)

        # Display a frame of the incoming video and some stats after each loop
        display_results(instance, stage, frame_start)
        frame_start = time.time()

        # Read responses from microcontroller
        instance.com.read(instance.com.inWaiting())

        # Quit if the Q key is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # When finished, clean up video and serial connections
    display_results(instance, stage, frame_start, log=True)
    instance.cap.release()
    com.close()
    # input('Press Enter to exit.')
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main_loop()
