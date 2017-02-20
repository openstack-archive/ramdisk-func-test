#!/usr/bin/env python
#
# Copyright 2016 Cray Inc., All Rights Reserved
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Mock web-server.

It gets 2 positional parameters:
- host
- port

For GET requests:
- If URL contains '/fake' at the beginning, mock web-server returns content
  of ./stubfile
- If URL is like '/tenant_images/<name>' at the beginning, mock web-server
  returns content of <name> file from folder specified in third positional
  parameter
- Fof all other cases, it tries to return appropriate file (e.g.
  '/tmp/banana.txt' for URL 'http://host:port/tmp/banana.txt')

For POST requests:
- If URL contains '/v1/nodes/<node_id>/vendor_passthru', mock web-server
  creates empty file with 'callback' name at subfolder named by <node_id>, in
  fpa_func_test working dir (and returns 202, with content of ./stubfile)
"""

import argparse
import json
import os
import SimpleHTTPServer
import SocketServer
import logging
import pkg_resources
import signal
import sys
import re
import tempfile

from ramdisk_func_test import conf


logging.basicConfig(filename='/tmp/mock-web-server.log',
                    level=logging.DEBUG,
                    format='%(asctime)s %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p')

CONF = conf.CONF
CONF.import_opt('tenant_images_dir', 'ramdisk_func_test.environment')
CONF.import_opt('ramdisk_func_test_workdir', 'ramdisk_func_test.utils')
LOG = logging.getLogger(__name__)

httpd = None


class RequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def __init__(self, ctx, *args, **kwargs):
        self.ctx = ctx
        SimpleHTTPServer.SimpleHTTPRequestHandler.__init__(
            self, *args, **kwargs)

    def do_GET(self):
        LOG.info('Got GET request: %s', self.path)
        fake_check = re.match(r'/fake', self.path)
        tenant_images_match = re.match(r'/tenant_images/(.*)$', self.path)
        deploy_steps_match = re.match(
            r'/v1/nodes/([^/]*)/vendor_passthru/deploy_steps', self.path)

        if fake_check is not None:
            LOG.info("This is 'fake' request.")
            self.path = os.path.join(self.ctx.htdocs, 'stubfile')
        elif tenant_images_match is not None:
            LOG.info("This is 'tenant-images' request: %s", self.path)
            tenant_image = tenant_images_match.group(1)
            self.path = os.path.join(self.ctx.images_path, tenant_image)
        elif deploy_steps_match is not None:
            with open('{}.2.pub'.format(self.ctx.ssh_key)) as data:
                ssh_key = data.read().rstrip()

            data = {
                'action': {
                    'name': 'inject-ssh-keys',
                    'payload': {
                        'ssh-keys': {
                            'root': [ssh_key]
                        }
                    }
                }
            }
            tmp = tempfile.NamedTemporaryFile()
            json.dump(data, tmp)
            tmp.flush()

            self.path = tmp.name

        return SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        deploy_steps_match = re.match(
            r'/v1/nodes/([^/]*)/vendor_passthru/deploy_steps', self.path)
        callback_match = re.search(
            r'/v1/nodes/([^/]*)/vendor_passthru', self.path)

        if deploy_steps_match is not None:
            tmp = tempfile.NamedTemporaryFile()
            json.dump({'url': None}, tmp)
            tmp.flush()

            self.path = tmp.name
        elif callback_match is not None:
            callback_file_path = os.path.join(
                CONF.ramdisk_func_test_workdir, callback_match.group(1),
                'callback')
            open(callback_file_path, 'a').close()
            LOG.info("Got callback: %s", self.path)
            self.path = os.path.join(self.ctx.htdocs, 'stubfile')

        return SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)

    def send_head(self):
        """Common code for GET and HEAD commands.

        This sends the response code and MIME headers.

        Return value is either a file object (which has to be copied
        to the output file by the caller unless the command was HEAD,
        and must be closed by the caller under all circumstances), or
        None, in which case the caller has nothing further to do.

        """
        path = self.path
        ctype = self.guess_type(path)
        try:
            # Always read in binary mode. Opening files in text mode may cause
            # newline translations, making the actual size of the content
            # transmitted *less* than the content-length!
            payload = open(path, 'rb')
        except IOError:
            self.send_error(404, "File not found ({0})".format(path))
            return None

        if self.command == 'POST':
            self.send_response(202)
        else:
            self.send_response(200)

        stat = os.fstat(payload.fileno())

        self.send_header("Content-type", ctype)
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
        self.end_headers()

        return payload


class HandlerFactory(object):
    def __init__(self, ctx, halder_class):
        self.ctx = ctx
        self.handler_class = halder_class

    def __call__(self, *args, **kwargs):
        return self.handler_class(self.ctx, *args, **kwargs)


class Context(object):
    def __init__(self):
        self.images_path = CONF.tenant_images_dir
        self.htdocs = pkg_resources.resource_filename(__name__, 'data')
        self.ssh_key = os.path.join(CONF.image_build_dir, CONF.ramdisk_key)


def signal_term_handler(signal, frame):
    LOG.info("ramdisk-func-test stub web server terminating ...")
    try:
        httpd.server_close()
    except Exception:
        LOG.error('Cannot close server!', exc_info=True)
        sys.exit(1)
    LOG.info("ramdisk-func-test stub web server has terminated.")
    sys.exit(0)


def main():
    global httpd

    argp = argparse.ArgumentParser()
    argp.add_argument('address', help='Bind address')
    argp.add_argument('port', help='Bind port', type=int)

    cli = argp.parse_args()

    bind = (cli.address, cli.port)
    handler = HandlerFactory(Context(), RequestHandler)
    try:
        SocketServer.TCPServer.allow_reuse_address = True
        httpd = SocketServer.TCPServer(bind, handler)
    except Exception:
        LOG.error('=' * 80)
        LOG.error('Error in webserver start stage', exc_info=True)
        sys.exit(1)

    LOG.info('=' * 80)
    LOG.info('ramdisk-func-test stub webserver started at %s:%s '
             '(tenant-images path is %s)',
             cli.address, cli.port, handler.ctx.images_path)

    signal.signal(signal.SIGTERM, signal_term_handler)
    httpd.serve_forever()
