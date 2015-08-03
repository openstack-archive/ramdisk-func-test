# Needs to be run from root e.g. sudo python tools/setup_rsync.py
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
import os.path
import distutils.spawn
import ConfigParser
import logging
import subprocess
import shlex

from fpa_func_test import utils

LOG = logging.getLogger(__name__)

RSYNC_CFG_PATH = "/etc/rsyncd.conf"
RSYNC_DIR = '/tmp/ironic_rsync'
RSYNC_STUB_FILE = os.path.join(RSYNC_DIR, 'fake')
RSYNC_IRONIC_CONF_SEC = 'ironic_rsync'


def ensure_tree(path):
    if not os.path.exists(path):
        os.makedirs(path)


LOG.info("Checking rsync binary...")
rsync_binary_path = distutils.spawn.find_executable('rsync')
if not rsync_binary_path:
    raise Exception('Cannot find rsync binary')

LOG.info("Touching rsync config file ...")
open(RSYNC_CFG_PATH, 'a').close()

LOG.info("Touching rsync_dir and rsync_stub_filename...")
ensure_tree(RSYNC_DIR)
os.chmod(RSYNC_DIR, 0777)
if not os.path.exists(RSYNC_STUB_FILE):
    fake = open(RSYNC_STUB_FILE, 'w')
    fake.write('{}')
    fake.close()
os.chmod(RSYNC_STUB_FILE, 0777)

LOG.info("Touching Ironic section in rsync config ...")
rsync_config = ConfigParser.ConfigParser()
rsync_config.read(RSYNC_CFG_PATH)
if RSYNC_IRONIC_CONF_SEC not in rsync_config.sections():
    rsync_config.add_section(RSYNC_IRONIC_CONF_SEC)
    rsync_config.set(RSYNC_IRONIC_CONF_SEC, 'uid', 'root')
    rsync_config.set(RSYNC_IRONIC_CONF_SEC, 'gid', 'root')
    rsync_config.set(RSYNC_IRONIC_CONF_SEC, 'path', RSYNC_DIR)
    rsync_config.set(RSYNC_IRONIC_CONF_SEC, 'read_only', 'true')
    with open(RSYNC_CFG_PATH, 'wb') as configfile:
        rsync_config.write(configfile)
        LOG.info("Ironic section has added to rsync config.")
else:
    LOG.info("Ironic section is already presenting in rsync config.")
    if rsync_config.get(RSYNC_IRONIC_CONF_SEC, 'path') != RSYNC_DIR:
        raise Exception('Path in existing ironic.conf section and script '
                        'setting mismatch')

LOG.info("Starting rsync daemon if not started so far")
if not utils._pid_of('rsync'):
    cmd = '{rsync_binary_path} --daemon --no-detach'.format(
        rsync_binary_path=rsync_binary_path)
    args = shlex.split(cmd)
    p = subprocess.Popen(args)
else:
    LOG.info("...Rsync process is already running.")

exit(0)
