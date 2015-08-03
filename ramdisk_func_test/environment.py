#
# 2016 Cray Inc., All Rights Reserved
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
import shutil
import subprocess
import json
import logging
import time
import sh

from oslo_config import cfg

from ramdisk_func_test import utils
from ramdisk_func_test.base import TemplateEngine
from ramdisk_func_test.base import ABS_PATH
from ramdisk_func_test.network import Network
from ramdisk_func_test.node import Node


opts = [
    cfg.StrOpt('image_build_dir',
               default="/tmp/rft_image_build",
               help='A path where images from DIB will be build. Expected '
                    'build artifacts are: kernel, ramdisk, ramdisk_key'),
    cfg.StrOpt('tenant_images_dir',
               default="/tmp/rft_golden_images",
               help='A path where mock web-server will take tenant images '),
    cfg.StrOpt('kernel',
               default='vmlinuz',
               help='Name of kernel image'),
    cfg.StrOpt('ramdisk',
               default='initramfs',
               help='Name of ramdisk image'),
    cfg.StrOpt('ramdisk_key',
               default='fuel_key',
               help='Name of private ssh key to access ramdisk'),
]

CONF = cfg.CONF
CONF.register_opts(opts)
CONF.import_opt('ramdisk_func_test_workdir', 'ramdisk_func_test.utils')

LOG = logging.getLogger(__name__)


