"""Init file for AutoMaxLair

Establishes logger and exposes functions to the `automaxlair`
name space.
"""

# imports for the matchup scoring functions
from automaxlair.matchup_scoring import (
    ability_damage_multiplier, type_damage_multiplier, 
    print_matchup_summary, select_best_move, evaluate_matchup, 
    calculate_move_score, calculate_average_damage, calculate_damage, 
    get_max_move_power)

# imports for the Pokemon data selection
from automaxlair.Pokemon import Pokemon

# imports for the Move data type
from automaxlair.Move import Move
