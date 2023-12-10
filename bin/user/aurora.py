"""
aurora.py

A WeeWX driver for Power One Aurora inverters.

Copyright (C) 2016-2023 Gary Roderick                  gjroderick<at>gmail.com

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program.  If not, see https://www.gnu.org/licenses/.

Version: 0.7.0a1                                      Date: 23 November 2023

Revision History
    23 November 2023    v0.7.0
        - now WeeWX v5 compatible
        - python v3.6 and earlier no longer supported
        - removed option to use inverter time as loop packet dateTime field
        - replaced the deprecated optparse module with argparse
        - add bolding to usage instructions when driver is run directly
    12 March 2020       v0.6.1
        - fix issue with structure of inverter commands with a payload
    9 March 2020        v0.6.0
        - now WeeWX 4.0 python2/3 compatible
    22 December 2018    v0.5.2
        - implemented port cycling after 2 failures to obtain a response from
          the inverter
    3 February 2018     v0.5.1
        - reworked install comments
    31 January 2018     v0.5.0
        - implemented port cycling to reset serial port after occasional CRC
          error
        - fixed issue where inverter date-time was never added to the raw loop
          packet so could never be used as the resulting loop packet timestamp
        - added confeditor_loader() function
        - revised logging output format to be more consistent
        - added more arguments to AuroraInverter class
        - AuroraDriver send_cmd_with_crc() method now accepts additional
          arguments
        - refactored calculate_energy()
        - units, groups, conversions and formatting defaults are now defined in
          the driver rather than via additions to extensions.py
        - renamed driver config option [[FieldMap]] to [[sensor_map]] and
          implemented a default sensor map
    9 February 2017     v0.4.0
        - implemented setTime() method
    7 February 2017     v0.3.0
        - hex inverter response streams now printed as space separated bytes
        - fixed various typos
        - some test screen error output now syslog'ed
        - genLoopPackets() now produces 'None' packets when the inverter is off
          line
        - converted a number of class properties that were set on __init__ to
          @property that are queried when required
        - inverter state request response now decoded
        - added --monitor action to __main__
        - improved delay loop in genLoopPackets()
        - added usage instructions
    31 January 2017     v0.2.0
        - no longer use the aurora application for interrogating the inverter,
          communication with the inverter is now performed directly via the
          AuroraInverter class
    1 January 2017      v0.1.0
        - initial release


The driver communicates directly with the inverter without the need for any
other application. The driver produces loop packets that WeeWX then aggregates
into archive records that, when used with a custom database schema, allow WeeWX
to store and report inverter data.

To use:

1.  Copy this file to /home/weewx/bin/user.

2.  Add the following section to weewx.conf setting model, port and address
options as required:

##############################################################################
[Aurora]
    # This section is for the Power One Aurora series of inverters.

    # The inverter model, e.g., Aurora PVI-6000, Aurora PVI-5000
    model = INSERT_MODEL_HERE

    # Serial port such as /dev/ttyS0, /dev/ttyUSB0, or /dev/cua0
    port = /dev/ttyUSB0

    # inverter address, usually 2
    address = 2

    # The driver to use:
    driver = user.aurora

##############################################################################

3.  Add the following section to weewx.conf:

##############################################################################
[Accumulator]
    [[energy]]
        extractor = sum

##############################################################################

4   Edit weewx.conf as follows:

    - under [Station] set station_type = Aurora
    - under [StdArchive] ensure record_generation = software

5.  Stop then start WeeWX.


Standalone testing

This driver can be run in standalone mode without the overheads of the WeeWX
engine and services. The available options can be displayed using:

    $ PYTHONPATH=/home/weewx/bin python /home/weewx/bin/user/aurora.py --help

The options can be selected using:

    $ PYTHONPATH=/home/weewx/bin python /home/weewx/bin/user/aurora.py --option

    where option is one of the options listed by --help
"""


# Python imports
import logging
import serial
import struct
import time

# WeeWX imports
import weeutil
import weewx.drivers
import weewx.units

# get a logger object
log = logging.getLogger(__name__)

# our name and version number
DRIVER_NAME = 'Aurora'
DRIVER_VERSION = '0.7.0a1'


def define_units():
    """Define unit groups, formats and conversions used by the driver.

    Define unit groups, conversions and default formats for units used by the
    aurora driver. This could be done in user/extensions.py or the driver,
    user/extensions.py will make the groups, conversions and formats available
    for all drivers and services but requires manual editing of the file by the
    user. Inclusion in the driver removes the need for the user to edit
    extensions.py, but means the groups, conversions and formats are only
    defined when the aurora driver is being used. Given the specialised nature
    of the groups, conversions and formats the latter is an acceptable
    approach. In any case there is nothing preventing the user manually adding
    these entries to extensions.py.
    """

    # create group for resistance
    weewx.units.USUnits['group_resistance'] = 'ohm'
    weewx.units.MetricUnits['group_resistance'] = 'ohm'
    weewx.units.MetricWXUnits['group_resistance'] = 'ohm'

    # set default formats and labels for resistance
    weewx.units.default_unit_format_dict['ohm'] = '%.1f'
    weewx.units.default_unit_label_dict['ohm'] = u' Ω'
    weewx.units.default_unit_format_dict['kohm'] = '%.1f'
    weewx.units.default_unit_label_dict['kohm'] = u' kΩ'
    weewx.units.default_unit_format_dict['Mohm'] = '%.1f'
    weewx.units.default_unit_label_dict['Mohm'] = u' MΩ'

    # define conversion functions for resistance
    weewx.units.conversionDict['ohm'] = {'kohm': lambda x: x / 1000.0,
                                         'Mohm': lambda x: x / 1000000.0}
    weewx.units.conversionDict['kohm'] = {'ohm': lambda x: x * 1000.0,
                                          'Mohm': lambda x: x / 1000.0}
    weewx.units.conversionDict['Mohm'] = {'ohm': lambda x: x * 1000000.0,
                                          'kohm': lambda x: x * 1000.0}

    # set default formats and labels for kilo and megawatt hours
    weewx.units.default_unit_format_dict['kilo_watt_hour'] = '%.1f'
    weewx.units.default_unit_label_dict['kilo_watt_hour'] = ' kWh'
    weewx.units.default_unit_format_dict['mega_watt_hour'] = '%.1f'
    weewx.units.default_unit_label_dict['mega_watt_hour'] = ' MWh'

    # define conversion functions for energy
    weewx.units.conversionDict['watt_hour'] = {'kilo_watt_hour': lambda x: x / 1000.0,
                                               'mega_watt_hour': lambda x: x / 1000000.0}
    weewx.units.conversionDict['kilo_watt_hour'] = {'watt_hour': lambda x: x * 1000.0,
                                                    'mega_watt_hour': lambda x: x / 1000.0}
    weewx.units.conversionDict['mega_watt_hour'] = {'watt_hour': lambda x: x * 1000000.0,
                                                    'kilo_watt_hour': lambda x: x * 1000.0}

    # set default formats and labels for kilo and mega watts
    weewx.units.default_unit_format_dict['kilo_watt'] = '%.1f'
    weewx.units.default_unit_label_dict['kilo_watt'] = ' kW'
    weewx.units.default_unit_format_dict['mega_watt'] = '%.1f'
    weewx.units.default_unit_label_dict['mega_watt'] = ' MW'

    # define conversion functions for energy
    weewx.units.conversionDict['watt'] = {'kilo_watt': lambda x: x / 1000.0,
                                          'mega_watt': lambda x: x / 1000000.0}
    weewx.units.conversionDict['kilo_watt'] = {'watt': lambda x: x * 1000.0,
                                               'mega_watt': lambda x: x / 1000.0}
    weewx.units.conversionDict['mega_watt'] = {'watt': lambda x: x * 1000000.0,
                                               'kilo_watt': lambda x: x * 1000.0}

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


# ============================================================================
#                 Aurora Loader/Configurator/Editor methods
# ============================================================================

def loader(config_dict, engine):
    """Loader used to load the driver."""

    # first define unit groups, conversions and default formats for units used
    # by the aurora driver
    define_units()
    # return an AuroraDriver object
    return AuroraDriver(config_dict[DRIVER_NAME])


def configurator_loader(config_dict):
    """Configurator used by weectl device."""

    return AuroraConfigurator()


def confeditor_loader():

    return AuroraConfEditor()


# ============================================================================
#                           Aurora Error classes
# ============================================================================

class DataFormatError(Exception):
    """Exception raised when an error is thrown when processing data being sent
       to or from the inverter."""


# ============================================================================
#                            class AuroraDriver
# ============================================================================

