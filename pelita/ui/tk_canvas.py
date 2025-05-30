import logging
import platform

import zmq

try:
    import tkinter
except ImportError:
    # if we are on linux, we suggest to install the python3-tk package
    if 'Linux' in platform.platform():
        message = '\nYour Python installation is missing tkinter\n\n'
        if platform.freedesktop_os_release()['ID'] == 'debian':
            message += 'Please install the python3-tk package'
        else:
            message += 'Please install the python3-tkinter package'
        raise Exception(message)

import tkinter.font

from .. import layout
from ..game import next_round_turn
from ..team import _ensure_list_tuples
from .tk_sprites import (
    BLUE,
    GREY,
    LIGHT_GREY,
    # LIGHT_BLUE,
    # LIGHT_RED,
    RED,
    SELECTED,
    STRONG_BLUE,
    STRONG_RED,
    Arrow,
    BotSprite,
    Food,
    Wall
)
from .tk_utils import wm_delete_window_handler

_logger = logging.getLogger(__name__)

# Design variables
#
# The size of the status section on the bottom is generated automatically.
# To have default geometry with square cells, this must be checked with
#
#   STATUS_HEIGHT = TkApplication.ui_status_frame.winfo_height()
#
# A good geometry is then (w, w/2 + HEADER_HEIGHT+STATUS_HEIGHT)

# Height of the title (team scores)
HEADER_HEIGHT = 45

# Padding around the maze cells (used in grid mode)
MAZE_PADDING = 13

# Extra padding around status section
STATUS_PADDING_TOP = 0
STATUS_PADDING_BOTTOM = 2

# Padding for the grid items in the status section
GRID_PADDING_X = 5
GRID_PADDING_Y = 0

# Distance from top to headline text
HEADER_MARGIN_TOP = 3

# Distance from headline text to subheader
SUBHEADER_MARGIN_TOP = 10

STATUS_FRAME_STYLE = {
    "background": "WHITE",
}

BUTTON_STYLE = {
    "background": "WHITE",
    # "padx": '3',
    # "pady": '1',
    "height": 0,
}

BUTTON_PADDING = {
    "padx": "5",
    "pady": "1",
}

LABEL_STYLE = {
    "background": "WHITE",
}

# We must not add background colour and widths/padding to buttons on
# macOS tkinter or it will look bad! (When testing, also check dark mode)
#
# alternatively, check 'aqua' in (widget.tk.call('tk', 'windowingsystem'))
if "macOS" in platform.platform():
    STATUS_FRAME_STYLE = {}
    BUTTON_STYLE = {}
    BUTTON_PADDING = {}
    LABEL_STYLE = {}


def guess_size(display_string, bounding_width, bounding_height, rel_size=0):
    no_lines = display_string.count("\n") + 1
    size_guess = bounding_height // ((3-rel_size) * no_lines)
    font = tkinter.font.Font(size=size_guess)
    text_width = font.measure(display_string)
    if text_width > bounding_width:
        font_size = size_guess * bounding_width // text_width
    else:
        font_size = size_guess
    return font_size

class MeshGraph:
    """ A `MeshGraph` is a structure of `mesh_width` * `mesh_height` rectangles,
    covering an area of `screen_width`, `screen_height`.
    """
    def __init__(self, mesh_width, mesh_height, screen_width, screen_height, top_margin=0):
        self.mesh_width = mesh_width
        self.mesh_height = mesh_height
        self.screen_height = screen_height
        self.screen_width = screen_width
        self.top_margin = top_margin
        self.padding = MAZE_PADDING

    def update_mesh_shape(self, shape):
        mesh_width, mesh_height = shape
        self.mesh_width = mesh_width
        self.mesh_height = mesh_height

    @property
    def rect_width(self):
        """ The width of a single field.
        """
        # we have to adjust by one pixel for the border
        width = float(self.screen_width - 1 - 2 * self.padding) / self.mesh_width
        # if the UI is not initialized yet (or just really really small) this may
        # result in a negative value. Ensure that it is always positive or zero.
        if width < 0:
            width = 0.0
        return width

    @property
    def rect_height(self):
        """ The height of a single field.
        """
        # we have to adjust by one pixel for the border
        height = float(self.screen_height - 1 - 2 * self.padding - self.top_margin) / self.mesh_height
        # if the UI is not initialized yet (or just really really small) this may
        # result in a negative value. Ensure that it is always positive or zero.
        if height < 0:
            height = 0.0
        return height

    @property
    def half_scale_x(self):
        return self.rect_width / 2.0

    @property
    def half_scale_y(self):
        return self.rect_height / 2.0

    def mesh_trafo(self, mesh_x, mesh_y):
        return Trafo(self, mesh_x, mesh_y)

    def mesh_to_screen(self, mesh, coords):
        mesh_x, mesh_y = mesh
        coords_x, coords_y = coords

        real_x = self.mesh_to_screen_x(mesh_x, coords_x)
        real_y = self.mesh_to_screen_y(mesh_y, coords_y)
        return (real_x, real_y)

    def mesh_to_screen_x(self, mesh_x, model_x):
        # coords are between -1 and +1: shift on [0, 1]
        trafo_x = (model_x + 1.0) / 2.0

        real_x = self.rect_width * (mesh_x + trafo_x) + self.padding
        return real_x

    def mesh_to_screen_y(self, mesh_y, model_y):
        # coords are between -1 and +1: shift on [0, 1]
        trafo_y = (model_y + 1.0) / 2.0

        real_y = self.rect_height * (mesh_y + trafo_y) + self.padding + self.top_margin
        return real_y

    def screen_to_mesh_coord(self, screen_x, screen_y):
        # returns the mesh coordinate of the selected screen coordinate
        # or None, when it is outside of the mesh

        x = int((screen_x - self.padding) / self.rect_width)
        y = int((screen_y - self.padding - self.top_margin) / self.rect_height)

        if not 0 <= x < self.mesh_width or not 0 <= y < self.mesh_height:
            return None
        return (x, y)

    def __repr__(self):
        return "MeshGraph(%d, %d, %d, %d)" % (self.mesh_width, self.mesh_height,
                                              self.screen_width, self.screen_height)

