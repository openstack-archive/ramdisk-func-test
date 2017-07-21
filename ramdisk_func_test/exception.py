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


class RamDiskTestException(Exception):
    _msg = "An unknown error occured."

    def __init__(self, message=None, **kwargs):
        if not message:
            message = self._msg % kwargs
        super(RamDiskTestException, self).__init__(message)


class RsyncException(RamDiskTestException):
    _msg = "Rsync error occured."


class RsyncProcessNotFound(RsyncException):
    _msg = "No rsync process is running."


class RsyncConfigNotFound(RsyncException):
    _msg = "No rsyncd config file found at %(path)s."


class RsyncIronicSectionNotFound(RsyncException):
    _msg = 'There is no ironic section (%(section)s) in rsync config file.'


class ImageException(RamDiskTestException):
    _msg = "Image error occured."


class MountedImageNotPresent(ImageException):
    _msg = "Previously mounted image no longer present."


class ImageMountError(ImageException):
    _msg = "Mounting of image did not happen."


class ImageNotFound(ImageException):
    _msg = "There is no such file '%(image_name)s' in '%(directory)s'."


class UnknownDeployDriver(RamDiskTestException):
    _msg = "Unknown deploy_driver."


class TimeoutException(RamDiskTestException):
    _msg = "Timeout expired."


class NodeBootTimeout(TimeoutException):
    _msg = ("Waiting for node %(node_name)s to boot exceeded timeout "
            "%(timeout)ss.")


class NodeCallbackTimeout(TimeoutException):
    _msg = ("Waiting timeout %(timeout)ss for node %(node_name)s callback "
            "expired.")


class NonZeroCmdRetCode(RamDiskTestException):
    _msg = "Non-zero code: %(ret_code)s from cmd: %(cmd)s."


class VacantNetworkNotFound(RamDiskTestException):
    _msg = "Cannot find free libvirt net in %(head)s."


class PXELinuxNotFound(RamDiskTestException):
    _msg = "Network boot program files not found in any known location."
