===============
Player Concepts
===============

The following concepts are only meant as examples. They may have bugs or may not work at all.

State based Player
==================

This code::

    class StateBasedPlayer(AbstractPlayer):
        def __init__(self):
            self.possible_states = {
              "attacking": AttackingState(),
              "defending": DefendingState(),
              "eating": EatingState()
            }
            self.the_state = "attacking"

        def get_move(self):
            return self.possible_states[self.the_state].get_move()

    class AttackingState(object):
        def get_move(self):
            pass

    class DefendingState(object):
        def get_move(self):
            pass

    class EatingState(object):
        def get_move(self):
            pass

.. note::
    Please do not accidentally alter `self.current_state`, which is already defined in `AbstractPlayer`.


Reflexive Player
================

We now want to document another way of writing a Player. Instead of estimating the best position from the current state, we may consider a *what if* approach: For each possible direction, we evaluate some kind of fitness function which tells us how *good* this new state is. Our choice will then of course be the direction with the highest score::

    class ReflexivePlayer(AbstractPlayer):
        def get_move(self):
            move = max(self.legal_moves, key=self._evaluate)
            return move

In order to calculate the score, we need to trick `AbstractPlayer` into believing this is a real situation and setup the `_evaluate` method in the following way::

        def _evaluate(self, move):
            uni = self.current_uni.copy()
            uni.move_bot(self._index, move)

            self.universe_states.append(uni)
            value = self.evaluate()
            self.universe_states.pop()

            return value

We then can subclass `ReflexivePlayer`, adding our very own `evaluate` method which only knows the *what if* universe::

    class ReflexiveTest(ReflexivePlayer):
        def evaluate(self):
            # return the difference in score
            return self.team.score - self.enemy_team.score

This Player does not do much, obviously. However, when it gets the opportunity, it will try to eat any food which is next to it, as well as attacking opponent Players.

Now, when you’ve tried to run this Player, you might have noticed that it only moves in a strange kind of way. For example, it might have moved only back and forth. This is because when there is no clear maximum, the `max` function will most likely return the first legal move which is available. We can make the movements more ‘interesting’ by adding a random base value to it::

            return self.team.score - self.enemy_team.score + random(0.5)

Of course, it is vital that this random value is small enough, so that it does not accidentally return the *worst* move.

Reflexive Player with weights
-----------------------------

As we are thinking about what other properties to add (distance to food, distance to enemy?), we might find that our `evaluate` method gets harder and harder to tune::


    class WeightedReflexivePlayer(ReflexivePlayer):
        def evaluate(self):
            scores = self.scores()
            weights = self.weights()
            return sum(weights[k] * scores[k] for k in weights)

Subclasses now need to implement two methods::

    class WeightedTest(WeightedReflexivePlayer):
        def weigths(self):
            return {
                "distance_to_enemy": 25,
                "score_diff": 10,
                "day_of_week": 2
            }

        def scores(self):
            return {
                "distance_to_enemy": ...

        def evaluate(self):
            return 25 * distance_to_enemy + 10 * score_diff - 2 * day_of_week

