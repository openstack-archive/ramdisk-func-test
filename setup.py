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

from setuptools import setup
from setuptools import find_packages


setup(
    name='ramdisk-func-test',
    version='0.1.0',
    packages=find_packages(),
    classifiers=[
        'Programming Language :: Python :: 2.7',
    ],
    entry_points={
        'console_scripts':
            'ramdisk-stub-webserver = ramdisk_func_test.webserver:main'
    },
    install_requires=[
        'stevedore>=1.3.0,<1.4.0', # Not used. Prevents pip dependency conflict.
        # This corresponds to openstack global-requirements.txt
        'oslo.config>=1.9.3,<1.10.0',
        'Jinja2==2.7.3',
        'paramiko',
        'pyyaml',
        'sh',
        'lxml>=2.3'
    ],
    package_data={
        'ramdisk_func_test.webserver': ['data/*']
    },
    url='',
    license='Apache License, Version 2.0',
    author='',
    author_email='openstack-dev@lists.openstack.org',
    description='A functional testing framework used for ramdisk-based '
                'deployment tools'
)
