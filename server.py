#!/usr/bin/env python
# encoding: utf-8
VERSION = [0, 2, 0]

import os, sys
sys.path.insert(0, '/Users/tug/Work/projects/cdnmail.ru/website')
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'

import tornado.web
import tornado.escape
import tornado.ioloop
import tornado.web

import django.conf
import django.contrib.auth
import django.core.handlers.wsgi
import django.db
import django.utils.importlib

from tornado.options import define, options
define('port', default=8888, help='Run on the given port', type=int)

import brukva
CHANNEL = 'sse'

import json
from datetime import datetime
from time import time

from sse import Sse
s = Sse()

import json
import time
import logging
import hashlib
#from handler import SSEHandler


def send_message(msg=None):
    #import pdb; pdb.set_trace()
    event, data = json.loads(msg.body)
    clients = MySSEHandler._channels.get(msg.channel, [])
    logging.info('Sending %s "%s" to %s clients' % (event, data, len(clients)))
    for x in clients:
        x.on_message(None, data)


class MainHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    def get(self):
        logging.info('Connection is established')
        self.write('Hello, world')

    def on_connection_close(self):
        logging.info('Connection is closed')


class MySSEHandler(tornado.web.RequestHandler):
    _closing_timeout = False
    _connections = [] # Yes, this list is declared here because it is used by the class methods
    _channels = {}

    def initialize(self):
        #self.set_header('Content-Type','text/event-stream; charset=utf-8')
        self.set_header('Cache-Control','no-cache')
        self.set_header('Connection','keep-alive')

    @tornado.web.asynchronous
    def get(self):
        cls = MySSEHandler

        self.user = self.get_current_user()
        if not self.user:
            self.set_status(403)
            self.finish()
        else:
            self.connection_id = time.time()
            self.channel = self.user
            logging.info('Incoming connection %s to channel "%s"' % (self.connection_id, self.channel))
            if not self.channel in cls._channels:
                cls.client.unsubscribe(cls._channels.keys())
                cls._channels[self.channel] = set()
                cls.client.subscribe(cls._channels.keys())
                cls.client.listen(send_message)
                logging.info('Channels: %s' % ', '.join(cls._channels.keys()))
            cls._channels[self.channel].add(self)

    def on_connection_close(self):
        cls = MySSEHandler
        logging.info('Connection %s is closed' % self.connection_id)
        if len(cls._channels[self.channel]) > 1:
            cls._channels[self.channel].remove(self)
        else:
            del cls._channels[self.channel]
            logging.info('Channels: %s' % ', '.join(cls._channels.keys()))

    def on_message(self, event_id=None, data=None):
        if data:
            message = tornado.escape.utf8(
                '<p>id: %s\ndata: %s\n\n</p>' % (event_id if event_id else '',  data)
            )
            logging.info(message)
            self.write(message)
            self.flush()

    def get_django_session(self):
        if not hasattr(self, '_session'):
            engine = django.utils.importlib.import_module(django.conf.settings.SESSION_ENGINE)
            session_key = self.get_cookie(django.conf.settings.SESSION_COOKIE_NAME)
            self._session = engine.SessionStore(session_key)
        return self._session

    def get_current_user(self):
        """ get_user needs a django request object, but only looks at the session """
        class Dummy: pass

        django_request = Dummy()
        django_request.session = self.get_django_session()
        user = django.contrib.auth.get_user(django_request)
        return user.username if user.is_authenticated() else None

    def send_message(self):
        logging.info('Sending new message')
        MessageSourceHandler.counter += 1
        MessageSourceHandler.write_message_to_all('message', {
            'waiters': len(MessageSourceHandler._live_connections),
            'counter': MessageSourceHandler.counter,
        })

        MessageSourceHandler._msg_timeout = tornado.ioloop.IOLoop.instance().add_timeout(time.time() + 5, self.send_message)


class Application(tornado.web.Application):
    periodic_callbacks = {}

    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            #(r"/sse-handler", MessageSourceHandler),
            #(r'/', MainHandler),
            (r'/sse/', MySSEHandler),
        ]

        settings = dict(
            cookie_secret="43oETzKXQAGaYdkL5gEmGeJJFuYh7EQnp2XdTP1o/Vo=",
            #template_path=os.path.join(os.path.dirname(__file__), "templates"),
            xsrf_cookies=True,
            autoescape=None,
            #login_url='http://127.0.0.1:8000/login/',
        )

        tornado.web.Application.__init__(self, handlers, **settings)


def main():
    tornado.options.parse_command_line()
    logging.info('Come along tornado on port %s...' % options.port)

    application = Application()
    application.listen(options.port)
    application.loop = tornado.ioloop.IOLoop.instance()

#    application.periodic_callbacks['test'] = tornado.ioloop.PeriodicCallback(send_message, 5000, application.loop)
#    application.periodic_callbacks['test'].start()

    application.loop.start()


if __name__ == '__main__':
    try:
        MySSEHandler.client = brukva.Client()
        MySSEHandler.client.connect()
        main()
    except KeyboardInterrupt, e:
        pass
    finally:
        MySSEHandler.client.disconnect()
        logging.info('Shutdowned')
