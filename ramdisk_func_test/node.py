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
import logging
import paramiko
from time import time
from time import sleep
from contextlib import contextmanager
from lxml import etree

from oslo_config import cfg

from ramdisk_func_test import base
from ramdisk_func_test import conf
from ramdisk_func_test import exception
from ramdisk_func_test import utils


CONF = conf.CONF
CONF.register_opts([
    cfg.IntOpt('node_boot_timeout',
               help='Time to wait slave node to boot (seconds)',
               default=360),
    cfg.StrOpt('libvirt_machine_type',
               default='',
               help='Libvirt machine type (apply if it is not set in '
                    'template)'),
])
CONF.import_opt('ramdisk_func_test_workdir', 'ramdisk_func_test.utils')

LOG = logging.getLogger(__name__)


class Node(base.LibvirtBase):
    def __init__(self, jinja_env, template, network, key):
        super(Node, self).__init__(jinja_env)

        self.name = self._generate_name('node')
        self.workdir = os.path.join(CONF.ramdisk_func_test_workdir, self.name)
        self.network = network
        self.mac = utils.get_random_mac()
        self.ip = None
        self.ssh_login = "root"
        self.ssh_key = key
        self.console_log = os.path.join(self.workdir, "console.log")

        xml = self.jinja_env.get_template(template).render(
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
            '; umount /mnt'.format(**locals()))
        return out

    def write_file(self, partition, file, contents, part_type='ext4'):
        out, ret_code = self.run_cmd(
            'mount -t {part_type} {partition} /mnt '
            '&& echo \'{contents}\' > /mnt/{file} '
            '; umount /mnt'.format(**locals()))
        return out

    def run_cmd(self, cmd, check_ret_code=False, get_bareon_log=False):
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

        if get_bareon_log:
            LOG.info("{0} bareon log below {0}".format("#"*40))
            out, rc = self.run_cmd('cat /var/log/bareon.log')
            LOG.info(out)
            LOG.info("{0} end bareon log {0}".format("#"*40))

        if check_ret_code and ret_code:
            raise exception.NonZeroCmdRetCode(cmd=cmd, ret_code=ret_code)

        return out, ret_code

    def wait_for_boot(self):
        LOG.info("Waiting {0} node to boot".format(
            self.name))
        timeout = CONF.node_boot_timeout
        end = time() + timeout

        while time() < end:
            try:
                self.run_cmd('ls')  # dummy cmd to check connection
                return
            except Exception:
                pass

            sleep(1)

        raise exception.NodeBootTimeout(timeout=timeout,
                                        node_name=self.name)

    def wait_for_callback(self):

        callback_path = os.path.join(CONF.ramdisk_func_test_workdir,
                                     self.name, 'callback')
        timeout = CONF.node_boot_timeout
        end = time() + timeout

        while time() < end:
            if os.path.exists(callback_path):
                LOG.info("Callback from node '{0}' received.".format(
                    self.name))
                return
            sleep(1)

        raise exception.NodeCallbackTimeout(timeout=timeout,
                                            node_name=self.name)

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
        xml_tree.find(r'.//os/boot').set('dev', 'hd')

        updated_xml = etree.tostring(xml_tree)

        self.domain = self._define_domain(updated_xml)
        self.stop()
        self.start()

        LOG.info("Boot device for node '{0}' has changed to hdd, node is "
                 "rebooting.".format(self.name))
