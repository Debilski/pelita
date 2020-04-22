try:
    import importlib.resources as importlib_resources
except ImportError:
    # Python 3.6
    import importlib_resources
import io
from pathlib import Path
import random

def get_random_layout(size='normal'):
    """ Return a random layout string from the available ones.

    Parameters
    ----------
    size : str
        only return layouts of size 'small', 'normal', 'big', 'all'.
        Default is 'normal'.

        'small'  -> width=16, height=8,  food=10
        'normal' -> width=32, height=16, food=30
        'big'    -> width=64, height=32, food=60
        'all'    -> all of the above

    Returns
    -------
    layout : tuple(str, str)
        the name of the layout, a random layout string

    """
    layouts_names = get_available_layouts(size=size)
    layout_choice = random.choice(layouts_names)
    return layout_choice, get_layout_by_name(layout_choice)

def get_available_layouts(size='normal'):
    """Return the names of the built-in layouts.

    Parameters
    ----------
    size : str
        only return layouts of size 'small', 'normal', 'big', 'all'.
        Default is 'normal'.

        'small'  -> width=16, height=8,  food=10
        'normal' -> width=32, height=16, food=30
        'big'    -> width=64, height=32, food=60
        'all'    -> all of the above


    Returns
    -------
    layout_names : list of str
        the available layouts

    """
    # loop in layouts directory and look for layout files
    valid = ('small', 'normal', 'big', 'all')
    if size not in valid:
        raise ValueError(f"Invalid layout size ('{size}' given). Valid: {valid}")
    if size == 'all':
        size = ''
    return [item[:-(len('.layout'))] for item in importlib_resources.contents('pelita._layouts')
                 if item.endswith('.layout') and size in item]

def get_layout_by_name(layout_name):
    """Get a built-in layout by name

    Parameters
    ----------
    layout_name : str
        a valid layout name

    Returns
    -------
    layout_str : str
        the layout as a string

    Raises
    ------
    KeyError
        if the layout_name is not known

    See Also
    --------
    get_available_layouts
    """
    try:
        return importlib_resources.read_text('pelita._layouts', layout_name + '.layout')
    except FileNotFoundError:
        # This happens if layout_name is not found in the layouts directory
        # reraise as ValueError with appropriate error message.
        raise ValueError(f"Layout: '{layout_name}' is not known.") from None

