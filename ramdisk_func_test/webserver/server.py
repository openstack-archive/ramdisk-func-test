#!/usr/bin/env python
#
# Copyright 2016 Cray Inc.  All Rights Reserved.
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


import os
import SimpleHTTPServer
import SocketServer
import logging
import signal
import sys
import traceback
import re

from oslo_config import cfg

from ramdisk_func_test.base import ABS_PATH


CONF = cfg.CONF
LOG = logging.getLogger(__name__)
logging.basicConfig(filename='/tmp/mock-web-server.log',
                    level=logging.DEBUG,
                    format='%(asctime)s %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p')


class MyRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):

    path_to_images_folder = None

    @classmethod
    def _set_path_to_images_folder(cls, path):
        cls.path_to_images_folder = path

    def do_GET(self):

        LOG.info("Got GET request: {0} ".format(self.path))
        fake_check = re.match(r'/fake', self.path)
        tenant_images_check = re.match(r'/tenant_images/', self.path)

        if fake_check is not None:
            LOG.info("This is 'fake' request.")
            self.path = os.path.join(ABS_PATH, 'webserver', 'stubfile')
        elif tenant_images_check is not None:
            LOG.info("This is 'tenant-images' request: {0} ".format(self.path))
            tenant_images_name = re.match(
                r'/tenant_images/(.*)', self.path).group(1)
            self.path = os.path.join(
                self.path_to_images_folder, tenant_images_name)

        return SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):

        callback_check = re.search(
            r'/v1/nodes/([^/]*)/vendor_passthru', self.path)

        if callback_check is not None:
            callback_file_path = os.path.join(
                CONF.ramdisk_func_test_workdir, callback_check.group(1),
                'callback')
            open(callback_file_path, 'a').close()
            LOG.info("Got callback: {0} ".format(self.path))

        self.path = os.path.join(ABS_PATH, 'webserver', 'stubfile')
        return SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)

    def send_head(self):
        """Common code for GET and HEAD commands.

        This sends the response code and MIME headers.

        Return value is either a file object (which has to be copied
        to the output file by the caller unless the command was HEAD,
        and must be closed by the caller under all circumstances), or
        None, in which case the caller has nothing further to do.

        """
        f = None
        path = self.path
        ctype = self.guess_type(path)
        try:
            # Always read in binary mode. Opening files in text mode may cause
            # newline translations, making the actual size of the content
            # transmitted *less* than the content-length!
            f = open(path, 'rb')
        except IOError:
            self.send_error(404, "File not found ({0})".format(path))
            return None

        if self.command == 'POST':
            self.send_response(202)
        else:
            self.send_response(200)

        self.send_header("Content-type", ctype)
        fs = os.fstat(f.fileno())
        self.send_header("Content-Length", str(fs[6]))
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        return f


Handler = MyRequestHandler

httpd = None


def signal_term_handler(s, f):
    LOG.info("ramdisk-func-test stub web server terminating ...")
    try:
        httpd.server_close()
    except:
        LOG.error("Cannot close server!")
        sys.exit(1)
    LOG.info("ramdisk-func-test stub web server has terminated.")
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_term_handler)

if __name__ == "__main__":

    try:
        host = sys.argv[1]
        port = int(sys.argv[2])
        path_to_images_folder = sys.argv[3]
    except IndexError:
        LOG.error("Mock web-server cannot get enough valid parameters!")
        exit(1)

    Handler._set_path_to_images_folder(path_to_images_folder)

    try:
        SocketServer.TCPServer.allow_reuse_address = True
        httpd = SocketServer.TCPServer((host, port), Handler)
    except:
        LOG.error("="*80)
        LOG.error("Cannot start: {0}".format(traceback.format_exc()))
        exit(1)

    LOG.info("="*80)
    LOG.info("ramdisk-func-test stub webserver started at {0}:{1} "
             "(tenant-images path is '{2}')".format(
        host, port, path_to_images_folder))

    httpd.serve_forever()