class Environment(object):
    HTTP_PORT = "8011"

    def __init__(self, node_templates):
        super(Environment, self).__init__()
        self.templ_eng = TemplateEngine(node_templates)

        self.node = None
        self.network = None
        self.webserver = None
        self.tenant_images_dir = None
        self.rsync_dir = None
        self.image_mount_point = None

    def setupclass(self):
        """Global setup - single for all tests"""
        self.network = Network(self.templ_eng)
        self.network.start()

        self.tenant_images_dir = CONF.tenant_images_dir

        self._setup_webserver()
        self._check_rsync()
        self._setup_pxe()

    def setup(self, node_template, deploy_config):
        """Per-test setup"""
        ssh_key_path = os.path.join(CONF.image_build_dir, CONF.ramdisk_key)
        self.node = Node(self.templ_eng,
                         node_template,
                         self.network.name,
                         ssh_key_path)

        self.add_pxe_config_for_current_node()
        self.network.add_node(self.node)

        path = self._save_provision_json_for_node(deploy_config)

        self.node.start()
        self.node.wait_for_callback()

        self.node.put_file(path, '/tmp/provision.json')

    def teardown(self):
        """Per-test teardown"""
        self.network.remove_node(self.node)
        self.node.kill()
        self._delete_node_workdir(self.node)

    def teardownclass(self):
        """Global tear down - single for all tests"""
        LOG.info("Tearing down Environment class...")
        self._teardown_webserver()
        self._teardown_rsync()

        self.network.kill()
        self._delete_workdir()

    def _setup_pxe(self):
        LOG.info("Setting up PXE configuration/images")
        tftp_root = self.network.tftp_root
        img_build = CONF.image_build_dir
        utils.copy_file(os.path.join(ABS_PATH, "pxe/pxelinux.0"), tftp_root)
        utils.copy_file(os.path.join(img_build, CONF.kernel), tftp_root)
        utils.copy_file(os.path.join(img_build, CONF.ramdisk), tftp_root)

    def add_pxe_config_for_current_node(self):
        LOG.info("Setting up PXE configuration file fo node {0}".format(
            self.node.name))

        tftp_root = self.network.tftp_root

        pxe_config = self.templ_eng.render_template(
            'bareon_config.template',
            kernel=CONF.kernel,
            ramdisk=CONF.ramdisk,
            deployment_id=self.node.name,
            api_url="http://{0}:{1}".format(self.network.address,
                                            self.HTTP_PORT)
        )

        pxe_path = os.path.join(tftp_root, "pxelinux.cfg")
        utils.ensure_tree(pxe_path)

        conf_path = os.path.join(pxe_path, '01-{0}'.format(
            self.node.mac.replace(':', '-')))
        with open(conf_path, 'w') as f:
            f.write(pxe_config)

    def _setup_webserver(self, port=HTTP_PORT):

        LOG.info("Starting stub webserver (at IP {0} port {1}, path to tenant "
                 "images folder is '{2}')".format(self.network.address,
                                                  port,
                                                  self.tenant_images_dir))

        # TODO(max_lobur) make webserver singletone
        self.webserver = subprocess.Popen(
            ['python',
             os.path.join(ABS_PATH, 'webserver/server.py'),
             self.network.address, port, self.tenant_images_dir], shell=False)

    def get_url_for_image(self, image_name, source_type):
        if source_type == 'swift':
            return self._get_swift_tenant_image_url(image_name)
        elif source_type == 'rsync':
            return self._get_rsync_tenant_image_url(image_name)
        else:
            raise Exception("Unknown deploy_driver")

    def get_url_for_stub_image(self):
        return "http://{0}:{1}/fake".format(self.network.address,
                                            self.HTTP_PORT)

    def _get_swift_tenant_image_url(self, image_name):
        return ("http://{0}:{1}/tenant_images/"
                "{2}".format(self.network.address, self.HTTP_PORT, image_name))

    def _get_rsync_tenant_image_url(self, image_name):
        url = "{0}::ironic_rsync/{1}/".format(self.network.address,
                                              image_name)
        image_path = os.path.join(self.tenant_images_dir, image_name)
        if os.path.exists(image_path):
            image_mount_point = os.path.join(self.rsync_dir, image_name)
            self.image_mount_point = image_mount_point
            utils.ensure_tree(image_mount_point)
            sh.sudo.mount('-o', 'loop,ro', image_path, image_mount_point)
            if not os.path.exists('{0}/etc/passwd'.format(
                    image_mount_point)):
                raise Exception('Mounting of image did not happen')
        else:
            raise Exception("There is no such file '{0}' in '{1}'".format(
                image_name, self.tenant_images_dir))
        return url

    def _save_provision_json_for_node(self, deploy_config):
        prov_json = json.dumps(deploy_config)
        path = os.path.join(self.node.workdir, "provision.json")
        with open(path, "w") as f:
            f.write(prov_json)
        return path

    def _teardown_webserver(self):
        LOG.info("Stopping stub web server ...")
        self.webserver.terminate()

        for i in range(0, 15):
            if self.webserver.poll() is not None:
                LOG.info("Stub web server has stopped.")
                return
            time.sleep(1)
        LOG.warning("Cannot terminate web server in 15 sec!")

    def _delete_workdir(self):
        LOG.info("Deleting workdir {0}".format(CONF.ramdisk_func_test_workdir))
        shutil.rmtree(CONF.ramdisk_func_test_workdir)

    def _delete_node_workdir(self, node):
        wdir = node.workdir
        LOG.info("Deleting node workdir {0}".format(wdir))
        shutil.rmtree(wdir)

    def _check_rsync(self):

        rsync_config_path = "/etc/rsyncd.conf"
        rsync_ironic_section_name = 'ironic_rsync'

        if not utils._pid_of('rsync'):
            raise Exception('No rsync process is running')

        if os.path.exists(rsync_config_path):
            cfg = utils.read_config(rsync_config_path)
        else:
            raise Exception('No rsyncd config file found at {0}'.format(
                rsync_config_path
            ))

        if rsync_ironic_section_name in cfg.sections():
            self.rsync_dir = cfg.get(rsync_ironic_section_name, 'path')
        else:
            raise Exception('There is no ironic section ({0}) in rsync '
                            'config file'.format(rsync_ironic_section_name))

    def _teardown_rsync(self):
        if self.image_mount_point:
            sh.sudo.umount(self.image_mount_point)
            sh.rmdir(self.image_mount_point)
