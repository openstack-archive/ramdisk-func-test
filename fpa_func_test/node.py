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
import logging
import paramiko
from time import time, sleep
from contextlib import contextmanager
from lxml import etree

from oslo_config import cfg

from fpa_func_test import utils
from fpa_func_test.base import LibvirtBase

opts = [
    cfg.IntOpt('node_boot_timeout',
               help='Time to wait slave node to boot (seconds)',
               default=360),
    cfg.StrOpt('libvirt_machine_type',
               default='',
               help='Libvirt machine type (apply if it is not set in '
                    'template)'),

]
CONF = cfg.CONF
CONF.register_opts(opts)
CONF.import_opt('fpa_func_test_workdir', 'fpa_func_test.utils')

LOG = logging.getLogger(__name__)


class Node(LibvirtBase):

    def __init__(self, templ_engine, template, network, key):
        super(Node, self).__init__(templ_engine)

        self.name = self._generate_name('node')
        self.workdir = os.path.join(CONF.fpa_func_test_workdir, self.name)
        self.network = network
        self.mac = utils.get_random_mac()
        self.ip = None
        self.ssh_login = "root"
        self.ssh_key = key
        self.console_log = os.path.join(self.workdir, "console.log")

        xml = self.templ_engine.render_template(
            template,
            mac_addr=self.mac,
            network_name=network,
            node_name=self.name,
            console_log=self.console_log)

        if CONF.libvirt_machine_type:
            xml_tree = etree.fromstring(xml)
            type_element = xml_tree.find(r'.//os/type')
            if 'machine' not in type_element.keys():
                type_element.set('machine', CONF.libvirt_machine_type)
                xml = etree.tostring(xml_tree)

        self.domain = self._define_domain(xml)

    def _define_domain(self, xml):
        self.libvirt.defineXML(xml)
        dom = self.libvirt.lookupByName(self.name)
        return dom

    def put_file(self, src, dst):
        LOG.info("Putting {0} file to {1} at {2} node".format(
            src, dst, self.name
        ))
        with self._connect_ssh() as ssh:
            sftp = ssh.open_sftp()
            sftp.put(src, dst)

    def get_file(self, src, dst):
        LOG.info("Getting {0} file from {1} node".format(
            src, self.name
        ))
        with self._connect_ssh() as ssh:
            sftp = ssh.open_sftp()
            sftp.get(src, dst)

    def read_file(self, partition, file, part_type='ext4'):
        out, ret_code = self.run_cmd(
            'mount -t {part_type} {partition} /mnt '
            '&& cat /mnt/{file} '
            '&& umount /mnt'.format(**locals()))
        return out

    def run_cmd(self, cmd, check_ret_code=False, get_fuel_log=False):
        LOG.info("Running '{0}' command on {1} node".format(
            cmd, self.name
        ))
        with self._connect_ssh() as ssh:
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            out = stdout.read()
            err = stderr.read()
            ret_code = stdout.channel.recv_exit_status()

        if err:
            LOG.info("{0} cmd {1} stderr below {0}".format("#"*40, cmd))
            LOG.error(err)
            LOG.info("{0} end cmd {1} stderr {0}".format("#"*40, cmd))

        if get_fuel_log:
            LOG.info("{0} bareon log below {0}".format("#"*40))
            out, rc = self.run_cmd('cat /var/log/bareon.log')
            LOG.info(out)
            LOG.info("{0} end bareon log {0}".format("#"*40))

        if check_ret_code and ret_code:
            raise Exception("bareon returned non-zero code: "
                            "{0}".format(ret_code))

        return out, ret_code

    def wait_for_boot(self):
        LOG.info("Waiting {0} node to boot".format(
            self.name))
        utils.wait_net_service(self.ip, 22, timeout=CONF.node_boot_timeout)

    def wait_for_callback(self):

        callback_path = os.path.join(CONF.fpa_func_test_workdir,
                                     self.name, 'callback')
        timeout = CONF.node_boot_timeout
        end = time() + timeout

        while time() < end:
            if os.path.exists(callback_path):
                LOG.info("Callback from node '{0}' received.".format(
                    self.name))
                return
            sleep(1)

        raise Exception("Timeout expired")

    @contextmanager
    def _connect_ssh(self):
        try:
            ssh = paramiko.SSHClient()
            # -oStrictHostKeyChecking=no
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.ip,
                        username=self.ssh_login,
                        key_filename=self.ssh_key,
                        look_for_keys=0)
            yield ssh
        finally:
            ssh.close()

    def reboot_to_hdd(self):
        xml = self.domain.XMLDesc()

        xml_tree = etree.fromstring(xml)
        xml_tree.find(r'.//os/boot').set('dev','hd')

        updated_xml = etree.tostring(xml_tree)

        self.domain = self._define_domain(updated_xml)
        self.stop()
        self.start()

        LOG.info("Boot device for node '{0}' has changed to hdd, node is "
                 "rebooting.".format(self.name))
