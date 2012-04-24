# -*- coding: utf-8 -*-

from datetime import datetime

from pelita.messaging import DispatchingActor, expose, actor_of, actor_registry, StopProcessing, RemoteConnection


class PingRelay2(DispatchingActor):
    @expose
    def wait_a_bit(self):
        self.ref.reply("Yes")

class PingRelay(DispatchingActor):
    def on_start(self):
        self.ping_relay = actor_of(PingRelay2)
        self.ping_relay.start()

    @expose
    def wait_a_bit(self):
        self.ref.reply(self.ping_relay.query("wait_a_bit").get())

class Ping(DispatchingActor):
    def on_start(self):
        self.pong = None
        self.pings_left = 2000

        self.ping_relay = actor_of(PingRelay)
        self.ping_relay.start()

    @expose
    def connect(self, actor_uuid):
        if self.ref.remote:
            self.pong = self.ref.remote.create_proxy(actor_uuid)
        else:
            self.pong = actor_registry.get_by_uuid(actor_uuid)

    @expose
    def Start(self):
        print "Ping: Starting"
        self.pong.notify("Ping", channel=self.ref)
        self.pings_left -= 1

    @expose
    def SendPing(self):
        self.pong.notify("Ping", channel=self.ref)
        self.pings_left -= 1

    @expose
    def Pong(self):
        result = self.ping_relay.query("wait_a_bit")
        result.get()

        if self.pings_left % 100 == 0:
            print "Ping: pong from: " + str(self.ref.channel)
        if self.pings_left > 0:
            self.ref.notify("SendPing")
        else:
            print "Ping: Stop."
            self.pong.notify("Stop", channel=self.ref)
            self.ref.put(StopProcessing)

class Pong(DispatchingActor):
    def on_start(self):
        self.pong_count = 0
        self.old_time = datetime.now()

    @expose
    def Ping(self):
        if self.pong_count % 100 == 0:
            delta = datetime.now() - self.old_time
            self.old_time = datetime.now()
            print "Pong: ping " + str(self.pong_count) + " from " + str(self.ref.channel) + \
                    str(delta.seconds) + "." + str(delta.microseconds // 1000)

        self.ref.channel.notify("Pong", channel=self.ref)
        self.pong_count += 1

    @expose
    def Stop(self):
        print "Pong: Stop."
        self.ref.put(StopProcessing)

import logging
#logging.basicConfig()

remote = True
if remote:

    remote = RemoteConnection().start_listener("localhost", 0)
    remote.register("ping", actor_of(Ping))
    remote.start_all()

    port = remote.listener.socket.port

    ping = RemoteConnection().actor_for("ping", "localhost", port)
else:
    ping = actor_of(Ping)
    ping.start()

pong = actor_of(Pong)
pong.start()

ping.notify("connect", [pong.uuid])
ping.notify("Start")

pong.join()

if remote:
    remote.stop()
else:
    ping.stop()

pong.stop()


