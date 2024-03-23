"""
This program is free software; you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software
Foundation; either version 2 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

                     Installer for Aurora inverter driver

Version: 0.7.3                                      Date: 23 March 2024

Revision History
    23 March 2024       v0.7.3
        - bumped version number only
    23 January 2024     v0.7.2
        - bumped version number only
    22 January 2024     v0.7.1
        - change required WeeWX version to '5.0.0' to workaround
          version_compare() shortcomings
    5 January 2024      v0.7.0
        - now requires WeeWX v5.0.0 or later
        - Python v3.6 and earlier no longer supported
        - removed distutils dependency
        - supports python 3.13
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

from io import StringIO

# WeeWX imports
import weewx

from setup import ExtensionInstaller

REQUIRED_WEEWX_VERSION = "5.0.0"
AURORA_VERSION = "0.7.2"

aurora_config_str = """
[Aurora]
    # This section is for the Aurora inverter driver.

    # inverter model number
    model = replace_me
    
    # port to use to contact the inverter
    port = replace_me
    
    # the inverter address, default is 2
    address = 2
    
    # how many times to try to attempt the inverter before giving up
    max_tries = 3
    
    # how often to poll the inverter, default is every 20 seconds
    poll_interval = 20
    
    # the driver to use
    driver = user.aurora

[Accumulator]
    [[energy]]
        extractor = sum
"""

# construct our config dict
aurora_config = configobj.ConfigObj(StringIO(aurora_config_str))


def version_compare(v1, v2):
    """Basic 'distutils' and 'packaging' free version comparison.

    v1 and v2 are WeeWX version numbers in string format. Works for simple
    versions only, does not work for version numbers containing 'a', 'b' and
    'rc', eg '5.0.0rc1' ('a', 'b' and 'rc' versions will always be considered
    greater than the same non-'a' or 'b' or 'rc' version number,
    ie '5.0.0b2' > '5.0.0').

    Returns:
        0 if v1 and v2 are the same
        -1 if v1 is less than v2
        +1 if v1 is greater than v2
    """

    import itertools
    mash = itertools.zip_longest(v1.split('.'), v2.split('.'), fillvalue='0')
    for x1, x2 in mash:
        if x1 > x2:
            return 1
        if x1 < x2:
            return -1
    return 0


def loader():
    return AuroraInstaller()


class AuroraInstaller(ExtensionInstaller):
    def __init__(self):
        if version_compare(weewx.__version__, REQUIRED_WEEWX_VERSION) < 0:
            msg = "%s requires WeeWX %s or greater, found %s" % ('Aurora driver ' + AURORA_VERSION,
                                                                 REQUIRED_WEEWX_VERSION,
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
