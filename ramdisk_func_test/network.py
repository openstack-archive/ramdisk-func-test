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

import os
import random
import logging
import libvirt

from oslo_config import cfg

from ramdisk_func_test import base
from ramdisk_func_test import conf
from ramdisk_func_test import utils


CONF = conf.CONF
CONF.register_opts([
    cfg.StrOpt('libvirt_net_head_octets',
               default="192.168",
               help='Head octets for libvirt network (choose free one).'),
    cfg.IntOpt('libvirt_net_range_start',
               default=100,
               help='Libvirt network DHCP range start.'),
    cfg.IntOpt('libvirt_net_range_end',
               default=254,
               help='Libvirt network DHCP range end.')
])
CONF.import_opt('ramdisk_func_test_workdir', 'ramdisk_func_test.utils')

LOG = logging.getLogger(__name__)


class Network(base.LibvirtBase):
    def __init__(self, jinja_env):
        super(Network, self).__init__(jinja_env)

        self.name = self._generate_name("net")
        head_octets = CONF.libvirt_net_head_octets
        free_net = self._find_free_libvirt_network(head_octets)
        self.address = "{0}.1".format(free_net)
        range_start = '{0}.{1}'.format(free_net, CONF.libvirt_net_range_start)
        range_end = '{0}.{1}'.format(free_net, CONF.libvirt_net_range_end)

        self.tftp_root = os.path.join(CONF.ramdisk_func_test_workdir,
                                      'tftp_root')
        utils.ensure_tree(self.tftp_root)

        xml = self.jinja_env.get_template('network.xml').render(
            name=self.name,
            bridge=self._generate_name("br"),
            address=self.address,
            tftp_root=self.tftp_root,
            range_start=range_start,
            range_end=range_end)
        self.domain = self._define_domain(xml)

    def _define_domain(self, xml):
        self.libvirt.networkDefineXML(xml)
        dom = self.libvirt.networkLookupByName(self.name)
        return dom

    def add_node(self, node):
        LOG.info("Adding {0} node to {1} network".format(
            node.name, self.name
        ))
        # TODO(lobur): take IP from DHCP instead
        ip = "{0}.{1}".format(self.address[:-2],
                              random.randint(CONF.libvirt_net_range_start,
                                             CONF.libvirt_net_range_end))
        self.domain.update(
            libvirt.VIR_NETWORK_UPDATE_COMMAND_ADD_LAST,
            libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST,
            -1,
            '<host mac="{mac}" name="{name}" ip="{ip}" />'.format(
                mac=node.mac,
                name=node.name,
                ip=ip))
        node.ip = ip

    def remove_node(self, node):
        LOG.info("Removing {0} node from {1} network".format(
            node.name, self.name
        ))
        self.domain.update(
            libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE,
            libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST,
            -1,
            '<host mac="{mac}" name="{name}" ip="{ip}" />'.format(
                mac=node.mac,
                name=node.name,
                ip=node.ip))
        node.ip = None

    def _find_free_libvirt_network(self, head):
        existing_nets = [n.XMLDesc() for n in self.libvirt.listAllNetworks()]
        for addr in range(254):
            pattern = '{0}.{1}'.format(head, addr)
            unique = all([pattern not in net_xml for net_xml in existing_nets])
            if unique:
                return pattern
        raise Exception("Cannot find free libvirt net in {0}".format(head))
