================
Pelita internals
================

Network format
==============

Messages are JSON objects that are transmitted via zmq.

A request message has the format::

    {
        "__uuid__": UUID,
        "__action__": str,
        "__data__": object
    }

A reply message has the format::

    {
        "__uuid__": UUID,
        "__return__": data
    }

An informal guideline is that `__action__` can be thought of being a function identifier and `__data__` being the respective object of keyword arguments. The `__return__` value is understood as the return value of a function and its type will depend on a given action.

.. note::
    Since JSON does not understand tuples, the receiving functions will be expected to apply further transformations.


Depending on the channel, there MAY be rules imposed on the order in which these messages can be sent. In particular, when a channel requires that a reply be sent, then the uuid
 in this reply message must conform to the uuid in the request.


Connection Types
================


Game Master <==> Pelita Clients
-------------------------------

    PAIR (bind) :: PAIR (connect)


Game Master ==> Pelita Viewers
-------------------------------

    PUB (bind) :: SUB (connect)


Game Master <-- Pelita Controller
---------------------------------

    ROUTER (bind) :: DEALER (bind)


Game Master <==> Pelita remote <==> Pelita client
-------------------------------------------------

    DEALER (connect) :: ROUTER (bind)
                          ^
                          |
                          v
                         PAIR (bind) :: PAIR (connect)

Reply Channel <-- Game Master
-----------------------------

    PAIR (bind) :: PAIR (connect)


Because there is no way of knowing the free port before binding the socket, the bind–connect pairs pre-define a caller hierarchy when subprocesses are involved.



Commandline format
==================

Pelita spawns new subprocesses that must conform to the following CLI interface::

    pelita-player $PLAYERNAME $ADDRESS