class AuroraDriver(weewx.drivers.AbstractDevice):
    """Class representing connection to Aurora inverter."""

    # default sensor map, format:
    #   loop packet field: raw data field
    DEFAULT_SENSOR_MAP = {'inverterDateTime': 'inverterDateTime',
                          'string1Voltage': 'str1V',
                          'string1Current': 'str1C',
                          'string1Power': 'str1P',
                          'string2Voltage': 'str2V',
                          'string2Current': 'str2C',
                          'string2Power': 'str2P',
                          'gridVoltage': 'gridV',
                          'gridCurrent': 'gridC',
                          'gridPower': 'gridP',
                          'gridFrequency': 'frequency',
                          'inverterTemp': 'inverterT',
                          'boosterTemp': 'boosterT',
                          'bulkVoltage': 'bulkV',
                          'isoResistance': 'isoR',
                          'bulkmidVoltage': 'bulkMidV',
                          'bulkdcVoltage': 'bulkDcV',
                          'leakdcCurrent': 'leakDcC',
                          'leakCurrent': 'leakC',
                          'griddcVoltage': 'gridDcV',
                          'gridavgVoltage': 'gridAvV',
                          'gridnVoltage': 'gridNV',
                          'griddcFrequency': 'gridDcFreq',
                          'dayEnergy': 'dayEnergy',
                          'weekEnergy': 'weekEnergy',
                          'monthEnergy': 'monthEnergy',
                          'yearEnergy': 'yearEnergy',
                          'totalEnergy': 'totalEnergy',
                          'partialEnergy': 'partialEnergy'
                          }

    # lookup table used to determine inverter command to be used for each raw
    # data packet field
    SENSOR_LOOKUP = {'inverterDateTime': 'getTimeDate',
                     'str1V': 'getStr1V',
                     'str1C': 'getStr1C',
                     'str1P': 'getStr1P',
                     'str2V': 'getStr2V',
                     'str2C': 'getStr2C',
                     'str2P': 'getStr2P',
                     'gridV': 'getGridV',
                     'gridC': 'getGridC',
                     'gridP': 'getGridP',
                     'frequency': 'getFrequency',
                     'inverterT': 'getInverterT',
                     'boosterT': 'getBoosterT',
                     'bulkV': 'getBulkV',
                     'isoR': 'getIsoR',
                     'bulkMidV': 'getBulkMidV',
                     'bulkDcV': 'getBulkDcV',
                     'leakDcC': 'getLeakDcC',
                     'leakC': 'getLeakC',
                     'gridDcV': 'getGridDcV',
                     'gridAvV': 'getGridAvV',
                     'gridNV': 'getGridNV',
                     'gridDcFreq': 'getGridDcFreq',
                     'dayEnergy': 'getDayEnergy',
                     'weekEnergy': 'getWeekEnergy',
                     'monthEnergy': 'getMonthEnergy',
                     'yearEnergy': 'getYearEnergy',
                     'totalEnergy': 'getTotalEnergy',
                     'partialEnergy': 'getPartialEnergy'
                     }
    # transmission state code map
    TRANSMISSION = {0: 'Everything is OK',
                    51: 'Command is not implemented',
                    52: 'Variable does not exist',
                    53: 'Variable value is out of range',
                    54: 'EEprom not accessible',
                    55: 'Not Toggled Service Mode',
                    56: 'Can not send the command to internal micro',
                    57: 'Command not Executed',
                    58: 'The variable is not available, retry'
                    }

    # inverter system module state code maps

    # global state
    GLOBAL = {0: 'Sending Parameters',
              1: 'Wait Sun/Grid',
              2: 'Checking Grid',
              3: 'Measuring Riso',
              4: 'DcDc Start',
              5: 'Inverter Start',
              6: 'Run',
              7: 'Recovery',
              8: 'Pause',
              9: 'Ground Fault',
              10: 'OTH Fault',
              11: 'Address Setting',
              12: 'Self Test',
              13: 'Self Test Fail',
              14: 'Sensor Test + Meas.Riso',
              15: 'Leak Fault',
              16: 'Waiting for manual reset ',
              17: 'Internal Error E026',
              18: 'Internal Error E027',
              19: 'Internal Error E028',
              20: 'Internal Error E029',
              21: 'Internal Error E030',
              22: 'Sending Wind Table',
              23: 'Failed Sending table',
              24: 'UTH Fault',
              25: 'Remote OFF',
              26: 'Interlock Fail',
              27: 'Executing Autotest',
              30: 'Waiting Sun',
              31: 'Temperature Fault',
              32: 'Fan Stacked',
              33: 'Int. Com. Fault',
              34: 'Slave Insertion',
              35: 'DC Switch Open',
              36: 'TRAS Switch Open',
              37: 'MASTER Exclusion',
              38: 'Auto Exclusion ',
              98: 'Erasing Internal EEprom',
              99: 'Erasing External EEprom',
              100: 'Counting EEprom',
              101: 'Freeze'
              }

    # inverter state
    INVERTER = {0: 'Stand By',
                1: 'Checking Grid',
                2: 'Run',
                3: 'Bulk OV',
                4: 'Out OC',
                5: 'IGBT Sat',
                6: 'Bulk UV',
                7: 'Degauss Error',
                8: 'No Parameters',
                9: 'Bulk Low',
                10: 'Grid OV',
                11: 'Communication Error',
                12: 'Degaussing',
                13: 'Starting',
                14: 'Bulk Cap Fail',
                15: 'Leak Fail',
                16: 'DcDc Fail',
                17: 'Ileak Sensor Fail',
                18: 'SelfTest: relay inverter',
                19: 'SelfTest: wait for sensor test',
                20: 'SelfTest: test relay DcDc + sensor',
                21: 'SelfTest: relay inverter fail',
                22: 'SelfTest timeout fail',
                23: 'SelfTest: relay DcDc fail',
                24: 'Self Test 1',
                25: 'Waiting self test start',
                26: 'Dc Injection',
                27: 'Self Test 2',
                28: 'Self Test 3',
                29: 'Self Test 4',
                30: 'Internal Error',
                31: 'Internal Error',
                40: 'Forbidden State',
                41: 'Input UC',
                42: 'Zero Power',
                43: 'Grid Not Present',
                44: 'Waiting Start',
                45: 'MPPT',
                46: 'Grid Fail',
                47: 'Input OC'
                }

    # DC/DC channel states
    DCDC = {0: 'DcDc OFF',
            1: 'Ramp Start',
            2: 'MPPT',
            3: 'Not Used',
            4: 'Input OC',
            5: 'Input UV',
            6: 'Input OV',
            7: 'Input Low',
            8: 'No Parameters',
            9: 'Bulk OV',
            10: 'Communication Error',
            11: 'Ramp Fail',
            12: 'Internal Error',
            13: 'Input mode Error',
            14: 'Ground Fault',
            15: 'Inverter Fail',
            16: 'DcDc IGBT Sat',
            17: 'DcDc ILEAK Fail',
            18: 'DcDc Grid Fail',
            19: 'DcDc Comm Error'
            }

    # alarm states
    ALARM = {0:  {'description': 'No Alarm',          'code': None},
             1:  {'description': 'Sun Low',           'code': 'W001'},
             2:  {'description': 'Input OC',          'code': 'E001'},
             3:  {'description': 'Input UV',          'code': 'W002'},
             4:  {'description': 'Input OV',          'code': 'E002'},
             5:  {'description': 'Sun Low',           'code': 'W001'},
             6:  {'description': 'No Parameters',     'code': 'E003'},
             7:  {'description': 'Bulk OV',           'code': 'E004'},
             8:  {'description': 'Comm.Error',        'code': 'E005'},
             9:  {'description': 'Output OC',         'code': 'E006'},
             10: {'description': 'IGBT Sat',          'code': 'E007'},
             11: {'description': 'Bulk UV',           'code': 'W011'},
             12: {'description': 'Internal error',    'code': 'E009'},
             13: {'description': 'Grid Fail',         'code': 'W003'},
             14: {'description': 'Bulk Low',          'code': 'E010'},
             15: {'description': 'Ramp Fail',         'code': 'E011'},
             16: {'description': 'Dc/Dc Fail',        'code': 'E012'},
             17: {'description': 'Wrong Mode',        'code': 'E013'},
             18: {'description': 'Ground Fault',      'code': '---'},
             19: {'description': 'Over Temp.',        'code': 'E014'},
             20: {'description': 'Bulk Cap Fail',     'code': 'E015'},
             21: {'description': 'Inverter Fail',     'code': 'E016'},
             22: {'description': 'Start Timeout',     'code': 'E017'},
             23: {'description': 'Ground Fault',      'code': 'E018'},
             24: {'description': 'Degauss error',     'code': '---'},
             25: {'description': 'Ileak sens.fail',   'code': 'E019'},
             26: {'description': 'DcDc Fail',         'code': 'E012'},
             27: {'description': 'Self Test Error 1', 'code': 'E020'},
             28: {'description': 'Self Test Error 2', 'code': 'E021'},
             29: {'description': 'Self Test Error 3', 'code': 'E019'},
             30: {'description': 'Self Test Error 4', 'code': 'E022'},
             31: {'description': 'DC inj error',      'code': 'E023'},
             32: {'description': 'Grid OV',           'code': 'W004'},
             33: {'description': 'Grid UV',           'code': 'W005'},
             34: {'description': 'Grid OF',           'code': 'W006'},
             35: {'description': 'Grid UF',           'code': 'W007'},
             36: {'description': 'Z grid Hi',         'code': 'W008'},
             37: {'description': 'Internal error',    'code': 'E024'},
             38: {'description': 'Riso Low',          'code': 'E025'},
             39: {'description': 'Vref Error',        'code': 'E026'},
             40: {'description': 'Error Meas V',      'code': 'E027'},
             41: {'description': 'Error Meas F',      'code': 'E028'},
             42: {'description': 'Error Meas Z',      'code': 'E029'},
             43: {'description': 'Error Meas Ileak',  'code': 'E030'},
             44: {'description': 'Error Read V',      'code': 'E031'},
             45: {'description': 'Error Read I',      'code': 'E032'},
             46: {'description': 'Table fail',        'code': 'W009'},
             47: {'description': 'Fan Fail',          'code': 'W010'},
             48: {'description': 'UTH',               'code': 'E033'},
             49: {'description': 'Interlock fail',    'code': 'E034'},
             50: {'description': 'Remote Off',        'code': 'E035'},
             51: {'description': 'Vout Avg error',    'code': 'E036'},
             52: {'description': 'Battery low',       'code': 'W012'},
             53: {'description': 'Clk fail',          'code': 'W013'},
             54: {'description': 'Input UC',          'code': 'E037'},
             55: {'description': 'Zero Power',        'code': 'W014'},
             56: {'description': 'Fan Stuck',         'code': 'E038'},
             57: {'description': 'DC Switch Open',    'code': 'E039'},
             58: {'description': 'Tras Switch Open',  'code': 'E040'},
             59: {'description': 'AC Switch Open',    'code': 'E041'},
             60: {'description': 'Bulk UV',           'code': 'E042'},
             61: {'description': 'Autoexclusion',     'code': 'E043'},
             62: {'description': 'Grid df/dt',        'code': 'W015'},
             63: {'description': 'Den switch Open',   'code': 'W016'},
             64: {'description': 'Jbox fail',         'code': 'W017'}
             }

    def __init__(self, **inverter_dict):
        """Initialise an object of type AuroraDriver."""

        # model
        self.model = inverter_dict.get('model', 'Aurora')
        log.info('%s driver version is %s' % (self.model, DRIVER_VERSION))
        # serial comms options
        try:
            port = inverter_dict.get('port')
        except KeyError:
            raise Exception("Required parameter 'port' was not specified.")
        baudrate = int(inverter_dict.get('baudrate', 19200))
        timeout = float(inverter_dict.get('timeout', 2.0))
        wait_before_retry = float(inverter_dict.get('wait_before_retry', 1.0))
        command_delay = float(inverter_dict.get('command_delay', 0.05))
        log.info('   using port %s baudrate %d timeout %d' % (port, baudrate, timeout))
        log.info('   wait_before_retry %d command_delay %.2f' % (wait_before_retry,
                                                                 command_delay))
        # driver options
        self.max_command_tries = int(inverter_dict.get('max_command_tries', 3))
        self.polling_interval = int(inverter_dict.get('loop_interval', 10))
        self.address = int(inverter_dict.get('address', 2))
        self.max_loop_tries = int(inverter_dict.get('max_loop_tries', 3))
        log.info('   inverter address %d will be polled every %d seconds' % (self.address,
                                                                             self.polling_interval))
        log.info('   max_command_tries %d max_loop_tries %d' % (self.max_command_tries,
                                                                self.max_loop_tries))
        # get an AuroraInverter object
        self.inverter = AuroraInverter(port,
                                       baudrate=baudrate,
                                       timeout=timeout,
                                       wait_before_retry=wait_before_retry,
                                       command_delay=command_delay)
        # open up the connection to the inverter
        self.openPort()
        # is the inverter running ie global state '6' (Run)
        self.running = self.do_cmd('getState').global_state == 6
        # initialise last energy value
        self.last_energy = None
        # get the sensor map
        self.sensor_map = inverter_dict.get('sensor_map',
                                            AuroraDriver.DEFAULT_SENSOR_MAP)
        log.info('sensor_map=%s' % (self.sensor_map, ))
        # build a 'none' packet to use when the inverter is offline
        self.none_packet = {}
        for field in AuroraDriver.SENSOR_LOOKUP:
            self.none_packet[field] = None

    def openPort(self):
        """Open the connection to the inverter."""

        self.inverter.open_port()

    def closePort(self):
        """Close the connection to the inverter."""

        self.inverter.close_port()

    def genLoopPackets(self):
        """Generator function that returns 'loop' packets.

        Poll the inverter every self.polling_interval seconds and generate a
        loop packet. Sleep between loop packets.
        """

        while int(time.time()) % self.polling_interval != 0:
            time.sleep(0.2)
        for count in range(self.max_loop_tries):
            while True:
                try:
                    # get the current time as timestamp
                    _ts = int(time.time())
                    # poll the inverter and obtain raw data
                    if weewx.debug >= 2:
                        log.debug("genLoopPackets: polling inverter for data")
                    if self.running:
                        raw_packet = self.get_raw_packet()
                    else:
                        self.running = self.do_cmd('getState').global_state == 6
                        if self.running:
                            raw_packet = self.get_raw_packet()
                        else:
                            raw_packet = self.none_packet
                    if weewx.debug >= 2:
                        log.debug("genLoopPackets: received raw data packet: %s" % (raw_packet, ))
                    # process raw data and return a dict that can be used as a
                    # LOOP packet
                    packet = self.process_raw_packet(raw_packet)
                    # add in/set fields that require special consideration
                    if packet:
                        # dateTime
                        packet['dateTime'] = _ts

                        # usUnits - set to METRIC
                        packet['usUnits'] = weewx.METRIC

                        # dayEnergy is cumulative by day but we need
                        # incremental values so we need to calculate it based
                        # on the last cumulative value
                        if 'dayEnergy' in packet:
                            packet['energy'] = self.calculate_energy(packet['dayEnergy'],
                                                                     self.last_energy)
                            self.last_energy = packet['dayEnergy']
                        else:
                            packet['energy'] = None
                            self.last_energy = None

                        if weewx.debug >= 2:
                            log.debug("genLoopPackets: received loop packet: %s" % (packet, ))
                        yield packet
                    # wait until it's time to poll again
                    if weewx.debug >= 2:
                        log.debug("genLoopPackets: sleeping")
                    while time.time() < _ts + self.polling_interval:
                        time.sleep(0.2)
                except IOError as e:
                    log.error("LOOP try #%d; error: %s" % (count + 1, e))
                    break
        log.error("LOOP max tries (%d) exceeded." % self.max_loop_tries)
        raise weewx.RetriesExceeded("Max tries exceeded while getting LOOP data.")

    def get_raw_packet(self):
        """Get the raw loop data from the inverter."""

        _packet = {}
        # iterate over each reading we need to get
        for field, command in AuroraDriver.SENSOR_LOOKUP.items():
            # get the reading
            _response = self.do_cmd(command)
            # If the inverter is running set the running property and save the
            # data. If the inverter is asleep set the running property only,
            # there will be no data.
            if _response.global_state == 6:
                # inverter is running
                self.running = True
                _packet[field] = _response.data
            else:
                # inverter is asleep
                self.running = False
                break
        return _packet

    def process_raw_packet(self, raw_packet):
        """Create a limited WeeWX loop packet from a raw loop data.

        Input:
            raw_packet: A dict holding unmapped raw data retrieved from the
                        inverter.

        Returns:
            A limited WeeWX loop packet of mapped raw inverter data.
        """

        # map raw packet readings to loop packet fields using the field map
        _packet = {}
        for dest, src in self.sensor_map.items():
            if src in raw_packet:
                _packet[dest] = raw_packet[src]
                # apply any special processing that may be required
                if src == 'getIsoR':
                    # isoR is reported in Mohms, we want ohms
                    try:
                        _packet[dest] *= 1000000.0
                    except TypeError:
                        # field is not numeric so leave it
                        pass
        return _packet

    def do_cmd(self, command, payload=None, globall=0):
        """Send a command to the inverter and return the decoded response.

        Inputs:
            command: One of the commands from the command vocabulary of the
                     AuroraInverter object, AuroraInverter.commands. String.
            global_mode: Global (global_mode=1) or Module (global_mode=0) measurements.

        Returns:
            Response Tuple with the inverters response to the command. If no
            response or response could not be decoded then (None, None, None)
            is returned.
        """

        try:
            return self.inverter.send_cmd_with_crc(command,
                                                   payload=payload,
                                                   globall=globall,
                                                   address=self.address,
                                                   max_tries=self.max_command_tries)
        except weewx.WeeWxIOError:
            return ResponseTuple(None, None, None)

    def getTime(self):
        """Get inverter system time and return as an epoch timestamp.

        During startup WeeWX uses the 'console' time if available. The way the
        driver tells WeeWX the 'console' time is not available is by raising a
        NotImplementedError error when getTime is called. This is what is
        normally done for stations that do not keep track of time. In the case
        of the Aurora inverter, when it is asleep we cannot get the time so in
        that case raise a NotImplementedError, if the inverter is awake then
        return the time.

        Returns:
            An epoch timestamp representing the inverter date-time.
        """

        # get the ts
        _time_ts = self.do_cmd('getTimeDate').data
        if _time_ts is None:
            # if it's None the inverter most likely asleep, though there could
            # be a communication problem, assume the former and raise a
            # NotImplementedError
            raise NotImplementedError("getTime: Could not contact inverter, it may be asleep")
        else:
            #  otherwise return the time
            return _time_ts

    def setTime(self):
        """Set inverter system time.

        The WeeWX StdTimeSync service will periodically check the inverters
        internal clock and use setTime() to adjust the inverters clock if
        required. As the inverters clock cannot be read or set when the
        inverter is asleep, setTime() will take one of two actions. If the
        inverter is asleep then a NotImplementedError is raised, if the
        inverter is awake then the time is set.
        """

        # check if the inverter is online, we will get None if the inverter
        # cannot be contacted
        _time_ts = self.do_cmd('getTimeDate').data
        # if it's None the inverter most likely asleep, though there could
        # be a communication problem, assume the former and raise a
        # NotImplementedError
        if _time_ts is None:
            raise NotImplementedError("setTime: Could not contact inverter, it may be asleep")
        else:
            # get the current system time, offset by 2 seconds to allow for
            # rounding (0.5) and the delay in the command being issued and
            # acted on by the inverter (1.5)
            _ts = int(time.time() + 2)
            # the inverters epoch is midnight 1 January 2000 so offset our
            # epoch timestamp
            _inv_ts = _ts - 946648800
            # pack the value into a Struct object so we can deal with the bytes
            s = struct.Struct('>i')
            _payload = s.pack(_inv_ts)
            # send the command and get the response
            _response = self.do_cmd('setTimeDate', payload=_payload)
            # The inverter response to a successful time set is to return
            # 8 bytes including transmission state and global state. The
            # remainder of the 8 bytes is CRC (last 2 bytes) and 0x00 for
            # remaining bytes. We will get the response as a Response Tuple
            # where we can check the transmission state and global state.
            if _response.transmission_state == 0 and _response.global_state == 6:
                # good response so log it
                log.info("Inverter time set")
            else:
                # something went wrong; it's not fatal, but we need to log the
                # failure and the returned states
                log.error("Inverter time was not set")
                log.error("  ***** transmission state=%d (%s)" % (_response.transmission_state,
                                                                  AuroraDriver.TRANSMISSION[_response.transmission_state]))
                log.error("  ***** global state=%d (%s)" % (_response.global_state,
                                                            AuroraDriver.GLOBAL[_response.global_state]))

    def get_last_alarms(self):
        """Get the last four alarms."""

        return self.do_cmd('getLastAlarms').data

    def get_dsp(self):
        """Get DSP data."""

        manifest = dict((k, v) for k, v in self.inverter.commands.items() if v['cmd'] == 59)

        _dsp = {}
        for reading, params in manifest.items():
            _dsp[reading] = self.do_cmd(reading, globall=1).data
        return _dsp

    @property
    def hardware_name(self):
        """The name by which this hardware is known."""

        return self.model

    @property
    def part_number(self):
        """The inverter part number."""

        return self.do_cmd('getPartNumber').data

    @property
    def version(self):
        """The inverter version."""

        return self.do_cmd('getVersion').data

    @property
    def serial_number(self):
        """The inverter firmware release."""

        return self.do_cmd('getSerialNumber').data

    @property
    def manufacture_date(self):
        """The inverter firmware release."""

        return self.do_cmd('getManufactureDate').data

    @property
    def firmware_rel(self):
        """The inverter firmware release."""

        return self.do_cmd('getFirmwareRelease').data

    @staticmethod
    def calculate_energy(newtotal, oldtotal):
        """Calculate energy differential given two cumulative measurements."""

        delta = None
        if newtotal is not None and oldtotal is not None:
            if newtotal >= oldtotal:
                delta = newtotal - oldtotal
        return delta


