#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT 
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
#                     Installer for Aurora inverter driver
#
# Version: 0.5.0                                    Date: 31 January 2018
#
# Revision History
#  31 January 2018  v0.5.0
#       - initial implementation as an extension
#

import weewx

from distutils.version import StrictVersion
from setup import ExtensionInstaller

REQUIRED_VERSION = "3.7.0"
AURORA_VERSION = "0.5.0"

def loader():
    return AuroraInstaller()

class AuroraInstaller(ExtensionInstaller):
    def __init__(self):
        if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_VERSION):
            msg = "%s requires weeWX %s or greater, found %s" % ('Aurora driver ' + AURORA_VERSION, 
                                                                 REQUIRED_VERSION, 
                                                                 weewx.__version__)
            raise weewx.UnsupportedFeature(msg)
        super(AuroraInstaller, self).__init__(
            version=AURORA_VERSION,
            name='aurora',
            description='weeWX driver for Power One Aurora inverters.',
            author="Gary Roderick",
            author_email="gjroderick@gmail.com",
            files=[('bin/user', ['bin/user/aurora.py', 'bin/user/aurora_schema.py'])]
        )
