"""
This program is free software; you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software
Foundation; either version 2 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

                     Installer for Aurora inverter driver

Version: 0.7.0                                      Date: 28 November 2023

Revision History
    12 March 2020       v0.6.1
        - bumped version number only
    9 March 2020        v0.6.0
        - minor formatting changes
    22 December 2018    v0.5.2
        - bumped version number only
    3 February 2018     v0.5.1
        - bumped version number only
    31 January 2018     v0.5.0
        - initial implementation as an extension
"""

# python imports
import configobj

from distutils.version import StrictVersion
from io import StringIO

# WeeWX imports
import weewx

from setup import ExtensionInstaller

REQUIRED_VERSION = "5.0.0b1"
AURORA_VERSION = "0.7.0a1"

aurora_config_str = """
[Aurora]
    # This section is for the Ecowitt Gateway driver.

    # inverter model number
    model = replace_me
    
    # port to use to contact the inverter
    port = replace_me
    
    # the inverter address, default is 2
    address = 2
    
    # how many times to try to attempt the inverter before giving up
    max_tries = 3
    
    # how often to poll the inverter, default is every 20 seconds
    loop_interval = 10
    
    # the driver to use
    driver = user.aurora

[Accumulator]
    [[energy]]
        extractor = sum
"""

# construct our config dict
aurora_config = configobj.ConfigObj(StringIO(aurora_config_str))

def loader():
    return AuroraInstaller()


class AuroraInstaller(ExtensionInstaller):
    def __init__(self):
        if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_VERSION):
            msg = "%s requires WeeWX %s or greater, found %s" % ('Aurora driver ' + AURORA_VERSION,
                                                                 REQUIRED_VERSION,
                                                                 weewx.__version__)
            raise weewx.UnsupportedFeature(msg)
        super(AuroraInstaller, self).__init__(
            version=AURORA_VERSION,
            name='aurora',
            description='WeeWX driver for Power One Aurora inverters.',
            author="Gary Roderick",
            author_email="gjroderick@gmail.com",
            files=[('bin/user', ['bin/user/aurora.py', 'bin/user/aurora_schema.py'])],
            config=aurora_config
        )
