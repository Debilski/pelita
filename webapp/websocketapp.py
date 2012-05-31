import gevent
from gevent_zeromq import zmq
from geventwebsocket.handler import WebSocketHandler

from pelita.messaging.json_convert import json_converter
from pelita.datamodel import Wall, Food
import json


class WebSocketApp(object):
    def __init__(self, context):
        self.context = context

    def __call__(self, environ, start_response):
        print "CALL", environ
        ws = environ['wsgi.websocket']
        sock = self.context.socket(zmq.SUB)
        sock.setsockopt(zmq.SUBSCRIBE, "")
        sock.connect('tcp://localhost:50011')
        print "Connect"

        walls = None

        while True:
            msg = sock.recv()
            msg_objs = json_converter.loads(msg)

            universe = msg_objs.get("universe")
            game_state = msg_objs.get("game_state")
            if universe:

                if not walls:
                    walls = []
                    for x in range(universe.maze.width):
                        col = []
                        for y in range(universe.maze.height):
                            col += [Wall in universe.maze[x, y]]
                        walls.append(col)

                food = []
                for x in range(universe.maze.width):
                    col = []
                    for y in range(universe.maze.height):
                        col += [Food in universe.maze[x, y]]
                    food.append(col)

                width = universe.maze.width
                height = universe.maze.height

                bots = []
                for bot in universe.bots:
                    bot_data = {'x': bot.current_pos[0],
                                'y': bot.current_pos[1]
                               }
                    bots.append(bot_data)

                teams = [{"name": t.name, "score": t.score} for t in universe.teams]

                data = {'walls': walls,
                        'width': width,
                        'height': height,
                        'bots': bots,
                        'food': food,
                        'teams': teams,
                        'state': game_state
                        }
                data_json = json.dumps(data)
                #print data_json
                ws.send(data_json)


def main():
    """Set up zmq context and greenlets for all the servers, then launch the web 
    browser and run the data producer"""
    context = zmq.Context()
    ws_server = gevent.pywsgi.WSGIServer(('', 51011), WebSocketApp(context), handler_class=WebSocketHandler)
    ws_server.serve_forever()

main()
