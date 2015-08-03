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
import os
import sys

import libvirt
import jinja2

from oslo_config import cfg

import utils


def _setup_config():
    cfg.CONF([], default_config_files=[
        "/etc/ramdisk-func-test/ramdisk-func-test.conf"])


def _setup_loggging():
    for pair in [
        'paramiko=WARN',
        'ironic.openstack.common=WARN',
    ]:
        mod, _sep, level_name = pair.partition('=')
        logger = logging.getLogger(mod)
        # NOTE(AAzza) in python2.6 Logger.setLevel doesn't convert string name
        # to integer code.
        if sys.version_info < (2, 7):
            level = logging.getLevelName(level_name)
            logger.setLevel(level)
        else:
            logger.setLevel(level_name)


_setup_config()
_setup_loggging()

opts = [
    cfg.StrOpt('qemu_url',
               help='URL of qemu server.',
               default="qemu:///system"),
]
CONF = cfg.CONF
CONF.register_opts(opts)

LOG = logging.getLogger(__name__)

ABS_PATH = os.path.dirname(os.path.abspath(__file__))


class LibvirtBase(object):
    """Generic wrapper for libvirt domain objects."""
    libvirt = libvirt.open(CONF.qemu_url)

    def __init__(self, templ_engine):
        super(LibvirtBase, self).__init__()
        self.templ_engine = templ_engine
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


class TemplateEngine(object):
    def __init__(self, node_templates):
        super(TemplateEngine, self).__init__()
        loader = jinja2.FileSystemLoader([
            node_templates,
            os.path.join(ABS_PATH, "templates")
        ])
        self._jinja = jinja2.Environment(loader=loader)

        # Custom template callbacks
        self._jinja.globals['empty_disk'] = utils.create_empty_disk
        self._jinja.globals['disk_from_base'] = utils.create_disk_from_base
        self._jinja.globals['get_rand_mac'] = utils.get_random_mac

    def render_template(self, template_name, **kwargs):
        template = self._jinja.get_template(template_name)
        return template.render(**kwargs)