def parse_layout(layout_str, food=None, bots=None):
    """Parse a layout string, with additional food, bots and enemy positions.

    Return a dict (if allow_enemy_chars is False)
        {'walls': list_of_wall_coordinates,
         'food' : list_of_food_coordinates,
         'bot'  : list_of_4_bot_coordinate}
         or (if allow_enemy_chars is True)
        {'walls': list_of_wall_coordinates,
         'food' : list_of_food_coordinates,
         'bot'  : list_of_2_bot_coordinate,
         'enemy': list_of_2_enemy_coordinates,
         'is_noisy': list_of_two_bool}


    A layout string is composed of wall characters '#', food characters '.', and
    bot characters '0', '1', '2', and '3'.

    Valid layouts must be enclosed by walls and be of rectangular shape. Example:

     ########
     #0  .  #
     #2    1#
     #  .  3#
     ########


    If items are overlapping, several layout strings can be concatenated:
     ########
     #0  .  #
     #     1#
     #  .  3#
     ########
     ########
     #2  .  #
     #     1#
     #  .  3#
     ########

    In this case, bot '0' and bot '2' are on top of each other at position (1,1)

    If `allow_enemy_chars` is True, we additionally allow for the definition of
    at most 2 enemy characters with the letters "E" and "?". The returned dict will
    then additionally contain an entry "enemy" which contains these coordinates and
    an entry "is_noisy" that specifies which of the given enemies is noisy.
    If only one enemy character is given, both will be assumed sitting on the
    same spot. """

    # bot to index conversion
    bot_n2i = {'a': 0, 'b': 2, 'x': 1, 'y': 3}
    bot_i2n = {0 : 'a', 2 : 'b', 1 : 'x', 3 : 'y'}

    if bots is None:
        bots = {}
    if food is None:
        food = []

    # Split Douple layouts into a list of two
    # set empty default values
    lwalls = []
    lfood = []
    lbots = [None] * 4

    width = None
    # list of layout rows
    rows = []
    start = False
    for i, line in enumerate(layout_str.splitlines()):
        row = line.strip()
        if not row:
            # always ignore empty lines
            continue
        # a layout is always started by a full row of walls
        if not start:
            if row.count('#') != len(row):
                raise ValueError(f"Layout must be enclosed by walls (line: {i})!")
            else:
                # start the layout parsing
                start = True
                # set width of layout
                width = len(row)
                # check that width is even
                if width % 2:
                    raise ValueError(f"Layout width must be even (found {width})!")
                rows.append(row)
                continue
        # Here we are within the layout
        # every row must have the same length
        if len(row) != width:
            raise ValueError(f"Layout rows have differing widths (line: {i})!")
        # rows are always enclosed by walls
        if row[0] != '#' or row[-1] != '#':
            raise ValueError(f"Layout must be enclosed by walls (line:{i})!")
        # append current row to the list of rows
        rows.append(row)
        # detect closing row and ignore whatever follows
        if row.count('#') == len(row):
            start = False
            break

    if start:
        # layout has not been closed!
        raise ValueError(f"Layout must be enclosed by walls (line:{i})!")

    # height of the layout (y-axis)
    height = len(rows)

    # iterate through the grid of characters
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            coord = (x, y)
            # assign the char to the corresponding list
            if char == '#':
                # wall
                lwalls.append(coord)
            elif char == '.':
                # food
                lfood.append(coord)
            elif char == ' ':
                # empty
                continue
            elif char in ['a', 'b', 'x', 'y']:
                # legal bots
                if char == 'a':
                    bot_idx = 0
                elif char == 'b':
                    bot_idx = 2
                elif char == 'x':
                    bot_idx = 1
                elif char == 'y':
                    bot_idx = 3
                if lbots[bot_idx]:
                    # bot_idx has already been set before
                    raise ValueError(f"Cannot set bot {bot_i2n[bot_idx]} to {coord} (already at {lbots[bot_idx]}).")
                lbots[bot_idx] = coord
            else:
                raise ValueError(f"Unknown character {char} in maze at {coord}!")
    for i, bot in enumerate(lbots):
        if bot is None and bot_i2n[i] not in bots:
            raise ValueError(f"Missing bot(s): {bot_i2n[i]}")
    lwalls.sort()
    lfood.sort()

    # if additional food was supplied, we add it
    for c in food:
        if not ((0 <= c[0] < width) and (0 <= c[1] < height)):
            raise ValueError(f"food item at {c} is outside of maze!")
        elif c in lwalls:
            raise ValueError(f"food item at {c} is on a wall!")
        else:
            lfood = sorted(list(set(food + lfood)))

    if set(bots.keys()) <= {"a", "b", "c", "d"}
        raise ValueError(f"Invalid Bot names in {bots}.")

    # check if additional bots are on legal positions
    for bn, bpos in bots.items():
        if not ((0 <= bpos[0] < width) and (0 <= bpos[1] < height)):
            raise ValueError(f"bot {bn} at {bpos} is outside of maze!")
        elif bpos in lwalls:
            raise ValueError(f"bot {bn} at {bpos} is on a wall!")
        else:
            # override bots
            lbots[bot_n2i[bn]] = bpos

    # build parsed layout, ensuring walls and food are sorted
    parsed_layout = {
        'walls': sorted(lwalls),
        'food': sorted(lfood),
        'bots': lbots
    }

    return parsed_layout


