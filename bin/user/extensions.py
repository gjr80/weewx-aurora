#
#    Copyright (c) 2009-2015 Tom Keffer <tkeffer@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

"""User extensions module

This module is imported from the main executable, so anything put here will be
executed before anything else happens. This makes it a good place to put user
extensions.
"""

import locale
# This will use the locale specified by the environment variable 'LANG'
# Other options are possible. See:
# http://docs.python.org/2/library/locale.html#locale.setlocale
locale.setlocale(locale.LC_ALL, '')


# ============================================================================
#                  Aurora units definitions and functions
# ============================================================================

import weewx.units

# create groups for frequency and resistance
weewx.units.USUnits['group_frequency'] = 'hertz'
weewx.units.MetricUnits['group_frequency'] = 'hertz'
weewx.units.MetricWXUnits['group_frequency'] = 'hertz'
weewx.units.USUnits['group_resistance'] = 'ohm'
weewx.units.MetricUnits['group_resistance'] = 'ohm'
weewx.units.MetricWXUnits['group_resistance'] = 'ohm'

# set default formats and labels for frequency and resistance
weewx.units.default_unit_format_dict['hertz'] = '%.1f'
weewx.units.default_unit_label_dict['hertz'] = ' ohm'
weewx.units.default_unit_format_dict['ohm'] = '%.1f'
weewx.units.default_unit_label_dict['ohm'] = ' ohm'

# define conversion functions for resistance
weewx.units.conversionDict['ohm'] = {'kohm': lambda x : x / 1000.0,
                                     'Mohm': lambda x : x / 1000000.0}
weewx.units.conversionDict['kohm'] = {'ohm': lambda x : x * 1000.0,
                                      'Mohm': lambda x : x / 1000.0}
weewx.units.conversionDict['Mohm'] = {'ohm': lambda x : x * 1000000.0,
                                      'kohm': lambda x : x * 1000.0}

# assign database fields to groups
weewx.units.obs_group_dict['string1Voltage'] = 'group_volt'
weewx.units.obs_group_dict['string1Current'] = 'group_amp'
weewx.units.obs_group_dict['string1Power'] = 'group_power'
weewx.units.obs_group_dict['string2Voltage'] = 'group_volt'
weewx.units.obs_group_dict['string2Current'] = 'group_amp'
weewx.units.obs_group_dict['string2Power'] = 'group_power'
weewx.units.obs_group_dict['gridVoltage'] = 'group_volt'
weewx.units.obs_group_dict['gridCurrent'] = 'group_amp'
weewx.units.obs_group_dict['gridPower'] = 'group_power'
weewx.units.obs_group_dict['gridFrequency'] = 'group_frequency'
weewx.units.obs_group_dict['efficiency'] = 'group_percent'
weewx.units.obs_group_dict['inverterTemp'] = 'group_temperature'
weewx.units.obs_group_dict['boosterTemp'] = 'group_temperature'
weewx.units.obs_group_dict['bulkVoltage'] = 'group_volt'
weewx.units.obs_group_dict['isoResistance'] = 'group_resistance'
weewx.units.obs_group_dict['in1Power'] = 'group_power'
weewx.units.obs_group_dict['in2Power'] = 'group_power'
weewx.units.obs_group_dict['bulkmidVoltage'] = 'group_volt'
weewx.units.obs_group_dict['bulkdcVoltage'] = 'group_volt'
weewx.units.obs_group_dict['leakdcCurrent'] = 'group_amp'
weewx.units.obs_group_dict['leakCurrent'] = 'group_amp'
weewx.units.obs_group_dict['griddcVoltage'] = 'group_volt'
weewx.units.obs_group_dict['gridavgVoltage'] = 'group_volt'
weewx.units.obs_group_dict['gridnVoltage'] = 'group_volt'
weewx.units.obs_group_dict['griddcFrequency'] = 'group_frequency'
weewx.units.obs_group_dict['energy'] = 'group_energy'
