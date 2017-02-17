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
#                     Installer for Aurora extension
#
# Version: 0.4.0                                        Date: 17 February 2017
#
# Revision History
#  17 February 2017    v0.4.0
#       - initial implementation (as an extension)
#

import weewx

from distutils.version import StrictVersion
from setup import ExtensionInstaller

REQUIRED_VERSION = "3.7.0"
AURORA_VERSION = "0.4.0"

def loader():
    return AuroraInstaller()

class AuroraInstaller(ExtensionInstaller):
    def __init__(self):
        if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_VERSION):
            msg = "%s requires weeWX %s or greater, found %s" % ('Aurora ' + AURORA_VERSION, 
                                                                 REQUIRED_VERSION, 
                                                                 weewx.__version__)
            raise weewx.UnsupportedFeature(msg)
        super(AuroraInstaller, self).__init__(
            version=AURORA_VERSION,
            name='Aurora',
            description='WeeWX support for recording solar PV power generation data from a Power One Aurora inverter.',
            author="Gary Roderick",
            author_email="gjroderick@gmail.com",
            restful_services=['user.pvoutput.StdPVOutput'],
            config={
                'Aurora': {
                    'model': 'replace_me',
                    'port': 'replace_me',
                    'address': '2',
                    'max_tries': '3',
                    'loop_interval': '10',
                    'use_inverter_time': 'false',
                    'driver': 'user.aurora',
                    'FieldMap': {
                        'string1Voltage': 'getStr1V',
                        'string1Current': 'getStr1C',
                        'string1Power': 'getStr1P',
                        'string2Voltage': 'getStr2V',
                        'string2Current': 'getStr2C',
                        'string2Power': 'getStr2P',
                        'gridVoltage': 'getGridV',
                        'gridCurrent': 'getGridC',
                        'gridPower': 'getGridP',
                        'gridFrequency': 'getFrequency',
                        'inverterTemp': 'getInverterT',
                        'boosterTemp': 'getBoosterT',
                        'bulkVoltage': 'getBulkV',
                        'isoResistance': 'getIsoR',
                        'bulkmidVoltage': 'getBulkMidV',
                        'bulkdcVoltage': 'getBulkDcV',
                        'leakdcCurrent': 'getLeakDcC',
                        'leakCurrent': 'getLeakC',
                        'griddcVoltage': 'getGridDcV',
                        'gridavgVoltage': 'getGridAvV',
                        'gridnVoltage': 'getPeakP',
                        'griddcFrequency': 'getGridDcFreq',
                        'dayEnergy': 'getDayEnergy'
                    }
                'Accumulator': {
                    'energy': {
                        'extractor': 'sum'
                    }
                }
            },
            files=[('bin/user', ['bin/user/aurora.py']),
                   ('bin/user', ['bin/user/aurora_schema.py']),
                   ('bin/user', ['bin/user/pvoutput.py'])]
        )
