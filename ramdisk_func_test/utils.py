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

import ConfigParser
import os
import logging
import shutil
import random
from subprocess import check_output

from oslo_config import cfg

from ramdisk_func_test import conf


CONF = conf.CONF
CONF.register_opts([
    cfg.StrOpt('ramdisk_func_test_workdir',
               help='Path where virtualized node disks will be stored.',
               default="/tmp/ramdisk-func-test/"),
])

LOG = logging.getLogger(__name__)


def ensure_tree(path):
    if not os.path.exists(path):
        os.makedirs(path)


def _build_disk_path(node_name, disk_name):
    workdir = CONF.ramdisk_func_test_workdir
    node_disks_path = os.path.join(workdir, node_name, "disks")
    ensure_tree(node_disks_path)

    path = "{disks}/{disk_name}.img".format(disks=node_disks_path,
                                            disk_name=disk_name)
    return path


def create_empty_disk(node_name, disk_name, size):
    path = _build_disk_path(node_name, disk_name)
    cmd = ["/usr/bin/qemu-img", "create", "-f", "raw", path, size]
    LOG.info(check_output(cmd))
    return path


def create_disk_from_base(node_name, disk_name, base_image_path):
    path = _build_disk_path(node_name, disk_name)
    shutil.copy(base_image_path, path)
    return path


def copy_file(source_file, dest_dir):
    ensure_tree(dest_dir)
    shutil.copy(source_file, dest_dir)


def get_random_mac():
    rnd = lambda: random.randint(0, 255)
    return "52:54:00:%02x:%02x:%02x" % (rnd(), rnd(), rnd())


class FakeGlobalSectionHead(object):
    def __init__(self, fp):
        self.fp = fp
        self.sechead = '[global]\n'

    def readline(self):
        if self.sechead:
            try:
                return self.sechead
            finally:
                self.sechead = None
        else:
            return self.fp.readline()


def read_config(path):
    cfg = ConfigParser.ConfigParser()
    cfg.readfp(FakeGlobalSectionHead(open(path)))
    return cfg


def _pid_of(name):
    cmd = ['ps', '-o', 'pid=', '-C', name]
    pidset = check_output(cmd).rstrip()
    return [(int(x) for x in pidset.splitlines())]