def layout_as_str(*, walls, food=None, bots=None, enemy=None, is_noisy=None):
    """Given walls, food and bots return a string layout representation

    Returns a combined layout string.

    The first layout string contains walls and food, the subsequent layout
    strings contain walls and bots. If bots are overlapping, as many layout
    strings are appended as there are overlapping bots.

    Example:

    ####
    #  #
    ####
    """
    walls = sorted(walls)
    width = max(walls)[0] + 1
    height = max(walls)[1] + 1

    # enemy is optional
    if enemy is None:
        enemy = []

    # if noisy is given, it must be of the same length as enemy
    if is_noisy is None:
        noisy_enemies = set()
    elif len(is_noisy) != len(enemy):
        raise ValueError("Parameter `noisy` must have same length as `enemy`.")
    else:
        # if an enemy is flagged as noisy, we put it into the set of noisy_enemies
        noisy_enemies = {e for e, e_is_noisy in zip(enemy, is_noisy) if e_is_noisy}

    # flag to check if we have overlapping objects

    # when need_combined is True, we force the printing of a combined layout
    # string:
    # - the first layout will have walls and food
    # - subsequent layouts will have walls and bots (and enemies, if given)
    # You'll get as many layouts as you have overlapping bots
    need_combined = False

    # combine bots an enemy lists
    bots_and_enemy = bots + enemy if enemy else bots

    # first, check if we have overlapping bots
    if len(set(bots_and_enemy)) != len(bots_and_enemy):
        need_combined = True
    else:
        need_combined = any(coord in food for coord in bots_and_enemy)
    # then, check that bots are not overlapping with food
    bot_names = ['a', 'x', 'b', 'y']
    out = io.StringIO()
    for y in range(height):
        for x in range(width):
            if (x, y) in walls:
                # always print walls
                out.write('#')
            elif (x, y) in food:
                # always print food
                out.write('.')
            else:
                if not need_combined:
                    # check if we have a bot here only when we know that
                    # we won't need a combined layout later
                    if (x, y) in bots:
                        out.write(str(bot_names[bots.index((x, y))]))
                    elif (x, y) in enemy:
                        if (x, y) in noisy_enemies:
                            out.write("?")
                        else:
                            out.write("E")
                    else:
                        out.write(' ')
                else:
                    out.write(' ')
        # close the row
        out.write('\n')

    # return here if we don't need a combined layout string
    if not need_combined:
        return out.getvalue()

    # create a mapping coordinate : list of bots at this coordinate
    coord_bots = {}
    for idx, pos in enumerate(bots):
        if pos is None:
            # if a bot coordinate is None
            # don't put the bot in the layout
            continue
        # append bot_index to the list of bots at this coordinate
        # if still no bot was seen here we have to start with an empty list
        coord_bots[pos] = coord_bots.get(pos, []) + [idx]

    # add enemies to mapping
    for pos in enemy:
        if pos is None:
            # if an enemy coordinate is None
            # don't put the enemy in the layout
            continue
        enemy_char = '?' if pos in noisy_enemies else 'E'
        coord_bots[pos] = coord_bots.get(pos, []) + [enemy_char]

    # loop through the bot coordinates
    while coord_bots:
        for y in range(height):
            for x in range(width):
                # let's repeat the walls
                if (x, y) in walls:
                    out.write('#')
                elif (x, y) in coord_bots:
                    # get the first bot at this position and remove it
                    # from the list
                    bot_idx = coord_bots[(x, y)].pop(0)
                    out.write(bot_names[bot_idx])
                    # if we are left without bots at this position
                    # remove the coordinate from the dict
                    if not coord_bots[(x, y)]:
                        del coord_bots[(x, y)]
                else:
                    # empty space
                    out.write(' ')
            # close the row
            out.write('\n')

    return out.getvalue()


def layout_for_team(layout, is_blue=True, is_noisy=(False, False)):
    """ Converts a layout dict with 4 bots to a layout
    from the view of the specified team.
    """
    if "enemy" in layout:
        raise ValueError("Layout is already in team-style.")

    if is_blue:
        bots = layout['bots'][0::2]
        enemy = layout['bots'][1::2]
    else:
        bots = layout['bots'][1::2]
        enemy = layout['bots'][0::2]

    return {
        'walls': layout['walls'][:],
        'food': layout['food'][:],
        'bots': bots,
        'enemy': enemy,
        'is_noisy' : is_noisy,
    }