class Trafo:
    def __init__(self, mesh_graph, mesh_x, mesh_y):
        self.mesh_graph = mesh_graph
        self.mesh_x = mesh_x
        self.mesh_y = mesh_y

    def screen_x(self, model_x):
        return self.mesh_graph.mesh_to_screen_x(self.mesh_x, model_x)

    def screen_y(self, model_y):
        return self.mesh_graph.mesh_to_screen_y(self.mesh_y, model_y)

    def screen(self, model_x, model_y):
        return self.mesh_graph.mesh_to_screen((self.mesh_x, self.mesh_y), (model_x, model_y))

class TkApplication:
    def __init__(self, window, controller_address=None,
                 geometry=None, delay=1, stop_after=None, stop_after_kill=False, fullscreen=False):
        self.window = window
        self.window.configure(background="white")

        self.context = zmq.Context()

        if controller_address:
            self.controller_socket = self.context.socket(zmq.DEALER)
            self.controller_socket.connect(controller_address)
        else:
            self.controller_socket = None

        self.window.title("Pelita")

        self.game_finish_overlay = lambda: None

        self.mesh_graph = MeshGraph(0, 0, 0, 0, top_margin=HEADER_HEIGHT)

        self.fullscreen = fullscreen
        self._fullscreen_enabled = fullscreen

        self._default_font = tkinter.font.nametofont("TkDefaultFont")
        self._default_font_size = self._default_font.cget('size')

        self._grid_enabled = False

        self.selected = None

        self.bot_sprites = {}
        self.shadow_sprites = {}
        self.init_bot_sprites([None] * 4)

        self._game_state = {}

        self.ui_game_canvas = tkinter.Canvas(window)
        self.ui_game_canvas.configure(background="white", bd=0, highlightthickness=0, relief='flat')
        self.ui_game_canvas.bind('<Configure>', lambda e: window.after_idle(self.update))
        self.ui_game_canvas.bind('<Button-1>', self.on_click)

        self.ui_status_frame = tkinter.Frame(window, **STATUS_FRAME_STYLE)
        self.ui_status_frame.configure(bd=0, relief="flat")

        self.ui_status_margin_top = tkinter.Frame(self.ui_status_frame, **STATUS_FRAME_STYLE)
        self.ui_status_margin_bottom = tkinter.Frame(self.ui_status_frame, **STATUS_FRAME_STYLE)
        self.ui_status_01 = tkinter.Frame(self.ui_status_frame, **STATUS_FRAME_STYLE)
        self.ui_status_00 = tkinter.Frame(self.ui_status_frame, **STATUS_FRAME_STYLE)
        self.ui_status_02 = tkinter.Frame(self.ui_status_frame, **STATUS_FRAME_STYLE)
        self.ui_status_10 = tkinter.Frame(self.ui_status_frame, **STATUS_FRAME_STYLE)
        self.ui_status_11 = tkinter.Frame(self.ui_status_frame, **STATUS_FRAME_STYLE)
        self.ui_status_12 = tkinter.Frame(self.ui_status_frame, **STATUS_FRAME_STYLE)

        # We need a small margin rows so that it looks better
        self.ui_status_margin_top.grid(row=1, column=0, columnspan=3, sticky="E", ipady=STATUS_PADDING_TOP)
        self.ui_status_margin_bottom.grid(row=4, column=0, columnspan=3, sticky="E", ipady=STATUS_PADDING_BOTTOM)

        self.ui_status_00.grid(row=2, column=0, sticky="W", padx=GRID_PADDING_X, pady=GRID_PADDING_Y)
        self.ui_status_01.grid(row=2, column=1, sticky="WE", pady=GRID_PADDING_Y)
        self.ui_status_02.grid(row=2, column=2, sticky="E", padx=GRID_PADDING_X, pady=GRID_PADDING_Y)

        self.ui_status_10.grid(row=3, column=0, sticky="W", padx=GRID_PADDING_X, pady=GRID_PADDING_Y)
        self.ui_status_11.grid(row=3, column=1, sticky="WE", pady=GRID_PADDING_Y)
        self.ui_status_12.grid(row=3, column=2, sticky="E", padx=GRID_PADDING_X, pady=GRID_PADDING_Y)

        self.ui_status_frame.grid_columnconfigure(0, weight=4, uniform='status')
        self.ui_status_frame.grid_columnconfigure(1, weight=3, uniform='status')
        self.ui_status_frame.grid_columnconfigure(2, weight=4, uniform='status')

        self.ui_button_game_speed_slower = tkinter.Button(self.ui_status_10,
            text="slower",
            command=self.delay_inc,
            **BUTTON_STYLE)
        self.ui_button_game_speed_slower.pack(side=tkinter.LEFT, **BUTTON_PADDING)

        self.ui_button_game_speed_faster = tkinter.Button(self.ui_status_10,
            text="faster",
            command=self.delay_dec,
            **BUTTON_STYLE)
        self.ui_button_game_speed_faster.pack(side=tkinter.LEFT, **BUTTON_PADDING)

        self._check_speed_button_state()

        self.ui_button_game_toggle_grid = tkinter.Button(self.ui_status_10,
            command=self.toggle_grid,
            **BUTTON_STYLE)
        self.ui_button_game_toggle_grid.pack(side=tkinter.LEFT, **BUTTON_PADDING)

        self._check_grid_toggle_state()

        self.ui_status_selected = tkinter.Label(self.ui_status_12,
            text="",
            font=(self._default_font, 8),
            **LABEL_STYLE)
        self.ui_status_selected.pack(side=tkinter.RIGHT)

        tkinter.Button(self.ui_status_00,
                       text="PLAY/PAUSE",
                       command=self.toggle_running,
                       **BUTTON_STYLE).pack(side=tkinter.LEFT, expand=True, **BUTTON_PADDING)

        tkinter.Button(self.ui_status_00,
                       text="STEP",
                       command=self.request_step,
                       **BUTTON_STYLE).pack(side=tkinter.LEFT, expand=True, **BUTTON_PADDING)

        tkinter.Button(self.ui_status_00,
                       text="ROUND",
                       command=self.request_round,
                       **BUTTON_STYLE).pack(side=tkinter.LEFT, expand=True, **BUTTON_PADDING)

        tkinter.Button(self.ui_status_01,
                       text="QUIT",
                       command=self.quit,
                       **BUTTON_STYLE).pack(side=tkinter.TOP, fill=tkinter.BOTH, anchor=tkinter.CENTER)

        self.ui_bot_indexes = []
        for idx in range(4):
            label = tkinter.Label(self.ui_status_02, text=layout.BOT_I2N[idx], width=1, justify='right', anchor='e', **LABEL_STYLE)

            label.pack(side=tkinter.LEFT)
            self.ui_bot_indexes.append(label)

        self.ui_status_round_info = tkinter.Label(self.ui_status_02, text="", justify='right', anchor='e', **LABEL_STYLE)
        self.ui_status_round_info.pack(side=tkinter.LEFT)

        self.ui_game_canvas.pack(side=tkinter.TOP, fill=tkinter.BOTH, expand=True)
        self.ui_status_frame.pack(side=tkinter.TOP, fill=tkinter.X)

        self._min_delay = 1
        self._delay = delay
        self._stop_after = stop_after
        self._stop_after_delay = delay
        if self._stop_after is not None:
            self._delay = self._min_delay
        self._stop_after_kill = stop_after_kill
        # This will be set once we get data
        self._last_bot_was_killed = []

        self._check_speed_button_state()

        self._observed_steps = set()

        self.running = True

        self.window.bind('f', lambda event: self.toggle_fullscreen())
        self.window.bind('q', lambda event: self.quit())
        self.window.bind('<numbersign>', lambda event: self.toggle_grid())
        self.window.bind('<greater>', lambda event: self.delay_dec())
        self.window.bind('<less>', lambda event: self.delay_inc())
        self.window.bind('<space>', lambda event: self.toggle_running())
        self.window.bind('<Return>', lambda event: self.request_step())
        self.window.bind('<Shift-Return>', lambda event: self.request_round())
        self.window.createcommand('exit', self.quit)
        self.window.protocol("WM_DELETE_WINDOW", self.quit)

        if self.controller_socket:
            self.window.after_idle(self.request_initial)

    def update(self, game_state=None, redraw=False):
        if game_state is not None:
            if self._game_state.get("shape") != game_state.get("shape"):
                redraw = True
            if self._game_state.get("walls") != game_state.get("walls"):
                redraw = True

            self._game_state = game_state
        game_state = self._game_state
        if not game_state:
            return

        self.mesh_graph.update_mesh_shape(game_state['shape'])

        # Check and adjust sizes
        if ((self.mesh_graph.screen_width, self.mesh_graph.screen_height)
            != (self.ui_game_canvas.winfo_width(), self.ui_game_canvas.winfo_height())):
            redraw = True

        self.mesh_graph.screen_width = self.ui_game_canvas.winfo_width()
        self.mesh_graph.screen_height = self.ui_game_canvas.winfo_height()

        if self.mesh_graph.screen_width < 600:
            if self._default_font.cget('size') != 8:
                self._default_font.configure(size=8)
        else:
            if self._default_font.cget('size') != self._default_font_size:
                self._default_font.configure(size=self._default_font_size)

        self.draw_universe(game_state, redraw=redraw)

        eaten_food = []
        for food_pos, food_item in self.food_items.items():
            food_item.food_age = game_state['food_age'].get(food_pos, 0)
            if food_pos not in game_state["food"]:
                self.ui_game_canvas.delete(food_item.tag)
                eaten_food.append(food_pos)
        for food_pos in eaten_food:
            del self.food_items[food_pos]

        winning_team_idx = game_state.get("whowins")
        if winning_team_idx is None:
            self.draw_end_of_game(None)
        elif winning_team_idx in (0, 1):
            team_name = game_state["team_names"][winning_team_idx]
            self.draw_game_over(team_name)
        elif winning_team_idx == 2:
            self.draw_game_draw()


    def draw_universe(self, game_state, redraw):
        self.draw_overlay(game_state.get('overlays', []))
        self.draw_grid(redraw=redraw)
        self.draw_selected(game_state)
        self.draw_line_of_sight(game_state)
        self.draw_bot_shadow(game_state)
        self.draw_background(redraw=redraw)
        self.draw_maze(game_state, redraw=redraw)
        self.draw_food(game_state)

        self.draw_title(game_state)
        self.draw_shadow_bots(game_state, redraw=redraw)
        self.draw_bots(game_state, redraw=redraw)

        self.draw_moves(game_state)

        self.draw_status_info(game_state)

    def draw_grid(self, redraw):
        """ Draws a light grid on the background.
        """
        if not redraw:
            return
        self.ui_game_canvas.delete("grid")

        if not self._grid_enabled:
            return

        # we don’t use scaling for the grid width currently
        grid_width = 0.01

        def draw_line(x0, y0, x1, y1):
            x0_ = self.mesh_graph.mesh_to_screen_x(x0, 0)
            y0_ = self.mesh_graph.mesh_to_screen_y(y0, 0)
            x1_ = self.mesh_graph.mesh_to_screen_x(x1, 0)
            y1_ = self.mesh_graph.mesh_to_screen_y(y1, 0)
            self.ui_game_canvas.create_line(x0_, y0_, x1_, y1_, width=grid_width, fill="#884488", tags="grid")

        for x in range(self.mesh_graph.mesh_width + 1):
            draw_line(x - 0.5, -0.5, x - 0.5, self.mesh_graph.mesh_height - 0.5)

        for y in range(self.mesh_graph.mesh_height + 1):
            draw_line(-0.5, y - 0.5, self.mesh_graph.mesh_width - 0.5, y - 0.5)

        label_size = 7
        label_style = {
            "font": (None, label_size),
            "fill": "#884488",
            "tags": "grid",
            "justify": tkinter.CENTER,
            "anchor": tkinter.CENTER
        }

        for x in range(self.mesh_graph.mesh_width):
            label = f"{x}"

            x_pos = self.mesh_graph.mesh_to_screen_x(x, 0)
            # the margin is not autoscaling, so we do the shift on the real grid
            y_pos = self.mesh_graph.mesh_to_screen_y(0, -1) - label_size
            self.ui_game_canvas.create_text(x_pos, y_pos, text=label, **label_style)
            y_pos = self.mesh_graph.mesh_to_screen_y(self.mesh_graph.mesh_height, -1) + label_size
            self.ui_game_canvas.create_text(x_pos, y_pos, text=label, **label_style)

        for y in range(self.mesh_graph.mesh_height):
            label = f"{y}"

            # the margin is not autoscaling, so we do the shift on the real grid
            x_pos = self.mesh_graph.mesh_to_screen_x(0, -1) - label_size
            y_pos = self.mesh_graph.mesh_to_screen_y(y, 0)
            self.ui_game_canvas.create_text(x_pos, y_pos, text=label, **label_style)
            x_pos = self.mesh_graph.mesh_to_screen_x(self.mesh_graph.mesh_width, -1) + label_size
            self.ui_game_canvas.create_text(x_pos, y_pos, text=label, **label_style)

        x_pos = self.mesh_graph.mesh_to_screen_x(0, -0.7)
        y_pos = self.mesh_graph.mesh_to_screen_y(0, -1) - label_size
        self.ui_game_canvas.create_text(x_pos, y_pos, text="x", **label_style)

        x_pos = self.mesh_graph.mesh_to_screen_x(0, -1) - label_size
        y_pos = self.mesh_graph.mesh_to_screen_y(0, -0.7)
        self.ui_game_canvas.create_text(x_pos, y_pos, text="y", **label_style)

    def draw_overlay(self, overlays):
        """ Draws a light grid on the background.
        """
        self.ui_game_canvas.delete("overlay")
        if not self._grid_enabled:
            return

        def draw_box(pos, fill_col):
            ul = self.mesh_graph.mesh_to_screen(pos, (-1, -1))
            lr = self.mesh_graph.mesh_to_screen(pos, (1, 1))

            self.ui_game_canvas.create_rectangle(*ul, *lr, width=0, fill=fill_col, tags=("overlay",))

        for overlay in overlays:
            if fill_col := overlay.get("fill"):
                for pos in overlay.get("pos", []):
                    draw_box(pos, fill_col)

        self.ui_game_canvas.tag_lower("overlay")
        self.ui_game_canvas.tag_raise("wall")

    def draw_line_of_sight(self, game_state):
        self.ui_game_canvas.delete("line_of_sight")
        if not self._grid_enabled:
            return

        bot = game_state.get('turn')
        if bot is None:
            # game has not started yet or we are in layout-only mode
            return

        def draw_box(pos):
            ul = self.mesh_graph.mesh_to_screen(pos, (-1, -1))
            lr = self.mesh_graph.mesh_to_screen(pos, (1, 1))

            self.ui_game_canvas.create_rectangle(*ul, *lr, width=2, outline='#111', tags=("line_of_sight",))

        line_col = STRONG_BLUE if bot % 2 == 0 else STRONG_RED
        # fill_col = LIGHT_BLUE if bot % 2 == 0 else LIGHT_RED

        try:
            old_pos = tuple(game_state['requested_moves'][bot]['previous_position'])
        except TypeError:
            old_pos = game_state['bots'][bot]
        draw_box(old_pos)

        sight_distance = game_state["sight_distance"]
        # starting from old_pos, iterate over all positions that are up to sight_distance
        # steps away and put a border around the fields.
        border_cells_relative = set(
            (dx, dy)
            for dx in range(- sight_distance, sight_distance + 1)
            for dy in range(- sight_distance, sight_distance + 1)
            if abs(dx) + abs(dy) == sight_distance
        )

        def in_maze(x, y):
            return 0 <= x < game_state['shape'][0] and  0 <= y < game_state['shape'][1]

        def on_edge(x, y):
            return x == 0 or x == game_state['shape'][0] - 1 or y == 0 or y == game_state['shape'][1] - 1


        def draw_line(pos, line_col, loc):
            x0_ = self.mesh_graph.mesh_to_screen_x(pos[0], loc[0])
            y0_ = self.mesh_graph.mesh_to_screen_y(pos[1], loc[1])
            x1_ = self.mesh_graph.mesh_to_screen_x(pos[0], loc[2])
            y1_ = self.mesh_graph.mesh_to_screen_y(pos[1], loc[3])
            self.ui_game_canvas.create_line(x0_, y0_, x1_, y1_, width=3, fill=line_col, tags=("line_of_sight"))

        def draw_box(pos, fill_col):
            ul = self.mesh_graph.mesh_to_screen(pos, (-1, -1))
            lr = self.mesh_graph.mesh_to_screen(pos, (1, 1))

            self.ui_game_canvas.create_rectangle(*ul, *lr, width=0, fill=fill_col, tags=("line_of_sight", "area_of_sight"))

        for dx in range(- sight_distance, sight_distance + 1):
            for dy in range(- sight_distance, sight_distance + 1):
                if abs(dx) + abs(dy) > sight_distance:
                    continue

                pos = (old_pos[0] + dx, old_pos[1] + dy)
                if not in_maze(pos[0], pos[1]):
                    continue

                # Currently not used
                # draw_box(pos, fill_col=fill_col)

                # add edge around cells at the line of sight max
                if (dx, dy) in border_cells_relative:
                    if dx >= 0:
                        draw_line(pos, loc=(1, 1, 1, -1), line_col=line_col)
                    if dx <= 0:
                        draw_line(pos, loc=(-1, 1, -1, -1), line_col=line_col)
                    if dy >= 0:
                        draw_line(pos, loc=(1, 1, -1, 1), line_col=line_col)
                    if dy <= 0:
                        draw_line(pos, loc=(1, -1, -1, -1), line_col=line_col)

                # add edge around cells at the edge of the maze
                if on_edge(pos[0], pos[1]):
                    if pos[0] == game_state['shape'][0] - 1:
                        draw_line(pos, loc=(1, 1, 1, -1), line_col=line_col)
                    if pos[0] == 0:
                        draw_line(pos, loc=(-1, 1, -1, -1), line_col=line_col)
                    if pos[1] == game_state['shape'][1] - 1:
                        draw_line(pos, loc=(1, 1, -1, 1), line_col=line_col)
                    if pos[1] == 0:
                        draw_line(pos, loc=(1, -1, -1, -1), line_col=line_col)

        self.ui_game_canvas.tag_lower("area_of_sight")
        self.ui_game_canvas.tag_raise("wall")


    def draw_bot_shadow(self, game_state):
        self.ui_game_canvas.delete("bot_shadow")
        if not self._grid_enabled:
            return

        bot = game_state.get('turn')
        if bot is None:
            # game has not started yet or we are in layout-only mode
            return

        # border_col = "#000"
        fill_col = LIGHT_GREY

        def draw_box(pos):
            ul = self.mesh_graph.mesh_to_screen(pos, (-1, -1))
            lr = self.mesh_graph.mesh_to_screen(pos, (1, 1))

            self.ui_game_canvas.create_rectangle(*ul, *lr, width=2, outline='#111', tags=("bot_shadow",))

        try:
            old_pos = tuple(game_state['requested_moves'][bot]['previous_position'])
        except TypeError:
            old_pos = game_state['bots'][bot]

        boundary = game_state['shape'][0] / 2
        if bot % 2 == 0:
            in_homezone = old_pos[0] < boundary
        else:
            in_homezone = old_pos[0] >= boundary

        if not in_homezone:
            # We are a pacman. No shadow
            return

        draw_box(old_pos)

        sight_distance = game_state["shadow_distance"]
        # starting from old_pos, iterate over all positions that are up to sight_distance
        # steps away and put a border around the fields.
        # border_cells_relative = set(
        #     (dx, dy)
        #     for dx in range(- sight_distance, sight_distance + 1)
        #     for dy in range(- sight_distance, sight_distance + 1)
        #     if abs(dx) + abs(dy) == sight_distance
        # )

        def in_maze(x, y):
            return 0 <= x < game_state['shape'][0] and  0 <= y < game_state['shape'][1]

        # def on_edge(x, y):
        #     return x == 0 or x == game_state['shape'][0] - 1 or y == 0 or y == game_state['shape'][1] - 1


        # def draw_line(pos, line_col, loc):
        #     x0_ = self.mesh_graph.mesh_to_screen_x(pos[0], loc[0])
        #     y0_ = self.mesh_graph.mesh_to_screen_y(pos[1], loc[1])
        #     x1_ = self.mesh_graph.mesh_to_screen_x(pos[0], loc[2])
        #     y1_ = self.mesh_graph.mesh_to_screen_y(pos[1], loc[3])
        #     self.ui_game_canvas.create_line(x0_, y0_, x1_, y1_, width=2, fill=line_col, tags=("bot_shadow"))


        def draw_box(pos, fill_col):
            ul = self.mesh_graph.mesh_to_screen(pos, (-1, -1))
            lr = self.mesh_graph.mesh_to_screen(pos, (1, 1))

            self.ui_game_canvas.create_rectangle(*ul, *lr, width=0, fill=fill_col, tags=("bot_shadow", "bot_shadow_area"))

        for dx in range(- sight_distance, sight_distance + 1):
            for dy in range(- sight_distance, sight_distance + 1):
                if abs(dx) + abs(dy) > sight_distance:
                    continue

                pos = (old_pos[0] + dx, old_pos[1] + dy)
                if not in_maze(pos[0], pos[1]):
                    continue

                draw_box(pos, fill_col=fill_col)

                # Border around the shadow removed for now
                #
                # # add edge around cells at the line of sight max
                # if (dx, dy) in border_cells_relative:
                #     if dx >= 0:
                #         draw_line(pos, loc=(1, 1, 1, -1), line_col=border_col)
                #     if dx <= 0:
                #         draw_line(pos, loc=(-1, 1, -1, -1), line_col=border_col)
                #     if dy >= 0:
                #         draw_line(pos, loc=(1, 1, -1, 1), line_col=border_col)
                #     if dy <= 0:
                #         draw_line(pos, loc=(1, -1, -1, -1), line_col=border_col)

                # # add edge around cells at the edge of the maze
                # if on_edge(pos[0], pos[1]):
                #     if pos[0] == game_state['shape'][0] - 1:
                #         draw_line(pos, loc=(1, 1, 1, -1), line_col=border_col)
                #     if pos[0] == 0:
                #         draw_line(pos, loc=(-1, 1, -1, -1), line_col=border_col)
                #     if pos[1] == game_state['shape'][1] - 1:
                #         draw_line(pos, loc=(1, 1, -1, 1), line_col=border_col)
                #     if pos[1] == 0:
                #         draw_line(pos, loc=(1, -1, -1, -1), line_col=border_col)

        self.ui_game_canvas.tag_lower("bot_shadow_area")
        self.ui_game_canvas.tag_lower("area_of_sight")
        self.ui_game_canvas.tag_raise("wall")


    def toggle_grid(self):
        self._grid_enabled = not self._grid_enabled
        self._check_grid_toggle_state()
        self.update(redraw=True)

    def toggle_fullscreen(self):
        self._fullscreen_enabled = not self._fullscreen_enabled
        if self._fullscreen_enabled:
            self.window.attributes('-fullscreen',True)
        else:
            self.window.attributes('-fullscreen',False)
        self.update(redraw=True)

    def _check_grid_toggle_state(self):
        if self._grid_enabled:
            self.ui_button_game_toggle_grid.configure(text="debug")
        else:
            self.ui_button_game_toggle_grid.configure(text="debug")

    def on_click(self, event):
        raw_x, raw_y = event.x, event.y
        selected = self.mesh_graph.screen_to_mesh_coord(raw_x, raw_y)
        if self.selected == selected:
            self.selected = None
        else:
            self.selected = selected
        self.update()

    def draw_background(self, redraw):
        """ Draws a line between blue and red team.
        """
        if not redraw:
            return
        self.ui_game_canvas.delete("background")

        center = self.mesh_graph.screen_width // 2
        cols = (BLUE, RED, GREY)

        scale = self.mesh_graph.half_scale_x * 0.2

        for color, x_orig in zip(cols, (center - 3, center + 3, center)):
            y_top = self.mesh_graph.mesh_to_screen_y(0, 0)
            y_bottom = self.mesh_graph.mesh_to_screen_y(self.mesh_graph.mesh_height - 1, 0)
            self.ui_game_canvas.create_line(x_orig, y_top, x_orig, y_bottom, width=scale, fill=color, tags="background")

    def draw_title(self, game_state):
        self.ui_game_canvas.delete("title")

        if "team_names" not in game_state:
            return

        center = self.ui_game_canvas.winfo_width() // 2

        left_name = game_state["team_names"][0]
        right_name = game_state["team_names"][1]

        left_score = game_state["score"][0]
        right_score = game_state["score"][1]

        left_info = game_state["team_infos"][0]
        right_info = game_state["team_infos"][1]

        left_info = f"({left_info})" if left_info else ""
        right_info = f"({right_info})" if right_info else ""

        left_team = f"{left_info} {left_name} {left_score} "
        right_team = f" {right_score} {right_name} {right_info}"

        font_size = guess_size(left_team + ' : ' + right_team,
                               self.ui_game_canvas.winfo_width(),
                               30,
                               rel_size = 1)

        def status(team_idx):
            try:
                # in case we had a fatal error, do not print the regular status
                if len(game_state['fatal_errors'][team_idx]) > 0:
                    # TODO: We only print the first fatal error (it is a list of errors) for now
                    err_type = game_state['fatal_errors'][team_idx][0]['type']
                    err_desc = game_state['fatal_errors'][team_idx][0]['description']
                    ret = f"FATAL: {err_type} {err_desc}"
                else:
                    # sum the deaths of both bots in this team
                    deaths = game_state['deaths'][team_idx] + game_state['deaths'][team_idx+2]
                    kills = game_state['kills'][team_idx] + game_state['kills'][team_idx+2]
                    ret = "Errors: %d, Kills: %d, Deaths: %d, Time: %.2f" % (game_state["num_errors"][team_idx], kills, deaths, game_state["team_time"][team_idx])
                return ret
            except TypeError:
                return ""

        left_status = status(0)
        right_status = status(1)
        status_font_size = max(font_size - 5, 3)

        top = HEADER_MARGIN_TOP
        status_top = top + font_size + SUBHEADER_MARGIN_TOP
        padding = MAZE_PADDING

        # middle colon
        self.ui_game_canvas.create_text(center, top, text=":", font=(self._default_font, font_size), fill="black", tags="title", anchor=tkinter.N)

        self.ui_game_canvas.create_text(center, top, text=left_team, font=(self._default_font, font_size), fill=BLUE, tags="title", anchor=tkinter.NE)
        self.ui_game_canvas.create_text(center+2, top, text=right_team, font=(self._default_font, font_size), fill=RED, tags="title", anchor=tkinter.NW)

        self.ui_game_canvas.create_text(0 + padding, status_top, text=" " + left_status, font=(self._default_font, status_font_size), fill="black", tags="title", anchor=tkinter.NW)
        self.ui_game_canvas.create_text(self.ui_game_canvas.winfo_width() - padding, status_top, text=right_status + " ", font=(self._default_font, status_font_size), fill="black", tags="title", anchor=tkinter.NE)

    def draw_status_info(self, game_state):
        if "round" in game_state:
            round = "–" if game_state["round"] is None else game_state["round"]
            max_rounds = "–" if game_state["max_rounds"] is None else game_state["max_rounds"]
            turn = "–" if game_state["turn"] is None else game_state["turn"]

            round_info = f"Round {round:>3}/{max_rounds}"
            self.ui_status_round_info.configure(text=round_info)

            bot_colors = [BLUE, RED, BLUE, RED]
            for idx, label in enumerate(self.ui_bot_indexes):
                label.configure(fg=bot_colors[idx] if turn == idx else "#bbb")



    def draw_selected(self, game_state):
        self.ui_game_canvas.delete("selected")
        if self.selected:
            def field_status(pos):
                has_food = pos in game_state['food']
                is_wall = pos in game_state['walls']
                bots = [idx for idx, bot in enumerate(game_state['bots']) if bot==pos]
                if pos[0] < (game_state['shape'][0] // 2):
                    zone = "blue"
                else:
                    zone = "red"

                if is_wall:
                    contents = ["wall"]
                elif has_food:
                    contents = ["food"]
                else:
                    contents = []

                if bots:
                    bot_map = {0:'blue 0', 1:'red 0', 2:'blue 1', 3:'red 1'}
                    contents += ["bots(" \
                                 + ", ".join(bot_map[bot] for bot in bots) \
                                 + ")"]

                contents = " ".join(contents)
                if not contents:
                    contents = "empty"

                return f"{pos} in {zone} zone: {contents}"

            self.ui_status_selected.configure(text=field_status(self.selected))

            ul = self.mesh_graph.mesh_to_screen(self.selected, (-1, -1))
            lr = self.mesh_graph.mesh_to_screen(self.selected, (1, 1))

            self.ui_game_canvas.create_rectangle(*ul, *lr, fill=SELECTED, tags=("selected",))
            self.ui_game_canvas.tag_lower("selected")
        else:
            self.ui_status_selected.configure(text="nothing selected")


    def draw_end_of_game(self, display_string):
        """ Draw an end of game string. """
        self.ui_game_canvas.delete("gameover")

        if display_string is None:
            return

        center = (self.mesh_graph.screen_width // 2,
                  self.mesh_graph.screen_height //2)

        font_size = guess_size(display_string,
                               self.mesh_graph.screen_width,
                               self.mesh_graph.screen_height,
                               rel_size = +1)

        for i in [-2, -1, 0, 1, 2]:
            for j in [-2, -1, 0, 1, 2]:
                self.ui_game_canvas.create_text(center[0] - i, center[1] - j,
                        text=display_string,
                        font=(self._default_font, font_size, "bold"),
                        fill="#ED1B22", tags="gameover",
                        justify=tkinter.CENTER, anchor=tkinter.CENTER)

        self.ui_game_canvas.create_text(center[0] , center[1] ,
                text=display_string,
                font=(self._default_font, font_size, "bold"),
                fill="#FFC903", tags="gameover",
                justify=tkinter.CENTER, anchor=tkinter.CENTER)


    def draw_game_over(self, win_name):
        """ Draw the game over string. """
        # shorten the winning name
        plural = '' if win_name.endswith('s') else 's'
        if len(win_name) > 25:
            win_name = win_name[:22] + '...'
        self.draw_end_of_game("GAME OVER\n%s win%s!" % (win_name, plural))

    def draw_game_draw(self):
        """ Draw the game draw string. """
        self.draw_end_of_game("GAME OVER\nDRAW!")

    def clear(self):
        self.ui_game_canvas.delete(tkinter.ALL)

    def draw_food(self, game_state):
        self.ui_game_canvas.delete("food")
        self.food_items = {}
        max_food_age = game_state.get("max_food_age")
        for position in game_state['food']:
            model_x, model_y = position
            food_age = game_state['food_age'].get(position, 0)
            food_item = Food(
                self.mesh_graph,
                position=(model_x, model_y),
                food_age=food_age,
                max_food_age=max_food_age,
            )
            food_item.draw(self.ui_game_canvas, show_lifetime=False)
            self.food_items[position] = food_item

    def draw_maze(self, game_state, redraw):
        if not redraw:
            return

        self.ui_game_canvas.delete("wall")
        # we keep all wall items stored in a list
        # some versions of Python seem to forget about drawing
        # them otherwise
        self.wall_items = []
        num = 0
        for wall in game_state['walls']:
            model_x, model_y = wall
            wall_neighbors = [(dx, dy)
                              for dx in [-1, 0, 1]
                              for dy in [-1, 0, 1]
                              if (model_x + dx, model_y + dy) in game_state['walls']]
            wall_item = Wall(self.mesh_graph, wall_neighbors=wall_neighbors, position=(model_x, model_y))
            wall_item.draw(self.ui_game_canvas)
            self.wall_items.append(wall_item)
            num += 1

    def init_bot_sprites(self, bot_positions):
        for sprite in self.bot_sprites.values():
            sprite.delete(self.ui_game_canvas)
        self.bot_sprites = {
            idx: BotSprite(self.mesh_graph, team=idx % 2, bot_id=idx, position=bot, font=self._default_font)
            for idx, bot in enumerate(bot_positions)
        }
        for sprite in self.shadow_sprites.values():
            sprite.delete(self.ui_game_canvas)
        self.shadow_sprites = {
            idx: BotSprite(self.mesh_graph, team=idx % 2, bot_id=idx, position=None, shadow=True, font=self._default_font)
            for idx, bot in enumerate(bot_positions)
        }

    def draw_moves(self, game_state):
        self.ui_game_canvas.delete("arrow")

        if game_state.get('turn') is None:
            return

        # we keep all arrow items stored in a list
        # some versions of Python seem to forget about drawing
        # them otherwise
        self.arrow_items = []

        if not self._grid_enabled:
            return

        bot = game_state['turn']
        try:
            old_pos = tuple(game_state['requested_moves'][bot]['previous_position'])
        except TypeError:
            old_pos = None
        try:
            req_pos = tuple(game_state['requested_moves'][bot]['requested_position'])
        except TypeError:
            req_pos = None

        if game_state['requested_moves'][bot]['success'] and req_pos and tuple(game_state['bots'][bot]) != tuple(req_pos):
            # Bot has committed suicide. Show two arrows.
            arrow_item1 = Arrow(self.mesh_graph,
                            position=old_pos,
                            req_pos=req_pos,
                            success=True,
                            head=False)
            arrow_item1.draw(self.ui_game_canvas)

            arrow_item2 = Arrow(self.mesh_graph,
                            position=req_pos,
                            req_pos=game_state['bots'][bot],
                            success=True)
            arrow_item2.draw(self.ui_game_canvas)

            self.arrow_items.append(arrow_item1)
            self.arrow_items.append(arrow_item2)
        else:
            arrow_item = Arrow(self.mesh_graph,
                            position=old_pos,
                            req_pos=game_state['bots'][bot],
                            success=game_state['requested_moves'][bot]['success'])
            arrow_item.draw(self.ui_game_canvas)
            self.arrow_items.append(arrow_item)


    def draw_bots(self, game_state, redraw):
        if game_state:
            for bot_id, was_killed in enumerate(game_state.get("bot_was_killed", [])):
                if was_killed:
                    self.bot_sprites[bot_id].position = None

        for bot_id, bot_sprite in self.bot_sprites.items():
            if game_state and "say" in game_state:
                say = game_state["say"][bot_id]
            else:
                say = ""
            bot_sprite.move_to(game_state["bots"][bot_sprite.bot_id],
                               self.ui_game_canvas,
                               game_state,
                               force=redraw,
                               say=say,
                               show_id=self._grid_enabled)

    def draw_shadow_bots(self, game_state, redraw):
        # Draw the shadowbots when debug mode (grid) is enabled
        # Otherwise make sure that they are deleted

        if game_state.get('turn') is None:
            # We cannot show shadow bots before the first turn has been played,
            # as we would only see the bots from the set_initial phase, and
            # only the blue bots (those that were shown to the second, red, player).
            # Given that this information is not available to the client API,
            # we must hide the shadow bots here.
            # TODO: This should be fixed inside game.py
            return

        for bot_id, bot_sprite in self.shadow_sprites.items():
            if self._grid_enabled:
                shadow_bots = game_state.get('noisy_positions')
            else:
                shadow_bots = None

            if shadow_bots is None or shadow_bots[bot_id] is None:
                bot_sprite.delete(self.ui_game_canvas)
            else:
                bot_sprite.move_to(shadow_bots[bot_id],
                                    self.ui_game_canvas,
                                    game_state,
                                    force=redraw,
                                    show_id=self._grid_enabled)

    def toggle_running(self):
        self.running = not self.running
        if self.running:
            self.request_step()

    def request_initial(self):
        if self.controller_socket:
            _logger.debug('---> set_initial')
            self.controller_socket.send_json({"__action__": "set_initial"})

    def request_step(self):
        if not self.controller_socket:
            return

        if self._game_state['gameover']:
            return

        if self._stop_after is not None:
            next_step = next_round_turn(self._game_state)
            if (next_step['round'] < self._stop_after):
                _logger.debug('---> play_step')
                self.controller_socket.send_json({"__action__": "play_step"})
            else:
                self._stop_after = None
                self.running = False
                self._delay = self._stop_after_delay
        else:
            _logger.debug('---> play_step')
            self.controller_socket.send_json({"__action__": "play_step"})

    def request_round(self):
        if not self.controller_socket:
            return

        if self._game_state['gameover']:
            return

        if self._game_state['round'] is not None:
            next_step = next_round_turn(self._game_state)
            self._stop_after = next_step['round'] + 1
        else:
            self._stop_after = 1
            self._delay = self._min_delay
        self.request_step()

    def observe(self, game_state, standalone_mode=False):
        # If in standalone mode, we will simply display everything that we receive

        if standalone_mode:
            self.running = False
        else:
            step = (game_state['round'], game_state['turn'])
            if step in self._observed_steps:
                skip_request = True
            else:
                skip_request = False
                self._observed_steps.add(step)

        # ensure walls, foods and bots positions are list of tuples
        game_state['walls'] = _ensure_list_tuples(game_state['walls'])
        game_state['food'] = _ensure_list_tuples(game_state['food'])
        game_state['bots'] = _ensure_list_tuples(game_state['bots'])
        game_state['shape'] = tuple(game_state['shape'])
        game_state['food_age'] = {tuple(pos): food_age for pos, food_age in game_state.get('food_age', [])}

        # check if a bot has been killed in the last round
        # gs.bot_was_killed does not reset the True state for a killed bot
        # until a whole round is over, so we have to cache previous values
        bot_was_killed = False
        for last, now in zip(self._last_bot_was_killed, game_state.get('bot_was_killed', [])):
            if now and not last:
                bot_was_killed = True
        self._last_bot_was_killed = game_state.get('bot_was_killed', [])

        if self._stop_after_kill and bot_was_killed:
            self.running = False

        self.update(game_state)
        if self._stop_after is not None:
            if self._stop_after == 0:
                self._stop_after = None
                self.running = False
                self._delay = self._stop_after_delay
            else:
                if skip_request:
                    _logger.debug("Skipping next request.")
                else:
                    self.window.after(self._delay, self.request_step)
        elif self.running:
            if skip_request:
                _logger.debug("Skipping next request.")
            else:
                self.window.after(self._delay, self.request_step)


    def on_quit(self):
        """ override for things which must be done when we exit.
        """
        self.running = False
        if self.controller_socket:
            _logger.debug('---> exit')
            self.controller_socket.send_json({"__action__": "exit"})
        else:
            # force closing the window (though this might not work)
            wm_delete_window_handler()

    def quit(self):
        self.on_quit()
        self.window.quit()

    def delay_inc(self):
        self._delay += 5
        self._check_speed_button_state()

    def delay_dec(self):
        # Tk may break if self._delay is lower than zero.
        # (For some systems a value < 1 is already too fast.)
        self._delay = max(self._delay - 5, self._min_delay)
        self._check_speed_button_state()

    def _check_speed_button_state(self):
        try:
            # self.ui_button_game_speed_faster
            # may not be available yet (or may be None).
            # If this is the case, we’ll do nothing at all.
            if self._delay <= self._min_delay:
                self.ui_button_game_speed_faster.configure(state=tkinter.DISABLED)
            else:
                self.ui_button_game_speed_faster.configure(state=tkinter.NORMAL)
        except AttributeError:
            pass
