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
#             Installer for PVOutput RESTful Service extension
#
# Version: 0.3.0                                        Date: 1 February 2018
#
# Revision History
#   1 February 2018    v0.3.0
#       - initial implementation as an extension
#

import weewx

from distutils.version import StrictVersion
from setup import ExtensionInstaller

REQUIRED_VERSION = "3.7.0"
PVOUTPUT_VERSION = "0.3.0"

def loader():
    return PVOutputInstaller()

class PVOutputInstaller(ExtensionInstaller):
    def __init__(self):
        if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_VERSION):
            msg = "%s requires weeWX %s or greater, found %s" % ('PVOutput ' + PVOUTPUT_VERSION, 
                                                                 REQUIRED_VERSION, 
                                                                 weewx.__version__)
            raise weewx.UnsupportedFeature(msg)
        super(PVOutputInstaller, self).__init__(
            version=PVOUTPUT_VERSION,
            name='PVOutput',
            description='WeeWX RESTful service for uploading data to PVOutput.org.',
            author="Gary Roderick",
            author_email="gjroderick@gmail.com",
            restful_services=['user.pvoutput.StdPVOutput'],
            config={
                'StdRESTful': {
                    'PVOutput': {
                        'enable': 'false',
                        'system_id': 'ENTER_PVOUTPUT_SYSTEM_ID_HERE',
                        'api_key': 'ENTER_PVOUTPUT_API_KEY_HERE'
                    }
                }
            },
            files=[('bin/user', ['bin/user/pvoutput.py'])]
        )
