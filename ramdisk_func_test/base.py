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

import logging
import uuid

import libvirt
from oslo_config import cfg

from ramdisk_func_test import conf


CONF = conf.CONF
CONF.register_opts([
    cfg.StrOpt('qemu_url',
               help='URL of qemu server.',
               default="qemu:///system"),
])

LOG = logging.getLogger(__name__)


class LibvirtBase(object):
    """Generic wrapper for libvirt domain objects."""
    libvirt = libvirt.open(CONF.qemu_url)

    def __init__(self, jinja_env):
        super(LibvirtBase, self).__init__()
        self.jinja_env = jinja_env
        # Initialized in child classes
        self.name = None
        self.domain = None

    def _generate_name(self, base):
        short_uid = str(uuid.uuid4())[:8]
        # Same string hardcoded in tools/cleanup.sh
        return "rft-{0}-{1}".format(base, short_uid)

    def start(self):
        LOG.debug("Starting domain %s" % self.name)
        self.domain.create()

    def stop(self):
        LOG.debug("Stopping domain %s" % self.name)
        self.domain.destroy()

    def reboot(self):
        LOG.debug("Rebooting domain %s" % self.name)
        self.domain.reboot()

    def kill(self):
        LOG.debug("Killing domain %s" % self.name)
        calls = (
            "destroy",
            "undefine"
        )
        for call in calls:
            try:
                getattr(self.domain, call)()
            except Exception as err:
                LOG.warning("Error during domain '{0}' call:\n{1}".format(
                    call, err.message
                ))
