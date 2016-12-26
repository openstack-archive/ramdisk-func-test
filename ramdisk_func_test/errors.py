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


class BaseError(Exception):
    _msg = "An unknown error occured."

    def __init__(self, message=None, **kwargs):
        if not message:
            message = self._msg % kwargs
        super(BaseError, self).__init__(message)


class RsyncError(BaseError):
    _msg = "Rsync error occured."


class RsyncProcessNotFound(RsyncError):
    _msg = "No rsync process is running."


class RsyncConfigNotFound(RsyncError):
    _msg = "No rsyncd config file found at %(path)s."


class RsyncIronicSectionNotFound(RsyncError):
    _msg = 'There is no ironic section (%(section)s) in rsync config file.'


class ImageError(BaseError):
    _msg = "Image error occured."


class MountedImageNotPresent(ImageError):
    _msg = "Previously mounted image no longer present."


class ImageMountError(ImageError):
    _msg = "Mounting of image did not happen."


class ImageNotFound(ImageError):
    _msg = "There is no such file '%(image_name)s' in '%(directory)s'."


class UnknownDeployDriver(BaseError):
    _msg = "Unknown deploy_driver."


class TimeoutException(BaseError):
    _msg = "Timeout expired."


class NetServiceStartTimeout(TimeoutException):
    _msg = ("Timeout %(timeout)ss for waiting for IP %(ip)s port %(port)s "
            "to start expired.")


class NodeCallbackTimeout(TimeoutException):
    _msg = ("Waiting timeout %(timeout)ss for node %(node_name)s callback "
            "expired.")


class NonZeroCmdRetCode(BaseError):
    _msg = "Non-zero code: %(ret_code)s from cmd: %(cmd)s."


class VacantNetworkNotFound(BaseError):
    _msg = "Cannot find free libvirt net in %(head)s."


class PXELinuxNotFound(BaseError):
    _msg = "No pxelinux.0 found in provided paths."
