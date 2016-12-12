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

import errno
import os
import shutil
import subprocess
import json
import logging
import time
import sh

import jinja2
import pkg_resources
from oslo_config import cfg

import ramdisk_func_test
from ramdisk_func_test import conf
from ramdisk_func_test import network
from ramdisk_func_test import node
from ramdisk_func_test import utils


CONF = conf.CONF
CONF.register_opts([
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
               default='bareon_key',
               help='Name of private ssh key to access ramdisk'),
    # NOTE(oberezovskyi): path from Centos 7 taken as default
    cfg.StrOpt('pxelinux',
               default='/usr/share/syslinux/pxelinux.0',
               help='Path to pxelinux.0 file'),
    cfg.IntOpt('stub_webserver_port',
               default=8011,
               help='The port used by stub webserver')
])
CONF.import_opt('ramdisk_func_test_workdir', 'ramdisk_func_test.utils')

LOG = logging.getLogger(__name__)


class Environment(object):
    _loaded_config = object()  # to fail comparison with None

    deploy_driver = None
    node = None
    network = None
    webserver = None
    rsync_dir = None
    image_mount_point = None

    def __init__(self, template_path, config=None):
        super(Environment, self).__init__()
        self._load_config(config)
        self.jinja_env = self._init_jinja2(template_path)

    @staticmethod
    def _init_jinja2(path):
        path = path[:]
        path.append(pkg_resources.resource_filename(
            ramdisk_func_test.__name__, 'templates'))
        loader = jinja2.FileSystemLoader(path)
        jinja_env = jinja2.Environment(loader=loader)

        # Custom template callbacks
        jinja_env.globals['empty_disk'] = utils.create_empty_disk
        jinja_env.globals['disk_from_base'] = utils.create_disk_from_base
        jinja_env.globals['get_rand_mac'] = utils.get_random_mac

        return jinja_env

    def setupclass(self):
        """Global setup - single for all tests"""
        self.network = network.Network(self.jinja_env)
        self.network.start()

        self._setup_webserver()
        self._check_rsync()
        self._setup_pxe()

    def setup(self, node_template, deploy_config, tenant_image=None,
              deploy_driver='swift'):
        """Per-test setup"""
        self.deploy_driver = deploy_driver
        ssh_key_path = os.path.join(CONF.image_build_dir, CONF.ramdisk_key)
        self.node = node.Node(
            self.jinja_env, node_template, self.network.name, ssh_key_path)

        public_key = '.'.join([ssh_key_path, 'pub'])
        self._generate_cloud_config(public_key)
        self.add_pxe_config_for_current_node()
        self.network.add_node(self.node)

        deploy_config = self._set_tenant_image(deploy_config, tenant_image)
        path = self._save_provision_json_for_node(deploy_config)

        self.node.start()
        self.node.wait_for_callback()
        self.node.put_file(path, '/tmp/provision.json')

    def teardown(self):
        """Per-test teardown"""
        self.network.remove_node(self.node)
        self.node.kill()
        self._delete_node_workdir(self.node)
        self._teardown_rsync()

    def teardownclass(self):
        """Global tear down - single for all tests"""
        LOG.info("Tearing down Environment class...")
        self._teardown_webserver()

        self.network.kill()
        self._delete_workdir()

    def _setup_pxe(self):
        LOG.info("Setting up PXE configuration/images")
        tftp_root = self.network.tftp_root
        img_build = CONF.image_build_dir
        utils.copy_file(CONF.pxelinux, tftp_root)
        utils.copy_file(os.path.join(img_build, CONF.kernel), tftp_root)
        utils.copy_file(os.path.join(img_build, CONF.ramdisk), tftp_root)

    def add_pxe_config_for_current_node(self):
        LOG.info("Setting up PXE configuration file for node {0}".format(
            self.node.name))

        tftp_root = self.network.tftp_root

        template = self.jinja_env.get_template('bareon_config.template')
        pxe_config = template.render(
            kernel=CONF.kernel,
            ramdisk=CONF.ramdisk,
            deployment_id=self.node.name,
            network=self.network,
            stub_server_port=CONF.stub_webserver_port)

        pxe_path = os.path.join(tftp_root, "pxelinux.cfg")
        utils.ensure_tree(pxe_path)

        conf_path = os.path.join(pxe_path, '01-{0}'.format(
            self.node.mac.replace(':', '-')))
        with open(conf_path, 'w') as f:
            f.write(pxe_config)

    def _generate_cloud_config(self, public_key):
        """"Used to support logging into the tenant image."""
        with open(public_key, 'r') as f:
            key = f.readline()

        template = self.jinja_env.get_template('cloud.cfg.template')
        path = os.path.join(self.node.workdir, 'cloud.cfg')
        with open(path, 'w') as f:
            f.write(template.render(fuel_public_key=key))

    def _setup_webserver(self):
        port = CONF.stub_webserver_port
        LOG.info("Starting stub webserver (at IP {0} port {1}, path to tenant "
                 "images folder is '{2}')".format(self.network.address, port,
                                                  CONF.tenant_images_dir))

        # TODO(max_lobur) make webserver singletone
        cmd = ['ramdisk-stub-webserver', self.network.address, str(port)]
        self.webserver = subprocess.Popen(cmd, shell=False)

    def _set_tenant_image(self, deploy_config, image_name=None):
        if isinstance(image_name, basestring):
            images = self._set_single_tenant_image(image_name)
        elif isinstance(image_name, dict):
            images = self._set_multiple_tenant_image(image_name)
        else:
            images = self._set_image_stub()

        deploy_config['images'] = images
        return deploy_config

    def _set_single_tenant_image(self, image_name=None, os_id=None, boot=True):
        return [{
            "name": os_id or image_name,
            "boot": boot,
            "target": '/',
            "image_pull_url": self.get_url_for_image(
                image_name, self.deploy_driver),
        }]

    def _set_image_stub(self):
        return [{
            "name": "FAKE",
            "boot": True,
            "target": '/',
            "image_pull_url": "http://{0}:{1}/fake".format(
                self.network.address, CONF.stub_webserver_port),
        }]

    def _set_multiple_tenant_image(self, image_names):
        images = []
        for index, element in enumerate(image_names.items()):
            os_id, image_name = element
            boot = True if index == 0 else False
            image_data = self._set_single_tenant_image(image_name, os_id, boot)
            images.append(image_data[0])
        return images

    def get_url_for_image(self, image_name, source_type):
        if source_type == 'swift':
            return self._get_swift_tenant_image_url(image_name)
        elif source_type == 'rsync':
            return self._get_rsync_tenant_image_url(image_name)
        else:
            raise Exception("Unknown deploy_driver")

    def get_url_for_stub_image(self):
        return "http://{0}:{1}/fake".format(self.network.address,
                                            CONF.stub_webserver_port)

    def _get_swift_tenant_image_url(self, image_name):
        return (
            'http://{0}:{1}/tenant_images/{2}'.format(
                self.network.address, CONF.stub_webserver_port, image_name))

    def _get_rsync_tenant_image_url(self, image_name):
        url = "{0}::ironic_rsync/{1}/".format(self.network.address,
                                              image_name)
        if self.image_mount_point:
            # Image already mounted.
            if not os.path.exists(
                    os.path.join(self.image_mount_point, 'etc/passwd')):
                raise Exception('Previously mounted image no longer present')
            return url

        image_path = os.path.join(CONF.tenant_images_dir, image_name)
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
                            image_name, CONF.tenant_images_dir))
        return url

    def _save_provision_json_for_node(self, deploy_config):
        prov_json = json.dumps(deploy_config)
        path = os.path.join(self.node.workdir, "provision.json")
        with open(path, "w") as f:
            f.write(prov_json)
        return path

    def _teardown_webserver(self):
        LOG.info("Stopping stub web server ...")
        try:
            self.webserver.terminate()
            for i in range(0, 15):
                if self.webserver.poll() is not None:
                    LOG.info("Stub web server has stopped.")
                    break
                time.sleep(1)
            else:
                LOG.warning(
                    '15 seconds have passed since sending SIGTERM to the stub '
                    'web server. It is still alive. Send SIGKILL.')
                self.webserver.kill()
                self.webserver.wait()  # collect zombie
        except OSError as e:
            if e.errno == errno.ESRCH:
                return
            raise

    def _delete_workdir(self):
        LOG.info("Deleting workdir {0}".format(CONF.ramdisk_func_test_workdir))
        try:
            shutil.rmtree(CONF.ramdisk_func_test_workdir)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

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
            self.image_mount_point = None

    @classmethod
    def _load_config(cls, path):
        if cls._loaded_config == path:
            return

        LOG.debug('Load ramdisk-func-test configuration')
        args = {}
        if path:
            args['default_config_files'] = [path]
        conf.CONF([], project=conf.PROJECT_NAME, **args)

        # configure log level for libs we are using
        for channel, level in [
                ('paramiko', logging.WARN),
                ('ironic.openstack.common', logging.WARN)]:
            logger = logging.getLogger(channel)
            logger.setLevel(level)

        cls._loaded_config = path
