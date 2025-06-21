"""
FE4 Arena Win Calculator

Usage should be pretty obvious once you run it.

Author: ssinback but mostly actually written by ChatGPT (thanks pal!)
Kudos especially goes to ChatGPT for remembering that Dynamic Programming is a
thing! I learned in school but 100% would not have remembered it if I wrote
this from scratch myself lol.

Did I check the math? No, but it seems basically correct to me.

Stored data eg. weapon stats, enemy characteristics, etc. gets generated as you
go, because I did not want to do all the data entry all at once.

Ideas for later expansion:
  - Reverse-engineer opponent stats from accumulated displayed hit rates etc. This could
    lead to more prediction-oriented but likely accurate win predictions, without the user
    having to actually start the combat to check the displayed hit rates.
  - Criticals and other combat skills can trigger in the Arena if characters have them
  - Enemy skills/items are also missing (this can be major esp. for Generals with shield rings)
  - Saved characters could be updated using the CLI (tbh I find just editing the JSON files
    completely fine, but it could be a nice vibe)
  - Allow for tweaking character stats by e.g. accounting for rings, etc
  - Clean argparsey usage strings would be good style

Big-brain game design type thoughts/reminders to myself:
  - The DP (Dynamic Programming) win chance calculation is just a number. But one thing
    we all love about the Arena is the thrill of the fight, which is not something that is just
    a single percent chance. For example:
    - If Dew is doing 1 HP chip and his opponent has 0 percent hit chance, that fight will take
      forever and be super boring.
    - Similar hit percent chances and damage outputs are boring

  - Future ideas for fight "texture" metrics:
    - Expected number of turns to finish the fight (could highlight “grind fights”)
    - Standard deviation of number of turns (nail-biters = high variance, foregone = low variance)
    - Probability of stalemate (neither side deals damage, or only 1 HP damage with very low hit)
    - Longest likely branch before fight resolution (a proxy for tedium or excitement)
    - “Swinginess” or volatility score (fights with wide damage ranges and moderate hit %s)
    - Probability of both units dying in the same round (rare but spicy)

  - Could also log/print some example fight paths from the DP traversal:
    - “Sample win route” or “sample loss route”
    - “Most likely sequence of events”
    - Helpful for narrative clarity or drama visualization

  - This could be an amazing design/debug tool if I ever make my own SRPG.
    The whole point isn’t just "what’s the win chance," but “does the fight feel right?”

Anyway if you fork this or find it useful, feel free to delete all those thoughts lol.
"""
from __future__ import annotations

import json
import os
from collections import OrderedDict
from enum import Enum, IntEnum
from pprint import pformat
from typing import Callable, Optional

import numpy as np

WEAPONS_FILE = "weapons.json"
OPPONENTS_FILE = "opponents.json"


class CharacterInputMode(IntEnum):
    STORED = 1  # Use stored characters.json for name lookup and save/update behavior
    MANUAL = 2  # Enter stats manually, do not store or load
    # Future idea: support ring modifiers etc?

    @staticmethod
    def from_input(s: str) -> CharacterInputMode:
        if not s.isdigit():
            raise ValueError("Input must be a digit")
        return CharacterInputMode(int(s))


def format_stats(stats: OrderedDict) -> str:
    """
    Format character or weapon stats for pretty printing.
    """
    # pformat already gets a lot of the job done for us, so start with that
    s = pformat(dict(stats), sort_dicts=False, indent=2)
    # Shave the initial { and final } off of s to make it even prettier
    # initial '{' is replaced with a ' ' (preserves indentation); final '}' is simply removed
    lines = s.splitlines()
    if not lines:
        return ""
    lines[0] = lines[0].replace('{', ' ', 1)
    if lines[-1].endswith('}'):      # it should, it's a pformatted dict
        lines[-1] = lines[-1].rsplit('}', 1)[0]  # remove the final '}'
    # Now trim ' and , characters out
    for i, line in enumerate(lines):
        line = line.replace("'", "")
        line = line.replace(",", "")
        lines[i] = line

    return '\n'.join(lines)


def capitalize(s: str) -> str:
    """
    Helper for use as a cast_method with sanitize_input below
    """
    return s.capitalize()