def layout_agnostic(layout, is_blue=True):
    """ Converts a layout dict with 2 bots and enemies (team-style)
    to a layout with 4 bots (server-style).
    """
    if "enemy" not in layout:
        raise ValueError("Layout is already in server-style.")

    if is_blue:
        bots = [layout['bots'][0], layout['enemy'][0],
                layout['bots'][1], layout['enemy'][1]]
    else:
        bots = [layout['enemy'][0], layout['bots'][0],
                layout['enemy'][1], layout['bots'][1]]

    return {
        'walls': layout['walls'][:],
        'food': layout['food'][:],
        'bots': bots,
    }


def wall_dimensions(walls):
    """ Given a list of walls, returns a tuple of (width, height)."""
    width = max(walls)[0] + 1
    height = max(walls)[1] + 1
    return (width, height)


def initial_positions(walls):
    """Calculate initial positions.

    Given the list of walls, returns the free positions that are closest to the
    bottom left and top right corner. The algorithm starts searching from
    (1, height-2) and (width-2, 1) respectively and uses the Manhattan distance
    for judging what is closest. On equal distances, a smaller distance in the
    x value is preferred.
    """
    width = max(walls)[0] + 1
    height = max(walls)[1] + 1

    left_start = (1, height - 2)
    left = []
    right_start = (width - 2, 1)
    right = []

    dist = 0
    while len(left) < 2:
        # iterate through all possible x distances (inclusive)
        for x_dist in range(dist + 1):
            y_dist = dist - x_dist
            pos = (left_start[0] + x_dist, left_start[1] - y_dist)
            # if both coordinates are out of bounds, we stop
            if not (0 <= pos[0] < width) and not (0 <= pos[1] < height):
                raise ValueError("Not enough free initial positions.")
            # if one coordinate is out of bounds, we just continue
            if not (0 <= pos[0] < width) or not (0 <= pos[1] < height):
                continue
            # check if the new value is free
            if pos not in walls:
                left.append(pos)

            if len(left) == 2:
                break

        dist += 1

    dist = 0
    while len(right) < 2:
        # iterate through all possible x distances (inclusive)
        for x_dist in range(dist + 1):
            y_dist = dist - x_dist
            pos = (right_start[0] - x_dist, right_start[1] + y_dist)
            # if both coordinates are out of bounds, we stop
            if not (0 <= pos[0] < width) and not (0 <= pos[1] < height):
                raise ValueError("Not enough free initial positions.")
            # if one coordinate is out of bounds, we just continue
            if not (0 <= pos[0] < width) or not (0 <= pos[1] < height):
                continue
            # check if the new value is free
            if pos not in walls:
                right.append(pos)

            if len(right) == 2:
                break

        dist += 1

    # lower indices start further away
    left.reverse()
    right.reverse()
    return [left[0], right[0], left[1], right[1]]


def get_legal_positions(walls, bot_position):
    """ Returns all legal positions that a bot at `bot_position`
    can go to.

     Parameters
    ----------
    walls : list
        position of the walls of current layout.
    bot_position: tuple
        position of current bot.

    Returns
    -------
    list
        legal positions

    Raises
    ------
    ValueError
        if bot_position invalid or on wall
    """
    width, height = wall_dimensions(walls)
    if not (0, 0) <= bot_position < (width, height):
        raise ValueError(f"Position {bot_position} not inside maze ({width}x{height}).")
    if bot_position in walls:
        raise ValueError(f"Position {bot_position} is on a wall.")
    north = (0, -1)
    south = (0, 1)
    east = (1, 0)
    west = (-1, 0)
    stop = (0, 0)
    directions = [north, east, west, south, stop]
    potential_moves = [(i[0] + bot_position[0], i[1] + bot_position[1]) for i in directions]
    possible_moves = [i for i in potential_moves if i not in walls]
    return possible_moves
