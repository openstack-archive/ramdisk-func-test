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

import collections
import logging
import unittest

from ramdisk_func_test import conf
from ramdisk_func_test import environment


__all__ = ['TestCaseMixin']

LOG = logging.getLogger(__name__)


class TestCaseMixin(unittest.TestCase):
    _rft_template_path = []
    env = None

    @classmethod
    def setUpClass(cls):
        template_path = []
        template_uniq = set()
        for member in cls.__mro__:
            try:
                path = member._rft_template_path
            except AttributeError:
                continue

            if isinstance(path, basestring):
                path = [path]
            elif isinstance(path, collections.Sequence):
                pass
            else:
                path = [path]

            uniq_path = set(path) - template_uniq
            template_uniq.update(uniq_path)
            template_path.extend(x for x in path if x in uniq_path)

        cls.env = environment.Environment(template_path)
        cls.env.setupclass()

        super(TestCaseMixin, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.env.teardownclass()
        super(TestCaseMixin, cls).tearDownClass()

    def tearDown(self):
        self.env.teardown()
        super(TestCaseMixin, self).tearDown()


def _init():
    LOG.debug('Load ramdisk-func-test configuration')
    conf.CONF(
        [], project=conf.PROJECT_NAME, default_config_files=[conf.CONF_FILE])

    # configure log level for libs we are using
    for channel, level in [
            ('paramiko', logging.WARN),
            ('ironic.openstack.common', logging.WARN)]:
        logger = logging.getLogger(channel)
        logger.setLevel(level)


_init()
