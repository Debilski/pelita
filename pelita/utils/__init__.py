import random

from ..player.team import create_layout, bot_from_layout
from ..graph import Graph

def setup_test_game(*, layout, game=None, is_blue=True, round=None, score=None, seed=None,
                    food=None, bots=None, enemy=None):
    """Returns the first bot object given a layout.

    The returned Bot instance can be passed to a move function to test its return value.
    The layout is a string that can be passed to create_layout."""
    if game is not None:
        raise RuntimeError("Re-using an old game is not implemented yet.")

    layout = create_layout(layout, food=food, bots=bots, enemy=enemy)

    rng = random.Random(seed)
    if score is None:
        score = [0, 0]
    bot = bot_from_layout(layout, is_blue, score, round, team_name=['blue', 'red'], timeout_count=[0, 0])
    bot.random = rng

    return bot