# ============================================================================
#                            class AuroraInverter
# ============================================================================

class AuroraInverter(object):
    """Class to support serial comms with an Aurora PVI-6000 inverter."""

    DEFAULT_PORT = '/dev/ttyUSB0'
    DEFAULT_ADDRESS = '2'

    def __init__(self, port, baudrate=19200, timeout=2.0,
                 wait_before_retry=1.0, command_delay=0.05):
        """Initialise the AuroraInverter object."""

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.wait_before_retry = wait_before_retry
        self.command_delay = command_delay

        self.serial_port = None

        # Commands that I know to obtain readings from the Aurora inverter.
        # Listed against each command is the command and sub-command codes and
        # applicable decode function.
        self.commands = {
            'getState':           {'cmd': 50, 'sub':  None, 'fn': self._dec_state},
            'getPartNumber':      {'cmd': 52, 'sub':  None, 'fn': self._dec_ascii},
            'getVersion':         {'cmd': 58, 'sub':  None, 'fn': self._dec_ascii_and_state},
            'getGridV':           {'cmd': 59, 'sub':  1,    'fn': self._dec_float},
            'getGridC':           {'cmd': 59, 'sub':  2,    'fn': self._dec_float},
            'getGridP':           {'cmd': 59, 'sub':  3,    'fn': self._dec_float},
            'getFrequency':       {'cmd': 59, 'sub':  4,    'fn': self._dec_float},
            'getBulkV':           {'cmd': 59, 'sub':  5,    'fn': self._dec_float},
            'getLeakDcC':         {'cmd': 59, 'sub':  6,    'fn': self._dec_float},
            'getLeakC':           {'cmd': 59, 'sub':  7,    'fn': self._dec_float},
            'getStr1P':           {'cmd': 59, 'sub':  8,    'fn': self._dec_float},
            'getStr2P':           {'cmd': 59, 'sub':  9,    'fn': self._dec_float},
            'getInverterT':       {'cmd': 59, 'sub': 21,    'fn': self._dec_float},
            'getBoosterT':        {'cmd': 59, 'sub': 22,    'fn': self._dec_float},
            'getStr1V':           {'cmd': 59, 'sub': 23,    'fn': self._dec_float},
            'getStr1C':           {'cmd': 59, 'sub': 25,    'fn': self._dec_float},
            'getStr2V':           {'cmd': 59, 'sub': 26,    'fn': self._dec_float},
            'getStr2C':           {'cmd': 59, 'sub': 27,    'fn': self._dec_float},
            'getGridDcV':         {'cmd': 59, 'sub': 28,    'fn': self._dec_float},
            'getGridDcFreq':      {'cmd': 59, 'sub': 29,    'fn': self._dec_float},
            'getIsoR':            {'cmd': 59, 'sub': 30,    'fn': self._dec_float},
            'getBulkDcV':         {'cmd': 59, 'sub': 31,    'fn': self._dec_float},
            'getGridAvV':         {'cmd': 59, 'sub': 32,    'fn': self._dec_float},
            'getBulkMidV':        {'cmd': 59, 'sub': 33,    'fn': self._dec_float},
            'getGridNV':          {'cmd': 59, 'sub': 34,    'fn': self._dec_float},
            'getDayPeakP':        {'cmd': 59, 'sub': 35,    'fn': self._dec_float},
            'getPeakP':           {'cmd': 59, 'sub': 36,    'fn': self._dec_float},
            'getGridNPhV':        {'cmd': 59, 'sub': 38,    'fn': self._dec_float},
            'getSerialNumber':    {'cmd': 63, 'sub':  None, 'fn': self._dec_ascii},
            'getManufactureDate': {'cmd': 65, 'sub':  None, 'fn': self._dec_week_year},
            'getTimeDate':        {'cmd': 70, 'sub':  None, 'fn': self._dec_ts},
            'setTimeDate':        {'cmd': 71, 'sub':  None, 'fn': self._dec_raw},
            'getFirmwareRelease': {'cmd': 72, 'sub':  None, 'fn': self._dec_ascii_and_state},
            'getDayEnergy':       {'cmd': 78, 'sub':  0,    'fn': self._dec_int},
            'getWeekEnergy':      {'cmd': 78, 'sub':  1,    'fn': self._dec_int},
            'getMonthEnergy':     {'cmd': 78, 'sub':  3,    'fn': self._dec_int},
            'getYearEnergy':      {'cmd': 78, 'sub':  4,    'fn': self._dec_int},
            'getTotalEnergy':     {'cmd': 78, 'sub':  5,    'fn': self._dec_int},
            'getPartialEnergy':   {'cmd': 78, 'sub':  6,    'fn': self._dec_int},
            'getLastAlarms':      {'cmd': 86, 'sub':  None, 'fn': self._dec_alarms}
        }

    def open_port(self):
        """Open a serial port."""

        self.serial_port = serial.Serial(port=self.port, baudrate=self.baudrate,
                                         timeout=self.timeout)
        log.debug("Opened serial port %s; baudrate %d; timeout %.2f" % (self.port,
                                                                        self.baudrate,
                                                                        self.timeout))

    def close_port(self):
        """Close a serial port."""

        try:
            # this will cancel any pending loop:
            self.write(b'\n')
        except weewx.WeeWxIOError:
            pass
        self.serial_port.close()

    def write(self, data):
        """Send data to the inverter.

        Sends a data string to the inverter.

        Input:
            data: A string containing a sequence of bytes to be sent to the
                  inverter. Usually a sequence of bytes that have been packed
                  into a string.
        """

        try:
            n = self.serial_port.write(data)
        except serial.serialutil.SerialException as e:
            log.error("SerialException on write.")
            log.error("  ***** %s" % e)
            # re-raise as a WeeWX error I/O error:
            raise weewx.WeeWxIOError(e)
        # Python version 2.5 and earlier returns 'None', so it cannot be used
        # to test for completion.
        if n is not None and n != len(data):
            raise weewx.WeeWxIOError("Expected to write %d chars; sent %d instead" % (len(data),
                                                                                      n))

    def read(self, bytes_to_read=8):
        """Read data from the inverter.

        Read a given number of bytes from the inverter. If the incorrect number
        of bytes is received then raise a WeeWxIOError().

        Input:
            bytes: The number of bytes to be read.

        Returns:
            A string of length bytes containing the data read from the
            inverter.
        """

        try:
            _buffer = self.serial_port.read(bytes_to_read)
        except serial.serialutil.SerialException as e:
            log.error("SerialException on read.")
            log.error("  ***** %s % e")
            log.error("  ***** Is there a competing process running??")
            # re-raise as a WeeWX I/O error:
            raise weewx.WeeWxIOError(e)
        n = len(_buffer)
        if n != bytes_to_read:
            raise weewx.WeeWxIOError("Expected to read %d bytes; got %d instead" % (bytes_to_read,
                                                                                    n))
        return _buffer

    def send_cmd_with_crc(self, command, payload=None, globall=0,
                          address=2, max_tries=3):
        """Send a command with CRC to the inverter and return the response.

        Inputs:
            command:    The inverter command being issued, eg 'getGridV'.
                        String.
            payload:    Data to be sent to the inverter as part of the command.
                        Will occupy part or all of bytes 2,3,4,5,6 and 7.
                        Currently only used by setTime. String.
            global_mode:
            address:    The inverter address to be used, normally 2.
            max_tries:  The maximum number of attempts to send the data before
                        an error is raised.

        Returns:
            The decoded inverter response to the command as a Response Tuple.
        """

        # get the command message to be sent including CRC
        _command_bytes_crc = self.construct_cmd_message(command, payload, globall, address)
        # now send the assembled command retrying up to max_tries times
        for count in range(max_tries):
            if weewx.debug >= 2:
                log.debug("send_cmd_with_crc: sent %d" % format_byte_to_hex(_command_bytes_crc))
            try:
                self.write(_command_bytes_crc)
                # wait before reading
                time.sleep(self.command_delay)
                # look for the response
                _resp = self.read_with_crc()
                if self.commands[command]['fn'] is not None:
                    return self.commands[command]['fn'](_resp)
                else:
                    return _resp
            except weewx.CRCError:
                # We seem to get occasional CRC errors, once they start they
                # continue indefinitely. Closing then opening the serial port
                # seems to reset the error and allow proper communication to
                # continue (until the next one). So if we get a CRC error then
                # cycle the port and continue.

                if count + 1 < max_tries:
                    # log that we are about to cycle the port
                    log.info("CRC error on try #%d. Cycling port." % (count + 1, ))
                    # close the port, wait 0.2 sec then open the port
                    self.close_port()
                    time.sleep(0.2)
                    self.open_port()
                    # log that the port has been cycled
                    log.info("Port cycle complete.")
                else:
                    log.info("CRC error on try #%d." % (count + 1, ))
                continue
            except weewx.WeeWxIOError:
                pass
            # Sometimes we seem to get stuck in continuous IO errors. Cycling
            # the serial port after the second IO error usually fixes the
            # problem.
            if count + 1 < max_tries:
                # 1st or 2nd attempt
                if count + 2 == max_tries:
                    # the 2nd attempt failed so cycle the port
                    if weewx.debug >= 2:
                        log.debug("send_cmd_with_crc: try #%d unsuccessful... cycling port" % (count + 1, ))
                    # close the port, wait 0.2 sec then open the port
                    self.close_port()
                    time.sleep(0.2)
                    self.open_port()
                    # log that the port has been cycled
                    if weewx.debug >= 2:
                        log.debug("send_cmd_with_crc: port cycle complete.")
                else:
                    if weewx.debug >= 2:
                        log.debug("send_cmd_with_crc: try #%d unsuccessful... sleeping" % (count + 1, ))
                    time.sleep(self.wait_before_retry)
                if weewx.debug >= 2:
                    log.debug("send_cmd_with_crc: retrying")
            else:
                if weewx.debug >= 2:
                    log.debug("send_cmd_with_crc: try #%d unsuccessful" % (count + 1,))
        log.debug("Unable to send or receive data to/from the inverter")
        raise weewx.WeeWxIOError("Unable to send or receive data to/from the inverter")

    def read_with_crc(self, bytes_to_read=8):
        """Read an inverter response with CRC and return the data.

        Read a response from the inverter, check the CRC and if valid strip the
        CRC and return the data pay load.

        Input:
            bytes: The number of bytes to be read.

        Returns:
            A string of length bytes containing the data read from the
            inverter.
        """

        # read the response
        _response = self.read(bytes_to_read=bytes_to_read)
        # log the hex bytes received
        if weewx.debug >= 2:
            log.debug("read %s" % format_byte_to_hex(_response))
        # check the CRC and strip out the pay load
        return self.strip_crc16(_response)

    @staticmethod
    def crc16(buf):
        """Calculate a CCITT CRC16 checksum of a series of bytes.

        Calculated as per the Checksum calculation section of the Aurora PV
        Inverter Series Communications Protocol.

        Use struct module to convert the input string to a sequence of bytes.
        Could use bytearray but that was not introduced until python 2.6.

        Input:
            buf: string of binary packed data for which the CRC is to be
                 calculated

        Returns:
            A two byte string containing the CRC.
        """

        poly = 0x8408
        crc = 0xffff

        # if our input is nothing then that is simple
        if len(buf) == 0:
            return ~crc & 0xffff

        # Get a Struct object so we can unpack our input string. Our input
        # could be of any length so construct our Struct format string based on
        # the length of the input string.
        _format = ''.join(['B' for _b in range(len(buf))])
        s = struct.Struct(_format)
        # unpack the input string into our sequence of bytes
        _bytes = s.unpack(buf)

        # now calculate the CRC of our sequence of bytes
        for _byte in _bytes:
            for i in range(8):
                if (crc & 0x0001) ^ (_byte & 0x0001):
                    crc = ((crc >> 1) ^ poly) & 0xffff
                else:
                    crc >>= 1
                _byte >>= 1

        return ~crc & 0xffff

    @staticmethod
    def strip_crc16(buffer):
        """Strip CRC bytes from an inverter response."""

        # get the data payload
        data = buffer[:-2]
        # get the CRC bytes
        crc_bytes = buffer[-2:]
        # calculate the CRC of the received data
        crc = AuroraInverter.word2struct(AuroraInverter.crc16(data))
        # if our calculated CRC == received CRC then our data is valid and
        # return it, otherwise raise a CRCError
        if crc == crc_bytes:
            return bytearray(data)
        else:
            log.error("Inverter response failed CRC check:")
            log.error("  ***** response=%s" % (format_byte_to_hex(buffer)))
            log.error("  *****     data=%s        CRC=%s  expected CRC=%s" % (format_byte_to_hex(data),
                                                                              format_byte_to_hex(crc_bytes),
                                                                              format_byte_to_hex(crc)))
            raise weewx.CRCError("Inverter response failed CRC check")

    @staticmethod
    def word2struct(i):
        """Take a 2 byte word and reverse the byte order.

        Input:
            i: A 2 byte string containing the bytes to be processed.

        Returns:
            A 2 byte string consisting of the input bytes but in reverse order.
        """

        s = struct.Struct('2B')
        b = s.pack(i & 0xff, i // 256)
        return b

    def construct_cmd_message(self, command, payload=None, global_mode=0, address=2):
        """Construct the byte sequence for a command.

        The inverter communications protocol uses fixed length transmission
        messages of 10 bytes. Each message is structured as follows:

        byte 0: inverter address
        byte 1: command code
        byte 2: byte 2
        byte 3: byte 3
        byte 4: byte 4
        byte 5: byte 5
        byte 6: byte 6
        byte 7: byte 7
        byte 8: CRC low byte
        byte 9: CRC high byte

        Bytes 2 to 7 inclusive are used with some command codes to represent a
        sub-command and/or command payload. Unused bytes can be anything, but
        in this implementation they are padded with 0x00.

        Inputs:
            command:     The inverter command being issued, eg 'getGridV'. Must
                         be a key to the AuroraInverter.commands dict.
                         Mandatory, string.
            payload:     Data to be sent to the inverter as part of the command.
                         Will occupy part or all of bytes 2, 3, 4, 5, 6 and 7.
                         Optional, bytestring. (currently only used by setTime)
            global_mode: Whether to return module energy (master or slave) (0)
                         or global energy (master) (1). Optional, integer 0 or
                         1, default 0.
            address:     The inverter address to be used. Optional,
                         integer 0-63, default is 2.

        Returns:
            A bytes object (aka bytestring) containing the command message.
        """
        # TODO. global_mode should not be here as it is only used with the #59 command

        # construct a tuple of the bytes we are to send, starting with byte 0,
        # ending with byte 9

        # do we have a sub-command
        if self.commands[command]['sub'] is not None:
            # we have a sub-command, construct the tuple
            command_t = (address,
                         self.commands[command]['cmd'],
                         self.commands[command]['sub'],
                         global_mode)
        elif payload is not None:
            # We have no sub-command, but we have a payload. As the payload is
            # a bytestring we can convert the payload to a tuple with a simple
            # list comprehension
            payload_t = tuple([b for b in payload])
            command_t = (address, self.commands[command]['cmd']) + payload_t
        else:
            # we have no sub-command or payload
            command_t = (address, self.commands[command]['cmd'])
        # pad out the tuple with 0s until it's length is 8 (10 bytes - 2 bytes
        # for CRC)
        padded_command_t = command_t + (0,) * (8 - len(command_t))
        # create a bytes object by packing our command tuple items
        command_bytes = struct.pack('8B', *padded_command_t)
        # add the CRC
        return command_bytes + self.word2struct(self.crc16(command_bytes))

    @staticmethod
    def _dec_state(v):
        """Decode an inverter state request response.

        To be written.
        """

        try:
            return ResponseTuple(int(v[0]), int(v[1]), (int(v[2]),
                                 int(v[3]), int(v[4]), int(v[5])))
        except (IndexError, TypeError):
            return ResponseTuple(None, None, None)

    @staticmethod
    def _dec_ascii(v):
        """Decode a response containing ASCII characters only.

        Decode a 6 byte response in the following format:

        byte 0: character 6 - most significant character
        byte 1: character 5
        byte 2: character 4
        byte 3: character 3
        byte 4: character 2
        byte 5: character 1 - least significant character

        Input:
            v: bytearray containing the 6 byte response

        Returns:
            A ResponseTuple where the transmission and global attributes are
            None and the data attribute is a 6 character ASCII string.
        """

        try:
            return ResponseTuple(None, None, str(v.decode()))
        except (IndexError, TypeError):
            return ResponseTuple(None, None, None)

    @staticmethod
    def _dec_ascii_and_state(v):
        """Decode a response containing ASCII characters and inverter state.

        Decode a 6 byte response in the following format:

        byte 0: transmission state
        byte 1: global state
        byte 2: par 1
        byte 3: par 2
        byte 4: par 3
        byte 5: par 4

        where par 1..par 4 are ASCII characters used to determine the inverter
        version. To decode par characters refer to Aurora PV Inverter Series
        Communication Protocol rel 4.7 command 58.

        Input:
            v: bytearray containing the 6 byte response

        Returns:
            A ResponseTuple where the data attribute is a 4 character ASCII
            string.
        """

        try:
            tx_state = int(v[0])
            g_state = int(v[1])
            ascii_str = str(v[2:6].decode())
            return ResponseTuple(tx_state, g_state, ascii_str)
        except (IndexError, TypeError):
            return ResponseTuple(None, None, None)

    @staticmethod
    def _dec_float(v):
        """Decode a response containing 4 byte float and inverter state.

        Decode a 6 byte response in the following format:

        byte 0: transmission state
        byte 1: global state
        byte 2: val3
        byte 3: val2
        byte 4: val1
        byte 5: val0

        ANSI standard format float:

        bit bit         bit bit                             bit
        31  30          23  22                              0
        <S> <--Exponent-->  <------------Mantissa----------->

        val3 = bits 24-31
        val2 = bits 16-23
        val1 = bits  8-15
        val0 = bits  0-7

        where

            float = (-1)**S * 2**(Exponent-127) * 1.Mantissa

        Refer to the Aurora PV Inverter Series Communication Protocol rel 4.7
        command 59.

        Input:
            v: bytearray containing the 6 bytes to convert

        Returns:
            A ResponseTuple where the data attribute is a 4 byte float.
        """

        try:
            return ResponseTuple(int(v[0]), int(v[1]),
                                 struct.unpack('!f', v[2:])[0])
        except (IndexError, TypeError):
            return ResponseTuple(None, None, None)

    @staticmethod
    def _dec_week_year(v):
        """Decode a response containing week and year and inverter state.

        Decode a 6 byte response in the following format:

        byte 0: transmission state
        byte 1: global state
        byte 2: most significant week digit
        byte 3: least significant week digit
        byte 4: most significant year digit
        byte 5: least significant year digit

        Input:
            v: bytearray containing the 6 byte response

        Returns:
           A ResponseTuple where data attribute is a 2 way tuple of (week,
           year).
        """

        try:
            s = struct.Struct('>H')
            week = s.unpack(v[2:4])
            year = s.unpack(v[4:6])
            return ResponseTuple(int(v[0]), int(v[1]), (week, year))
        except (IndexError, TypeError):
            return ResponseTuple(None, None, None)

    @staticmethod
    def _dec_ts(v):
        """Decode a response containing timestamp and inverter state.

        Decode a 6 byte response in the following format:

        byte 0: transmission state
        byte 1: global state
        byte 2: time3
        byte 3: time2
        byte 4: time1
        byte 5: time0

        where

            time-date = time3 * 2**24 + time2 * 2**16 + time1 * 2**8 + time0
            2**x = 2 raised to the power of x
            time-date = number of seconds since midnight 1 January 2000

        Refer to the Aurora PV Inverter Series Communication Protocol rel 4.7
        command 70.

        Since WeeWX uses epoch timestamps the calculated date-time value is
        converted to an epoch timestamp before being returned in a
        ResponseTuple.

        Input:
            v: bytearray containing the 6 bytes to convert

        Returns:
            A ResponseTuple where the data attribute is an epoch timestamp.
        """

        try:
            return ResponseTuple(int(v[0]), int(v[1]),
                                 AuroraInverter._dec_int(v).data + 946648800)
        except (IndexError, TypeError):
            return ResponseTuple(None, None, None)

    @staticmethod
    def _dec_int(v):
        """Decode a response containing 4 byte integer and inverter state.

        Decode a 6 byte response in the following format:

        byte 0: transmission state
        byte 1: global state
        byte 2: int3
        byte 3: int2
        byte 4: int1
        byte 5: int0

        where

            integer value = int3 * 2**24 + int2 * 2**16 + int1 * 2**8 + int0
            2**x = 2 raised to the power of x

        Refer to the Aurora PV Inverter Series Communication Protocol rel 4.7
        command 78

        Input:
            v: bytearray containing the 6 bytes to convert

        Returns:
            A ResponseTuple where the data attribute is a 4 byte integer.
        """

        try:
            s = struct.Struct('>I')
            _int = s.unpack(v[2:6])[0]
            return ResponseTuple(int(v[0]), int(v[1]), _int)
        except (IndexError, TypeError):
            return ResponseTuple(None, None, None)

    @staticmethod
    def _dec_raw(v):
        """Decode a response containing inverter state and unknown data.

        Decode a 6 byte response in the following format:

        byte 0: transmission state
        byte 1: global state
        byte 2: data 4
        byte 3: data 3
        byte 4: data 2
        byte 5: data 1 - least significant character

        Input:
            v: bytearray containing the 6 byte response

        Returns:
            A ResponseTuple where the transmission and global attributes are
            None and the data attribute is a 4 character ASCII string.
        """

        try:
            return AuroraInverter._dec_ascii_and_state(v)
        except (IndexError, TypeError):
            return ResponseTuple(None, None, None)

    @staticmethod
    def _dec_alarms(v):
        """Decode a response contain last 4 alarms and inverter state.

        Decode a 6 byte response in the following format:

        byte 0: transmission state
        byte 1: global state
        byte 2: alarm code 1 (oldest)
        byte 3: alarm code 2
        byte 4: alarm code 3
        byte 5: alarm code 4 (latest)

        Input:
            v: bytearray containing the 6 byte response

        Returns:
           A ResponseTuple where data attribute is a 4 way tuple of alarm
           codes.
        """

        try:
            _alarms = tuple([int(a) for a in v[2:6]])
            return ResponseTuple(int(v[0]), int(v[1]), _alarms)
        except (IndexError, TypeError):
            return ResponseTuple(None, None, None)


# ============================================================================
#                          Class AuroraConfigurator
# ============================================================================

class AuroraConfigurator(weewx.drivers.AbstractConfigurator):
    """Configures the Aurora inverter.

    This class is used by weectl device when interrogating an Aurora inverter.

    The Ecowitt gateway device API supports both reading and setting various
    gateway device parameters; however, at this time the Ecowitt gateway
    device driver only supports the reading these parameters. The Ecowitt
    gateway device driver does not support setting these parameters, rather
    this should be done via the Ecowitt WSView Plus app.

    When used with weectl device this configurator allows inverter parameters
    to be displayed. The Aurora driver may also be run directly to test the
    Aurora driver operation as well as display various driver configuration
    options (as distinct from inverter hardware parameters).
    """

    @property
    def description(self):
        """Description displayed as part of weectl device help information."""

        return "Configuration utility for an Aurora inverter."

    @property
    def usage(self):
        """weectl device usage information."""

        return """%prog --help
       %prog --version 
       %prog --live-data [FILENAME|--config=FILENAME]
       %prog --gen-packets [FILENAME|--config=FILENAME]
       %prog --status [FILENAME|--config=FILENAME]
       %prog --info [FILENAME|--config=FILENAME]
       %prog --time [FILENAME|--config=FILENAME]
       %prog --set-time [FILENAME|--config=FILENAME]"""

    @property
    def epilog(self):
        """Epilog displayed as part of weectl device help information."""

        return "Be sure to stop weewxd first before using. Mutating actions will request " \
               "confirmation before proceeding.\n"

    def add_options(self, parser):
        """Define weectl device parser options."""

        super(AuroraConfigurator, self).add_options(parser)
        if parser.has_option('-y'):
            parser.remove_option('-y')
        parser.add_option('--version',
                          action='store_true',
                          help='Display driver version.')
        parser.add_option('--live-data',
                          dest='live',
                          action='store_true',
                          help='Display live inverter data.')
        parser.add_option('--gen-packets',
                          dest='gen',
                          action='store_true',
                          help='Output LOOP packets indefinitely.')
        parser.add_option('--status',
                          dest='status',
                          action='store_true',
                          help='Display inverter status.')
        parser.add_option('--info',
                          dest='info',
                          action='store_true',
                          help='Display inverter information.')
        parser.add_option('--time',
                          dest='get_time',
                          action='store_true',
                          help='Display current inverter date-time.')
        parser.add_option('--set-time',
                          dest='set_time',
                          action='store_true',
                          help='Set inverter date-time to the current system date-time.')

    def do_options(self, options, parser, config_dict, prompt):
        """Process weectl device option parser options."""

        import sys

        # get station config dict to use
        stn_dict = config_dict.get('Aurora', {})

        # we can process the --version option now if required
        if options.version:
            # we don't actually have to do anything as 'weectl device' prints
            # the driver version as the last thing before the configurator
            # takes over. So just exist.
            sys.exit(0)

        # set weewx.debug as necessary
        if options.debug is not None:
            _debug = weeutil.weeutil.to_int(options.debug)
        else:
            _debug = weeutil.weeutil.to_int(config_dict.get('debug', 0))
        weewx.debug = _debug
        # inform the user if the debug level is 'higher' than 0
        if _debug > 0:
            print(f"debug level is '{_debug}'")

        # now we can set up the user customized logging
        weeutil.logger.setup('weewx', config_dict)

        # get anAurora driver object
        aurora = AuroraDriver(**stn_dict)
        if options.live:
            pass
        elif options.gen:
            pass
        elif options.status:
            pass
        elif options.info:
            pass
        elif options.get_time:
            pass
        elif options.set_time:
            pass
        else:
            pass


# ============================================================================
#                           Class AuroraConfEditor
# ============================================================================

class AuroraConfEditor(weewx.drivers.AbstractConfEditor):
    """Config editor for the Aurora driver."""

    @property
    def default_stanza(self):
        return f"""
[Aurora]
    # This section is for the Power One Aurora series of inverters.

    # The inverter model, e.g., Aurora PVI-6000, Aurora PVI-5000
    model = INSERT_MODEL_HERE

    # Serial port such as /dev/ttyS0, /dev/ttyUSB0, or /dev/cua0
    port = {AuroraInverter.DEFAULT_PORT}

    # inverter address, usually 2
    address = {AuroraInverter.DEFAULT_ADDRESS}

    # The driver to use:
    driver = user.aurora
"""

    def prompt_for_settings(self):

        print("Specify the inverter model, for example: Aurora PVI-6000 or Aurora PVI-5000")
        model = self._prompt('model', 'Aurora PVI-6000')
        print("Specify the serial port on which the inverter is connected, for")
        print("example: /dev/ttyUSB0 or /dev/ttyS0 or /dev/cua0.")
        port = self._prompt('port', AuroraInverter.DEFAULT_PORT)
        print("Specify the inverter address, normally 2")
        address = self._prompt('address', AuroraInverter.DEFAULT_ADDRESS)
        return {'model': model,
                'port': port,
                'address': address
                }

    @staticmethod
    def modify_config(config_dict):

        print("""Setting record_generation to software.""")
        config_dict['StdArchive']['record_generation'] = 'software'
        print("""Setting energy extractor to sum.""")
        if 'Accumulator' in config_dict:
            config_dict['Accumulator']['energy'] = {'extractor': 'sum'}
        else:
            config_dict['Accumulator'] = {'energy': {'extractor': 'sum'}}


# ============================================================================
#                             Utility functions
# ============================================================================

def format_byte_to_hex(byte_seq):
    """Format a sequence of bytes as a string of space separated hex bytes.

    Input:
        bytes: A string or sequence containing the bytes to be formatted.

    Returns:
        A string of space separated hex digit pairs representing the input byte
        sequence.
    """
    _b_array = bytearray(byte_seq)
    return ' '.join(['%02X' % b for b in _b_array])


# ============================================================================
#                            class ResponseTuple
# ============================================================================

# An inverter response consists of 8 bytes as follows:
#
#   byte 0: transmission state
#   byte 1: global state
#   byte 2: data
#   byte 3: data
#   byte 4: data
#   byte 5: data
#   byte 6: CRC low byte
#   byte 7: CRC high byte
#
# The CRC bytes are stripped away by the Aurora class when validating the
# inverter response. The four data bytes may represent ASCII characters, a
# 4 byte float or some other coded value. An inverter response can be
# represented as a 3-way tuple called a response tuple:
#
# Item  Attribute       Meaning
# 0     transmission    The transmission state code (an integer)
# 1     global          The global state code (an integer)
# 2     data            The four bytes in decoded form (eg 4 character ASCII
#                       string, ANSI float)
#
# Some inverter responses do not include the transmission state and global
# state, in these cases those response tuple attributes are set to None.
#
# It is also valid to have a data attribute of None. In these cases the data
# could not be decoded and the driver will handle this appropriately.

class ResponseTuple(tuple):

    def __new__(cls, *args):
        return tuple.__new__(cls, args)

    @property
    def transmission_state(self):
        return self[0]

    @property
    def global_state(self):
        return self[1]

    @property
    def data(self):
        return self[2]


class DirectAurora(object):
    """Class to interact with an Aurora inverter driver when run directly.

    Would normally run a driver directly by calling from main() only, but when
    run directly the Aurora driver has numerous options so pushing the detail
    into its own class/object makes sense. Also simplifies some test suite
    routines/calls.

    A DirectAurora object is created with just an optparse options dict and a
    standard WeeWX station dict. Once created the DirectAurora()
    process_arguments() method is called to process the respective command line
    options.
    """

    DEFAULT_PORT = '/dev/ttyUSB0'

    def __init__(self, namespace, parser, aurora_dict):
        """Initialise a DirectAurora object."""

        # save the argparse arguments and parser
        self.namespace = namespace
        self.parser = parser
        # save our config dict
        self.aurora_dict = aurora_dict
        # obtain the port to be used, that is the minimum we need to
        # communicate with the inverter
        self.port = self.port_from_config_opts()

    def port_from_config_opts(self):
        """Obtain the port from inverter config or command line argument.

        Determine the port to use given an inverter config dict and command
        line arguments. The port is chosen as follows:
        - if specified use the port from the command line
        - if a port was not specified on the command line obtain the port from
          the inverter config dict
        - if the inverter config dict does not specify a port use the default
          /dev/ttyUSB0
        """

        # obtain a port number from the command line options
        port = self.namespace.port if self.namespace.port else None
        # if we didn't get a port check the inverter config dict
        if port is None:
            # obtain the port from the inverter config dict
            port = self.aurora_dict.get('port')
            if port is None:
                port = DirectAurora.DEFAULT_PORT
                if weewx.debug >= 1:
                    print(f"Port set to default port '{port}'")
            else:
                if weewx.debug >= 1:
                    print("Port obtained from station config")
        else:
            if weewx.debug >= 1:
                print("Port obtained from command line options")
        return port

    def process_arguments(self):
        """Call the appropriate method based on the argparse arguments."""

        # run the driver
        if hasattr(self.namespace, 'gen') and self.namespace.gen:
            self.test_driver()
        elif hasattr(self.namespace, 'status') and self.namespace.status:
            self.status()
        elif hasattr(self.namespace, 'info') and self.namespace.info:
            self.info()
        elif hasattr(self.namespace, 'readings') and self.namespace.readings:
            self.readings()
        elif hasattr(self.namespace, 'get_time') and self.namespace.get_time:
            self.get_time()
        elif hasattr(self.namespace, 'set_time') and self.namespace.set_time:
            self.set_time()
        else:
            print()
            print("No option selected, nothing done")
            print()
            self.parser.print_help()
            return

    def test_driver(self):
        """Exercise the aurora driver.

        Exercises the aurora driver only. Loop packets, but no archive records,
        are emitted to the console continuously until a keyboard interrupt is
        received. A station config dict is coalesced from any relevant command
        line parameters and the config file in use with command line
        parameters overriding those in the config file.
        """

        log.info("Testing Aurora driver...")
        if self.namespace.poll_interval:
            self.aurora_dict['poll_interval'] = self.namespace.poll_interval
        if self.namespace.max_tries:
            self.aurora_dict['max_tries'] = self.namespace.max_tries
        if self.namespace.retry_wait:
            self.aurora_dict['retry_wait'] = self.namespace.retry_wait
        # wrap in a try..except in case there is an error
        try:
            # get a AuroraDriver object
            driver = AuroraDriver(**self.aurora_dict)
            # identify the device being used
            print()
            print(f"Interrogating {driver.model} at {driver.inverter.port}")
            print()
            # continuously get loop packets and print them to screen
            for pkt in driver.genLoopPackets():
                print(f"{weeutil.weeutil.timestamp_to_string(pkt['dateTime'])}: "
                      f"{weeutil.weeutil.to_sorted_string(pkt)})")
        except Exception as e:
            print()
            print("Unable to connect to device: %s" % e)
        except KeyboardInterrupt:
            # we have a keyboard interrupt so shut down
            driver.closePort()
        log.info("Aurora driver testing complete")

    def status(self):
        """Display the inverter status."""

        # wrap in a try..except in case there is an error
        try:
            # get an AuroraDriver object
            driver = AuroraDriver(port=self.port)
            # obtain the inverter state
            response_rt = driver.do_cmd('getState')
            # and print the state
            print()
            print(f"{driver.model} Status:")
            if response_rt.transmission_state is not None:
                print(f'{"Transmission state":>22}: {response_rt.transmission_state} '
                      f'({AuroraDriver.TRANSMISSION[response_rt.transmission_state]})')
            else:
                print(f'{"Transmission state":>22}: None (---)')
            if response_rt.global_state is not None:
                print(f'{"Global state":>22}: {response_rt.global_state} '
                      f'({AuroraDriver.GLOBAL[response_rt.global_state]})')
            else:
                print(f'{"Global state":>22}: None (---)')
            if response_rt.data is not None and response_rt.data[0] is not None:
                print(f'{"Inverter state":>22}: {response_rt.data[0]} '
                      f'({AuroraDriver.INVERTER[response_rt.data[0]]})')
            else:
                print(f'{"Inverter state":>22}: None (---)')
            if response_rt.data is not None and response_rt.data[1] is not None:
                print(f'{"DcDc1 state":>22}: {response_rt.data[1]} '
                      f'({AuroraDriver.DCDC[response_rt.data[1]]})')
            else:
                print(f'{"DcDc1 state":>22}: None (---)')
            if response_rt.data is not None and response_rt.data[2] is not None:
                print(f'{"DcDc2 state":>22}: {response_rt.data[2]} '
                      f'({AuroraDriver.DCDC[response_rt.data[2]]})')
            else:
                print(f'{"DcDc2 state":>22}: None (---)')
            if response_rt.data is not None and response_rt.data[3] is not None:
                print(f'{"Alarm state":>22}: {response_rt.data[3]} '
                      f'({AuroraDriver.ALARM[response_rt.data[3]]["description"]})'
                      f'[{AuroraDriver.ALARM[response_rt.data[3]]["code"]}]')
            else:
                print(f'{"Alarm state":>22}: None (---)')
        except Exception as e:
            print()
            print("Unable to connect to device: %s" % e)

    def info(self):
        
        try:
            # get an AuroraDriver object
            driver = AuroraDriver(port=self.port)
            # display inverter info
            print()
            print(f'{driver.model} Information:')
            print(f'{"Part Number":>21}: {driver.part_number}')
            print(f'{"Version":>21}: {driver.version}')
            print(f'{"Serial Number":>21}: {driver.serial_number}')
            print(f'{"Manufacture Date":>21}: {driver.manufacture_date}')
            print(f'{"Firmware Release":>21}: {driver.firmware_rel}')
        except Exception as e:
            print()
            print("Unable to connect to device: %s" % e)

    def readings(self):

        try:
            # get an AuroraDriver object
            driver = AuroraDriver(port=self.port)
            print()
            print(f"{driver.model} Current Readings:")
            print("-----------------------------------------------")
            print("Grid:")
            print(f"{'Voltage':>29}: {driver.do_cmd('getGridV').data}V")
            print(f"{'Current':>29}: {driver.do_cmd('getGridC').data}A")
            print(f"{'Power':>29}: {driver.do_cmd('getGridP').data}W")
            print(f"{'Frequency':>29}: {driver.do_cmd('getFrequency').data}Hz")
            print(f"{'Average Voltage':>29}: {driver.do_cmd('getGridAvV').data}V")
            print(f"{'Neutral Voltage':>29}: {driver.do_cmd('getGridNV').data}V")
            print(f"{'Neutral Phase Voltage':>29}: {driver.do_cmd('getGridNPhV').data}V")
            print("-----------------------------------------------")
            print("String 1:")
            print(f"{'Voltage':>29}: {driver.do_cmd('getStr1V').data}V")
            print(f"{'Current':>29}: {driver.do_cmd('getStr1C').data}A")
            print(f"{'Power':>29}: {driver.do_cmd('getStr1P').data}W")
            print("-----------------------------------------------")
            print("String 2:")
            print(f"{'Voltage':>29}: {driver.do_cmd('getStr2V').data}V")
            print(f"{'Current':>29}: {driver.do_cmd('getStr2C').data}A")
            print(f"{'Power':>29}: {driver.do_cmd('getStr2P').data}W")
            print("-----------------------------------------------")
            print("Inverter:")
            print(f"""{"Voltage (DC/DC Booster)":>29}: {driver.do_cmd("getGridDcV").data}V""")
            print(f"""{"Frequency (DC/DC Booster)":>29}: {driver.do_cmd("getGridDcFreq").data}Hz""")
            print(f"""{"Inverter Temp":>29}: {driver.do_cmd("getInverterT").data}C""")
            print(f"""{"Booster Temp":>29}: {driver.do_cmd("getBoosterT").data}C""")
            print(f"""{"Today's Peak Power":>29}: {driver.do_cmd("getDayPeakP").data}W""")
            print(f"""{"Lifetime Peak Power":>29}: {driver.do_cmd("getPeakP").data}W""")
            print(f"""{"Today's Energy":>29}: {driver.do_cmd("getDayEnergy").data}Wh""")
            print(f"""{"This Weeks's Energy":>29}: {driver.do_cmd("getWeekEnergy").data}Wh""")
            print(f"""{"This Month's Energy":>29}: {driver.do_cmd("getMonthEnergy").data}Wh""")
            print(f"""{"This Year's Energy":>29}: {driver.do_cmd("getYearEnergy").data}Wh""")
            print(f"""{"Partial Energy":>29}: {driver.do_cmd("getPartialEnergy").data}Wh""")
            print(f"""{"Lifetime Energy":>29}: {driver.do_cmd("getTotalEnergy").data}Wh""")
            print()
            print(f"{'Bulk Voltage':>29}: {driver.do_cmd('getBulkV').data}V")
            print(f"{'Bulk DC Voltage':>29}: {driver.do_cmd('getBulkDcV').data}V")
            print(f"{'Bulk Mid Voltage':>29}: {driver.do_cmd('getBulkMidV').data}V")
            print()
            print(f"{'Insulation Resistance':>29}: {driver.do_cmd('getIsoR').data}MOhms")
            print()
            print(f"{'zLeakage Current(Inverter)zz':>29}: {driver.do_cmd('getLeakC').data}A")
            print(f"{'Leakage Current(Booster)':>29}: {driver.do_cmd('getLeakDcC').data}A")
        except Exception as e:
            print()
            print("Unable to connect to device: %s" % e)

    def get_time(self):

        try:
            # get an AuroraDriver object
            driver = AuroraDriver(port=self.port)
        except Exception as e:
            # something happened and we could not load the driver, inform the
            # user and display any error message
            print()
            print("Unable to load driver: %s" % e)
            return
        try:
            # obtain the inverter time
            inverter_ts = driver.getTime()
        except Exception as e:
            # something happened and we could not get the time from the
            # inverter, inform the user and display any error message
            print()
            print("Unable to obtain device time: %s" % e)
        else:
            # we have the inverter time, so calculate the difference to system
            # time
            _error = inverter_ts - time.time()
            # display the results
            print()
            print(f"Inverter date-time is {timestamp_to_string(inverter_ts)}")
            print(f"    Clock error is {_error:.3f} seconds (positive is fast)")

    def set_time(self):

        try:
            # get an AuroraDriver object
            driver = AuroraDriver(port=self.port)
            # set the inverter time
            # obtain the inverter time
            inverter_ts = driver.getTime()
            # calculate the difference to system time
            _error = inverter_ts - time.time()
            # display the results
            print()
            print(f"Current inverter date-time is {timestamp_to_string(inverter_ts)}")
            print(f"    Clock error is {_error:.3f} seconds (positive is fast)")
            print()
            print("Setting time...")
            # set the inverter time to the system time
            driver.setTime()
            # now obtain and display the inverter time
            inverter_ts = driver.getTime()
            _error = inverter_ts - time.time()
            print()
            print(f"Updated inverter date-time is {timestamp_to_string(inverter_ts)}")
            print(f"    Clock error is {_error:.3f} seconds (positive is fast)")
        except Exception as e:
            print()
            print("Unable to connect to device: %s" % e)


# ============================================================================
#                          Main Entry for Testing
# ============================================================================

"""
Define a main entry point for basic testing without the WeeWX engine and
service overhead. To invoke this driver without WeeWX:

$ PYTHONPATH=BIN_ROOT python3 WEEWX_ROOT/bin/user/aurora.py --option

where:
- BIN_ROOT is the location of the WeeWX executables (varies by install method
  and system)
- WEEWX_ROOT is the WeeWX root directory (nominally weewx-data)
- option is one of the following options:
  --help          - display driver command line help
  --version       - display driver version
  --gen-packets   - generate LOOP packets indefinitely
  --get-status    - display inverter status
  --get-info      - display inverter information
  --get-readings  - display current inverter readings
  --get-time      - display inverter time
  --set-time      - set inverter time to the current system time
"""

def main():

    # python imports
    import argparse
    import sys
    import time

    # WeeWX imports
    import weecfg

    from weeutil.weeutil import bcolors, timestamp_to_string, to_sorted_string

    usage = f"""{bcolors.BOLD}%(prog)s --help
                 --version 
                 --gen-packets [--config=FILENAME]
                 --get-status [--config=FILENAME]
                 --get-info [--config=FILENAME]
                 --get-readings [--config=FILENAME]
                 --get-time [--config=FILENAME]
                 --set-time [--config=FILENAME]
                 --port{bcolors.ENDC}
    """
    description = """Interact with a Power One Aurora inverter."""

    parser = argparse.ArgumentParser(usage=usage,
                                     description=description,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('--config',
                        type=str,
                        metavar="FILENAME",
                        help="Use configuration file FILENAME.")
    parser.add_argument('--version',
                        action='store_true',
                        help='Display driver version.')
    parser.add_argument('--port',
                        type=str,
                        metavar="PORT",
                        help='Use port PORT.')
    parser.add_argument('--gen-packets',
                        dest='gen',
                        action='store_true',
                        help='Output LOOP packets indefinitely.')
    parser.add_argument('--get-status',
                        dest='status',
                        action='store_true',
                        help='Display inverter status.')
    parser.add_argument('--get-info',
                        dest='info',
                        action='store_true',
                        help='Display inverter information.')
    parser.add_argument('--get-readings',
                        dest='readings',
                        action='store_true',
                        help='Display current inverter readings.')
    parser.add_argument('--get-time',
                        dest='get_time',
                        action='store_true',
                        help='Display current inverter date-time.')
    parser.add_argument('--set-time',
                        dest='set_time',
                        action='store_true',
                        help='Set inverter date-time to the current system date-time.')
    namespace = parser.parse_args()

    if len(sys.argv) == 1:
        # we have no arguments, display the help text and exit
        parser.print_help()
        sys.exit(0)

    # if we have been asked for the version number we can display that now
    if namespace.version:
        print(f"Aurora driver version {DRIVER_VERSION}")
        sys.exit(0)

    # any other options will require an AuroraDriver object
    # first get the config_dict to use
    config_path, config_dict = weecfg.read_config(namespace.config)
    print(f"Using configuration file '{config_path}'")

    # define custom units settings
    define_units()

    # now get a config dict for the inverter
    aurora_dict = config_dict.get('Aurora')

    weeutil.logger.setup('weewx', config_dict)

    # get a DirectAurora object
    direct_aurora = DirectAurora(namespace, parser, aurora_dict)
    # now let the DirectAurora object process the arguments
    direct_aurora.process_arguments()
    exit(1)


if __name__ == "__main__":
    # start up the program
    main()
