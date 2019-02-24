import base64
import io
import random
import zlib

try:
    from . import __layouts
except SyntaxError as err:
    print("Invalid syntax in __layouts module. Pelita will not be able to use built-in layouts.")
    print(err)

class Layout:
    pass

class LayoutEncodingException(Exception):
    """ Signifies a problem with the encoding of a layout. """
    pass

def load_layout(layout_name=None, layout_file=None):
    """ Returns the layout_name and layout_string for a given parameter.

    The Parameters 'layout_name' and 'layout_file' are mutually exclusive.

    Parameters
    ----------
    layout_name : string, optional
        The name of an available layout
    layout_file : filename, optional
        A file which holds a layout

    Returns
    -------
    layout : tuple(str, str)
        the name of the layout, a random layout string
    """
    if layout_name and not layout_file:
        layout_name = layout_name
        layout_string = get_layout_by_name(layout_name)
    elif layout_file and not layout_name:
        with open(layout_file) as file:
            layout_name = file.name
            layout_string = file.read()
    else:
        raise  ValueError("Can only supply one of: 'layout_name' or 'layout_file'")

    return layout_name, layout_string

def get_random_layout(filter=''):
    """ Return a random layout string from the available ones.

    Parameters
    ----------
    filter : str
        only return layouts which contain "filter" in their name.
        Default is no filter.

    Returns
    -------
    layout : tuple(str, str)
        the name of the layout, a random layout string

    Examples
    --------
    To only get layouts without dead ends you may use:

        >>> get_random_layout(filter='without_dead_ends')

    """
    layouts_names = [item for item in get_available_layouts() if filter in item]
    layout_choice = random.choice(layouts_names)
    return layout_choice, get_layout_by_name(layout_choice)

def get_available_layouts(filter=''):
    """ The names of the available layouts.

    Parameters
    ----------
    filter : str
        only return layouts which contain 'filter' in their name.
        Default is no filter.

    Returns
    -------
    layout_names : list of str
        the available layouts

    Examples
    --------
    To only get layouts without dead ends you may use:

        >>> get_available_layouts(filter='without_dead_ends')

    """
    # loop in layouts dictionary and look for layout strings
    return [item for item in dir(__layouts) if item.startswith('layout_') and
            filter in item]

def get_layout_by_name(layout_name):
    """ Get a layout.

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
    # decode and return this layout
    try:
        return zlib.decompress(base64.decodebytes(__layouts.__dict__[layout_name].encode())).decode()
    except KeyError as ke:
        # This happens if layout_name is not a valid key in the __dict__.
        # I.e. if the layout_name is not available.
        # The error message would be to terse "KeyError: 'non_existing_layout'",
        # thus reraise as ValueError with appropriate error message.
        raise ValueError("Layout: '%s' is not known." % ke.args)

def parse_layout(layout_str):
    layout_list = []
    current_layout = []
    for row in layout_str.splitlines():
        stripped = row.strip()
        if stripped:
            # this line is not empty, append it to the current layout
            current_layout.append(row)
        else:
            # this line is empty
            # if we have a current_layout close it and start a new one
            if current_layout:
                layout_list.append('\n'.join(current_layout))
                current_layout = []

    if current_layout:
        # the last layout has not been closed, close it here
        layout_list.append('\n'.join(current_layout))

    # initialize walls, food and bots from the first layout
    out = parse_single_layout(layout_list.pop(0))
    for layout in layout_list:
        items = parse_layout(layout)
        # walls should always be the same
        if items['walls'] != out['walls']:
            raise ValueError('Walls are not equal in all layouts!')
        # add the food, removing duplicates
        out['food'] = list(set(out['food'] + items['food']))
        # add the bots
        for bot_idx, bot_pos in enumerate(items['bots']):
            if bot_pos:
                # this bot position is not None, overwrite whatever we had before
                out['bots'][bot_idx] = bot_pos

    return out

def parse_single_layout(layout_str):
    """Parse a single layout from a string"""
    # width of the layout (x-axis)
    width = None
    # list of layout rows
    rows = []
    for line, row in enumerate(layout_str.splitlines()):
        stripped = row.strip()
        if not stripped:
            # ignore empty lines
            continue
        if width is not None and len(stripped) != width:
            raise ValueError(f"Layout rows have differing widths at line {line}!")
        width = len(stripped)
        rows.append(stripped)
    # sanity check, width must be even
    if width % 2:
        raise ValueError(f"Layout must have even number of columns (found {width})!")

    # height of the layout (y-axis)
    height = len(rows)
    walls = []
    food = []
    # bot positions (we assume 4 bots)
    bots = [None]*4

    # iterate through the grid of characters
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            # check that we have walls on the borders
            if x == 0 or y == 0 or x == (width-1) or y == (height-1):
                if char != '#':
                    raise ValueError("Layout not surrounded with #!")
            coord = (x, y)
            # assign the char to the corresponding list
            if char == '#':
                # wall
                walls.append(coord)
            elif char == '.':
                # food
                food.append(coord)
            elif char == ' ':
                # empty
                continue
            else:
                # bot
                try:
                    # we expect an 0<=index<=3
                    bot_idx = int(char)
                    if bot_idx >= len(bots):
                        # reuse the except below
                        raise ValueError
                except ValueError:
                    raise ValueError(f"Unknown character {char} in maze!")
                bots[bot_idx] = coord
    walls.sort()
    food.sort()
    return {'walls':walls, 'food':food, 'bots':bots}

def layout_as_str(*, walls, food=None, bots=None):
    """Given walls, food and bots return a combined string layout representation

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

    with io.StringIO() as out:
        # first, print walls and food
        for y in range(height):
            for x in range(width):
                if (x, y) in walls:
                    out.write('#')
                elif (x, y) in food:
                    out.write('.')
                else:
                    out.write(' ')
            # close the row
            out.write('\n')
        # start a new layout string for the bots
        out.write('\n')

        # create a mapping coordinate : list of bots at this coordinate
        coord_bots = {}
        for idx, pos in enumerate(bots):
            if pos is None:
                # if a bot coordinate is None
                # don't put the bot in the layout
                continue
            # append bot_index to the list of bots at this coordinate
            # if still no bot was seen here we have to start with an empty list
            coord_bots[pos] = coord_bots.get(pos, []) + [str(idx)]

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
                        out.write(bot_idx)
                        # if we are left without bots at this position
                        # remove the coordinate from the dict
                        if not coord_bots[(x, y)]:
                            del coord_bots[(x, y)]
                    else:
                        # empty space
                        out.write(' ')
                # close the row
                out.write('\n')
            # close this layout string
            out.write('\n')

        # drop the last empty line: we always have two at the end
        return out.getvalue()[:-1]