def sanitize_input(prompt: str, cast_method: Callable = lambda x: x):
    """
    Helper function to sanitize user input.
    Prompts the user with the given prompt text and calls cast_method on it.

    The default cast_method doesn't change the input, but common cast_methods might be int,
    capitalize, or CharacterInputMode.from_input, etc.
    """
    return cast_method(input(prompt).strip().lower())


def load_data(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.load(f, object_pairs_hook=OrderedDict)
    return OrderedDict()


def save_data(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)


weapons = load_data(WEAPONS_FILE)
opponents = load_data(OPPONENTS_FILE)


def get_input_ints(prompt, fields):
    """
    Prompt the user using the given prompt text to input data for the given fields.
    """
    print(f"\n{prompt}")
    result = OrderedDict()
    for field in fields:
        result[field] = sanitize_input(f'  {field}: ', cast_method=int)
    return result


def choose_character_input_mode():
    print("\nChoose character stat input mode:")
    print("  1. Use stored characters.json (name lookup, save/update behavior)")
    print("  2. Enter stats manually (do not store or load)")
    choice = sanitize_input("Enter choice (1 or 2): ", CharacterInputMode.from_input)
    return choice


def manual_character_entry():
    return get_input_ints("Enter character stats (manual mode, not saved)", 
        ["Str", "Mag", "Skill", "Speed", "Luck", "Def", "Res", "HP"])


def get_or_add_weapon():
    name = sanitize_input("Enter weapon name: ")
    if name in weapons:
        print(f"Loaded existing weapon: {name}")
        print("Weapon stats:")
        print(format_stats(weapons[name]))
        return weapons[name]
    else:
        data = get_input_ints(f"Enter stats for new weapon '{name}'", ["Might", "Hit", "Weight"])
        data["DamageType"] = sanitize_input("  Type (physical/magic): ")
        # Opponent properties are different if you use a bow, because it's 2-range only, so this
        # attribute helps with opponent lookup.
        data["OpponentType"] = sanitize_input(
            "  Weapon type (normal/bow): ",
            lambda x: 'ranged' if x == 'bow' else 'normal')

        weapons[name] = data
        save_data(WEAPONS_FILE, weapons)
        return data


def get_or_add_opponent():
    chapter = sanitize_input("Chapter number: ")
    arena = sanitize_input("Arena level (1–7): ")

    # Will defer inference to actual weapon choice later
    return chapter, arena  # key information used later


def get_or_add_character():
    name = sanitize_input("Enter character name: ", cast_method=capitalize)
    characters = load_data("characters.json")
    
    if name in characters:
        print(f"Loaded existing character: {name}")
        print("Character stats:")
        print(format_stats(characters[name]))
        return characters[name]
    else:
        data = get_input_ints(f"Enter stats for new character '{name}'", 
            ["Str", "Mag", "Skill", "Speed", "Luck", "Def", "Res", "HP"])
        characters[name] = data
        save_data("characters.json", characters)
        return data

def compute_hit(skill, luck, weapon_hit):
    return min((weapon_hit + skill * 2 + luck // 2), 100)

def compute_atk(strength, weapon_might):
    return strength + weapon_might

def compute_as(speed, weapon_weight):
    return speed - weapon_weight

def compute_win_chance(
    player_hp,
    enemy_hp,
    player_hit,
    player_dmg,
    enemy_hit,
    enemy_dmg,
    doubling: str
):
    # Create a DP table: dp[Beowulf HP][Enemy HP] = win chance
    dp = np.zeros((player_hp + 1, enemy_hp + 1))
    dp[0, :] = 0     # Player dead
    dp[:, 0] = 1     # Enemy dead

    # Define possible hit/miss outcomes per attack
    p_phit = player_hit / 100
    p_emhit = enemy_hit / 100
    p_pmiss = 1 - p_phit
    p_emmiss = 1 - p_emhit

    # Depending on doubling state, we use different round outcome structures
    if doubling == "enemy" or doubling == "unknown":
        # Player gets 1 attack, Enemy gets 2
        round_outcomes = [
            (player_dmg, 2 * enemy_dmg, p_phit * p_emhit * p_emhit),
            (player_dmg, enemy_dmg, p_phit * (2 * p_emhit * p_emmiss)),
            (player_dmg, 0, p_phit * p_emmiss * p_emmiss),
            (0, 2 * enemy_dmg, p_pmiss * p_emhit * p_emhit),
            (0, enemy_dmg, p_pmiss * (2 * p_emhit * p_emmiss)),
            (0, 0, p_pmiss * p_emmiss * p_emmiss),
        ]
    elif doubling == "player":
        # Player gets 2, Enemy gets 1
        round_outcomes = [
            (2 * player_dmg, enemy_dmg, p_phit * p_phit * p_emhit),
            (player_dmg, enemy_dmg, 2 * p_phit * p_pmiss * p_emhit),
            (0, enemy_dmg, p_pmiss * p_pmiss * p_emhit),
            (2 * player_dmg, 0, p_phit * p_phit * p_emmiss),
            (player_dmg, 0, 2 * p_phit * p_pmiss * p_emmiss),
            (0, 0, p_pmiss * p_pmiss * p_emmiss),
        ]
    else:  # 'none'
        # Both get 1 attack
        round_outcomes = [
            (player_dmg, enemy_dmg, p_phit * p_emhit),
            (player_dmg, 0, p_phit * p_emmiss),
            (0, enemy_dmg, p_pmiss * p_emhit),
            (0, 0, p_pmiss * p_emmiss),
        ]

    # Fill DP table
    for b_hp in range(1, player_hp + 1):
        for e_hp in range(1, enemy_hp + 1):
            prob = 0
            for d_beo, d_opp, p in round_outcomes:
                next_b = max(b_hp - d_opp, 0)
                next_e = max(e_hp - d_beo, 0)
                prob += p * dp[next_b][next_e]
            dp[b_hp][e_hp] = prob

    return dp[player_hp][enemy_hp]


def run():
    print("=== FE4 Arena Win Calculator ===")

    match choose_character_input_mode():
        case CharacterInputMode.STORED:
            char_stats = get_or_add_character()
        case CharacterInputMode.MANUAL:
            char_stats = manual_character_entry()

    weapon = get_or_add_weapon()

    # Opponent key info
    chapter, arena = get_or_add_opponent()

    # Arena combat UI stats
    print("\nEnter Arena displayed combat stats:")
    displayed_char_hit = sanitize_input("  Your displayed hit (e.g. 64): ", int)
    displayed_enemy_hit = sanitize_input("  Enemy displayed hit (e.g. 53): ", int)

    # Doubling info
    double_state = sanitize_input("Who doubles? (player/enemy/none/unknown): ").strip().lower()

    # Infer opponent type from weapon metadata
    opponent_type = weapon.get("OpponentType", "normal")
    key = f"{opponent_type}_ch{chapter}_lvl{arena}"

    if key not in opponents:
        print(f"Opponent data for {key} not found. Please enter it:")
        data = get_input_ints(f"Enter arena stats for opponent {key}", ["Hit", "Def", "Atc", "HP"])
        data["DamageType"] = sanitize_input("  Damage Type (physical/magic): ")
        opponents[key] = data
        save_data(OPPONENTS_FILE, opponents)
    opponent = opponents[key]

    char_atk = (
        compute_atk(char_stats["Str"], weapon["Might"])
        if weapon["DamageType"] == "physical"
        else compute_atk(char_stats["Mag"], weapon["Might"])
    )
    char_dmg = max(char_atk - opponent["Def"], 0) if weapon["DamageType"] == "physical" else max(char_atk - char_stats["Res"], 0)
    opp_dmg = max(opponent["Atc"] - char_stats["Def"], 0) if opponent["DamageType"] == "physical" else max(opponent["Atc"] - char_stats["Res"], 0)

    win_prob = compute_win_chance(
        player_hp=char_stats["HP"],
        enemy_hp=opponent["HP"],
        player_hit=displayed_char_hit,
        player_dmg=char_dmg,
        enemy_hit=displayed_enemy_hit,
        enemy_dmg=opp_dmg,
        doubling=double_state
    )

    print(f"\n=== Combat Preview with {weapon} ===")
    print(f"Your Hit: {displayed_char_hit}, Dmg: {char_dmg}, AS: {char_stats['Speed'] - weapon['Weight']}")
    print(f"Enemy Hit: {displayed_enemy_hit}, Dmg: {opp_dmg}")
    print(f"Your HP: {char_stats['HP']}, Enemy HP: {opponent['HP']}")
    print(f"Doubling: {double_state.capitalize()}")
    print(f"Win Chance: {win_prob * 100:.2f}%")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nSee ya!")
