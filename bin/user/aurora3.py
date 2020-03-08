"""
aurora.py

A WeeWX driver for Power One Aurora inverters.

Copyright (C) 2016-2020 Gary Roderick                  gjroderick<at>gmail.com

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program.  If not, see http://www.gnu.org/licenses/.

Version: 0.5.2                                        Date: 22 December 2018

Revision History
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



from six import iteritems

import logging
import serial
import struct
import syslog
import time

# WeeWX imports
import weewx.drivers
import weewx.units

from weeutil.weeutil import to_bool

# get a logger object
log = logging.getLogger(__name__)

# our name and version number
DRIVER_NAME = 'Aurora'
DRIVER_VERSION = '0.5.2'


# define unit groups, formats and conversions for units used by the aurora
# driver

# create groups for frequency and resistance
weewx.units.USUnits['group_frequency'] = 'hertz'
weewx.units.MetricUnits['group_frequency'] = 'hertz'
weewx.units.MetricWXUnits['group_frequency'] = 'hertz'
weewx.units.USUnits['group_resistance'] = 'ohm'
weewx.units.MetricUnits['group_resistance'] = 'ohm'
weewx.units.MetricWXUnits['group_resistance'] = 'ohm'

# set default formats and labels for frequency and resistance
weewx.units.default_unit_format_dict['hertz'] = '%.1f'
weewx.units.default_unit_label_dict['hertz'] = ' Hz'
weewx.units.default_unit_format_dict['ohm'] = '%.1f'
weewx.units.default_unit_label_dict['ohm'] = ' \xce\xa9'
weewx.units.default_unit_format_dict['kohm'] = '%.1f'
weewx.units.default_unit_label_dict['kohm'] = ' k\xce\xa9'
weewx.units.default_unit_format_dict['Mohm'] = '%.1f'
weewx.units.default_unit_label_dict['Mohm'] = ' M\xce\xa9'

# define conversion functions for resistance
weewx.units.conversionDict['ohm'] = {'kohm': lambda x: x / 1000.0,
                                     'Mohm': lambda x: x / 1000000.0}
weewx.units.conversionDict['kohm'] = {'ohm': lambda x: x * 1000.0,
                                      'Mohm': lambda x: x / 1000.0}
weewx.units.conversionDict['Mohm'] = {'ohm': lambda x: x * 1000000.0,
                                      'kohm': lambda x: x * 1000.0}

# set default formats and labels for kilo and mega watt hours
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


def loader(config_dict, engine):  # @UnusedVariable
    return AuroraDriver(config_dict[DRIVER_NAME])


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

    # default sensor map
    DEFAULT_SENSOR_MAP = {'timeDate': 'getTimeDate',
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

    def __init__(self, aurora_dict):
        """Initialise an object of type AuroroaDriver."""

        # model
        self.model = aurora_dict.get('model', 'Aurora')
        log.debug('%s driver version is %s' % (self.model, DRIVER_VERSION))
        # serial comms options
        try:
            port = aurora_dict.get('port', '/dev/ttyUSB0')
        except KeyError:
            raise Exception("Required parameter 'port' was not specified.")
        baudrate = int(aurora_dict.get('baudrate', 19200))
        timeout = float(aurora_dict.get('timeout', 2.0))
        wait_before_retry = float(aurora_dict.get('wait_before_retry', 1.0))
        command_delay = float(aurora_dict.get('command_delay', 0.05))
        log.debug('   using port %s baudrate %d timeout %s' % (port,
                                                               baudrate,
                                                               timeout))
        log.debug('   wait_before_retry %s command_delay %s' % (wait_before_retry,
                                                                command_delay))
        # driver options
        self.max_command_tries = int(aurora_dict.get('max_command_tries', 3))
        self.polling_interval = int(aurora_dict.get('loop_interval', 10))
        self.address = int(aurora_dict.get('address', 2))
        self.max_loop_tries = int(aurora_dict.get('max_loop_tries', 3))
        log.debug('   inverter address %d will be polled every %d seconds' % (self.address,
                                                                              self.polling_interval))
        log.debug('   max_command_tries %d max_loop_tries %d' % (self.max_command_tries,
                                                                 self.max_loop_tries))
        self.use_inverter_time = to_bool(aurora_dict.get('use_inverter_time',
                                                         False))
        if self.use_inverter_time:
            log.debug('   inverter time will be used to timestamp data')
        else:
            log.debug('   WeeWX system time will be used to timestamp data')

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

        # Build the manifest of readings to be included in the loop packet.
        # Build the Aurora reading to loop packet field map.
        (self.field_map, self.manifest) = self._build_map_manifest(aurora_dict)
        log.info('sensor_map=%s' % (self.field_map,))
        # build a 'none' packet to use when the inverter is offline
        self.none_packet = {}
        for src in self.manifest:
            self.none_packet[src] = None

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
                        log.debug("genLoopPackets: received raw data packet: %s" % raw_packet)
                    # process raw data and return a dict that can be used as a
                    # LOOP packet
                    packet = self.process_raw_packet(raw_packet)
                    # add in/set fields that require special consideration
                    if packet:

                        # dateTime - either be system time or inverter time
                        if not self.use_inverter_time:
                            # we are NOT using the inverter timestamp so set
                            # the packet timestamp to the current system time
                            packet['dateTime'] = _ts
                        else:
                            # we ARE using the inverter timestamp so set the
                            # packet timestamp to the current inverter time
                            packet['dateTime'] = packet['timeDate']

                        # usUnits - set to METRIC
                        packet['usUnits'] = weewx.METRIC

                        # energy - derive from dayEnergy
                        # dayEnergy is cumulative by day but we need
                        # incremental values so we need to calculate it based
                        # on the last cumulative value
                        packet['energy'] = self.calculate_energy(packet['dayEnergy'],
                                                                 self.last_energy)
                        self.last_energy = packet['dayEnergy'] if 'dayEnergy' in packet else None

                        if weewx.debug >= 2:
                            log.debug("genLoopPackets: received loop packet: %s" % packet)
                        yield packet
                    # wait until its time to poll again
                    if weewx.debug >= 2:
                        log.debug("genLoopPackets: Sleeping")
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
        for reading in self.manifest:
            # get the reading
            _response = self.do_cmd(reading)
            # If the inverter is running set the running property and save the
            # data. If the inverter is asleep set the running property only,
            # there will be no data.
            if _response.global_state == 6:
                # inverter is running
                self.running = True
                _packet[reading] = _response.data
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
        for dest, src in iteritems(self.field_map):
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
            else:
                _packet[dest] = None
        return _packet

    def do_cmd(self, command, payload=None, globall=0):
        """Send a command to the inverter and return the decoded response.

        Inputs:
            command: One of the commands from the command vocabulary of the
                     AuroraInverter object, AuroraInverter.commands. String.
            globall: Global (globall=1) or Module (globall=0) measurements.

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
            # if it's None the inverter is asleep (or otherwise unavailable) so
            # raise a NotImplementedError
            raise NotImplementedError("Method 'getTime' not implemented")
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

        # check if the inverter is on line, we will get None if the inverter
        # cannot be contacted
        _time_ts = self.do_cmd('getTimeDate').data
        # if the inverter is not there then raise a NotImplementedError
        # otherwise continue
        if _time_ts is None:
            raise NotImplementedError("Method 'setTime' not implemented")
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
                # something went wrong, it's not fatal but we need to log the
                # failure and the returned states
                log.error("Inverter time was not set")
                log.error("  ***** transmission state=%d (%s)" % (_response.transmission_state,
                                                                  AuroraDriver.TRANSMISSION[_response.transmission_state]))
                log.error("  ***** global state=%d (%s)" % (_response.global_state,
                                                            AuroraDriver.GLOBAL[_response.global_state]))

    def get_cumulated_energy(self, period=None):
        """Get 'cumulated' energy readings.

        Returns a dict with value for one or more periods. Valid dict keys are:
            'day'
            'week'
            'month'
            'year'
            'total'
            'partial'

        Input:
            period: Specify a single period for which cumulated energy is
                    required. If None or omitted cumulated values for all
                    periods will be returned. String, must be one of the above
                    dict keys, may be None. Default is None.
        Returns:
            Dict of requested cumulated energy values. If an invalid period is
            passed in then None is returned.
        """

        manifest = {'day': 'dayEnergy',
                    'week': 'weekEnergy',
                    'month': 'monthEnergy',
                    'year': 'yearEnergy',
                    'total': 'totalEnergy',
                    'partial': 'partialEnergy'
                    }

        _energy = {}
        if period is None:
            for _period, _reading in iteritems(manifest):
                _energy[_period] = self.do_cmd(_reading).data
        elif period in manifest:
            _energy[period] = self.do_cmd(period).data
        else:
            _energy = None
        return _energy

    def get_last_alarms(self):
        """Get the last four alarms."""

        return self.do_cmd('getLastAlarms').data

    def get_dsp(self):
        """Get DSP data."""

        manifest = dict((k, v) for k, v in iteritems(self.inverter.commands) if v['cmd'] == 59)

        _dsp = {}
        for reading, params in iteritems(manifest):
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

    def _build_map_manifest(self, inverter_dict):
        """Build a field map and command manifest.

        Build a dict mapping Aurora readings to loop packet fields. Also builds
        a dict of commands to be used to obtain raw loop data from the
        inverter.

        Input:
            inverter_dict: An inverter config dict

        Returns:
            Tuple consisting of (field_map, manifest) where:

            field_map:  A is a dict mapping Aurora readings to loop packet
                        fields.
            manifest:   A dict of inverter readings and their associated
                        command parameters to be used as the raw data used as
                        the basis for a loop packet.
        """

        _manifest = []
        _field_map = {}
        _field_map_config = inverter_dict.get('sensor_map', AuroraDriver.DEFAULT_SENSOR_MAP)
        for dest, src in iteritems(_field_map_config):
            if src in self.inverter.commands:
                _manifest.append(src)
                _field_map[dest] = src
            else:
                log.debug("Invalid inverter data field '%s' specified in config file. Field ignored." % src)
        return _field_map, _manifest


# ============================================================================
#                               class Aurora
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
        log.debug("Opened serial port %s; baud %d; timeout %.2f" % (self.port,
                                                                    self.baudrate,
                                                                    self.timeout))

    def close_port(self):
        """Close a serial port."""

        try:
            # This will cancel any pending loop:
            self.write('\n')
        except:
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

    def read(self, bytes=8):
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
            _buffer = self.serial_port.read(bytes)
        except serial.serialutil.SerialException as e:
            log.error("SerialException on read.")
            log.error("  ***** %s" % e)
            log.error("  ***** Is there a competing process running??")
            # re-raise as a WeeWX error I/O error:
            raise weewx.WeeWxIOError(e)
        n = len(_buffer)
        if n != bytes:
            raise weewx.WeeWxIOError("Expected to read %d bytes; got %d instead" % (bytes,
                                                                                    n))
        return _buffer

    def send_cmd_with_crc(self, command, payload=None, globall=0,
                          address=2, max_tries=3):
        """Send a command with CRC to the inverter and return the response.

        Inputs:
            command:    The inverter command being issued. String.
            payload:    Data to be sent to the inverter as part of the command.
                        Will occupy part or all of bytes 2,3,4,5,6 and 7.
                        Currently only used by setTime. String.
            globall:
            address:    The inverter address to be used, normally 2.
            max_tries:  The maximum number of attempts to send the data before
                        an error is raised.

        Returns:
            The decoded inverter response to the command as a Response Tuple.
        """

        # get the applicable command codes etc
        if self.commands[command]['sub'] is not None:
            # we have a sub-command
            command_t = (address, self.commands[command]['cmd'],
                         self.commands[command]['sub'], globall)
        elif payload is not None:
            # we have no sub-command, but we have a payload
            command_t = (address, self.commands[command]['cmd']) + tuple([ord(b) for b in payload])
        else:
            # no sub-command or payload
            command_t = (address, self.commands[command]['cmd'])
        # assemble our command
        s = struct.Struct('%dB' % len(command_t))
        _b = s.pack(*[b for b in command_t])
        # pad the command to 8 bytes
        _b_padded = self.pad(_b, 8)
        # add the CRC
        _data_with_crc = _b_padded + self.word2struct(self.crc16(_b_padded))
        # now send the assembled command retrying up to max_tries times
        for count in range(max_tries):
            if weewx.debug >= 2:
                log.debug("send_cmd_with_crc: sent %s" % format_byte_to_hex(_data_with_crc))
            try:
                self.write(_data_with_crc)
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
                    log.info("CRC error on try #%d. Cycling port." % (count + 1,))
                    # close the port, wait 0.2 sec then open the port
                    self.close_port()
                    time.sleep(0.2)
                    self.open_port()
                    # log that the port has been cycled
                    log.info("Port cycle complete.")
                else:
                    log.info("CRC error on try #%d." % (count + 1,))
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
                        log.debug("send_cmd_with_crc: try #%d unsuccessful... cycling port" % (count + 1,))
                    # close the port, wait 0.2 sec then open the port
                    self.close_port()
                    time.sleep(0.2)
                    self.open_port()
                    # log that the port has been cycled
                    if weewx.debug >= 2:
                        log.debug("send_cmd_with_crc: port cycle complete.")
                else:
                    if weewx.debug >= 2:
                        log.debug("send_cmd_with_crc: try #%d unsuccessful... sleeping" % (count + 1,))
                    time.sleep(self.wait_before_retry)
                if weewx.debug >= 2:
                    log.debug("send_cmd_with_crc: retrying")
            else:
                if weewx.debug >= 2:
                    log.debug("send_cmd_with_crc: try #%d unsuccessful" % (count + 1,))
        log.debug("Unable to send or receive data to/from the inverter")
        raise weewx.WeeWxIOError("Unable to send or receive data to/from the inverter")

    def read_with_crc(self, bytes=8):
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
        _response = self.read(bytes=bytes)
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
        _format = ''.join(['B' for b in range(len(buf))])
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

    @staticmethod
    def pad(buf, size):
        """Pad a string with nulls.

        Pad a string with nulls to make it a given size. If the string to be
        padded is longer than size then an exception is raised.

        Inputs:
            buff: The string to be padded
            size: The length of the padded string

        Returns:
            A padded string of length size.
        """

        if len(buf) > size:
            raise DataFormatError("pad: string to be padded must be <= %d characters in length" % size)
        return buf + b'\x00' * (size - len(buf))

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
#                          Class AuroraConfEditor
# ============================================================================


class AuroraConfEditor(weewx.drivers.AbstractConfEditor):

    @property
    def default_stanza(self):
        return """
[Aurora]
    # This section is for the Power One Aurora series of inverters.

    # The inverter model, e.g., Aurora PVI-6000, Aurora PVI-5000
    model = INSERT_MODEL_HERE

    # Serial port such as /dev/ttyS0, /dev/ttyUSB0, or /dev/cua0
    port = %s

    # inverter address, usually 2
    address = %s

    # The driver to use:
    driver = user.aurora
""" % (AuroraInverter.DEFAULT_PORT, AuroraInverter.DEFAULT_ADDRESS)

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

    def modify_config(self, config_dict):

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
# The CRC bytes are stripped away by the Aurora class class when validating the
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


# ============================================================================
#                          Main Entry for Testing
# ============================================================================

# Define a main entry point for basic testing without the WeeWX engine and
# service overhead. To invoke this driver without WeeWX:
#
# $ sudo PYTHONPATH=/home/weewx/bin python /home/weewx/bin/user/aurora.py --option
#
# where option is one of the following options:
#   --help          - display driver command line help
#   --version       - display driver version
#   --gen-packets   - generate LOOP packets indefinitely
#   --get-status    - display inverter status
#   --get-readings  - display current inverter readings
#   --get-time      - display inverter time
#   --get-info      - display inverter information
#


if __name__ == '__main__':

    # python imports
    import optparse
    import sys
    import time

    # WeeWX imports
    import weecfg
    import weewx.units

    from weeutil.weeutil import timestamp_to_string

    def sort(rec):
        return ", ".join(["%s: %s" % (k, rec.get(k)) for k in sorted(rec,
                                                                     key=str.lower)])

    usage = """sudo PYTHONPATH=/home/weewx/bin python
               /home/weewx/bin/user/%prog [--option]"""

    syslog.openlog('aurora', syslog.LOG_PID | syslog.LOG_CONS)
    syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--config', dest='config_path', type=str,
                      metavar="CONFIG_FILE",
                      help="Use configuration file CONFIG_FILE.")
    parser.add_option('--version', dest='version', action='store_true',
                      help='Display driver version.')
    parser.add_option('--gen-packets', dest='gen', action='store_true',
                      help='Output LOOP packets indefinitely.')
    parser.add_option('--get-status', dest='status', action='store_true',
                      help='Display inverter status.')
    parser.add_option('--get-info', dest='info', action='store_true',
                      help='Display inverter information.')
    parser.add_option('--get-readings', dest='readings', action='store_true',
                      help='Display current inverter readings.')
    parser.add_option('--get-time', dest='get_time', action='store_true',
                      help='Display current inverter date-time.')
    parser.add_option('--set-time', dest='set_time', action='store_true',
                      help='Set inverter date-time to the current system date-time.')
    (options, args) = parser.parse_args()

    if options.version:
        print(("Aurora driver version %s" % DRIVER_VERSION))
        exit(0)

    # get config_dict to use
    config_path, config_dict = weecfg.read_config(options.config_path, args)
    print(("Using configuration file %s" % config_path))

    # get a config dict for the inverter
    aurora_dict = config_dict.get('Aurora', None)
    # get an AuroraDriver object
    if aurora_dict is not None:
        inverter = AuroraDriver(aurora_dict)
    else:
        exit_str = "'Aurora' stanza not found in config file '%s'. Exiting." % config_path
        sys.exit(exit_str)

    if options.gen:
        while True:
            for packet in inverter.genLoopPackets():
                print(("LOOP:  ", timestamp_to_string(packet['dateTime']), sort(packet)))
    elif options.status:
        response_rt = inverter.do_cmd('getState')
        print()
        print(("%s Status:" % inverter.model))
        if response_rt.transmission_state is not None:
            print(("%22s: %d (%s)" % ("Transmission state",
                                     response_rt.transmission_state,
                                     AuroraDriver.TRANSMISSION[response_rt.transmission_state])))
        else:
            print("Transmission state: None (---)")
        if response_rt.global_state is not None:
            print(("%22s: %d (%s)" % ("Global state",
                                     response_rt.global_state,
                                     AuroraDriver.GLOBAL[response_rt.global_state])))
        else:
            print("      Global state: None (---)")
        if response_rt.data is not None and response_rt.data[0] is not None:
            print(("%22s: %d (%s)" % ("Inverter state",
                                     response_rt.data[0],
                                     AuroraDriver.INVERTER[response_rt.data[0]])))
        else:
            print("    Inverter state: None (---)")
        if response_rt.data is not None and response_rt.data[1] is not None:
            print(("%22s: %d (%s)" % ("DcDc1 state",
                                     response_rt.data[1],
                                     AuroraDriver.DCDC[response_rt.data[1]])))
        else:
            print("       DcDc1 state: None (---)")
        if response_rt.data is not None and response_rt.data[2] is not None:
            print(("%22s: %d (%s)" % ("DcDc2 state",
                                     response_rt.data[2],
                                     AuroraDriver.DCDC[response_rt.data[2]])))
        else:
            print("       DcDc2 state: None (---)")
        if response_rt.data is not None and response_rt.data[3] is not None:
            print(("%22s: %d (%s)[%s]" % ("Alarm state",
                                         response_rt.data[3],
                                         AuroraDriver.ALARM[response_rt.data[3]]['description'],
                                         AuroraDriver.ALARM[response_rt.data[3]]['code'])))
        else:
            print("       Alarm state: None (---)")

    elif options.info:
        print()
        print("%s Information:" % inverter.model)
        print("%21s: %s" % ("Part Number", inverter.part_number))
        print("%21s: %s" % ("Version", inverter.version))
        print("%21s: %s" % ("Serial Number", inverter.serial_number))
        print("%21s: %s" % ("Manufacture Date", inverter.manufacture_date))
        print("%21s: %s" % ("Firmware Release", inverter.firmware_rel))
    elif options.readings:
        print()
        print("%s Current Readings:" % inverter.model)
        print("-----------------------------------------------")
        print("Grid:")
        print("%29s: %sV" % ('Voltage', inverter.do_cmd('getGridV').data))
        print("%29s: %sA" % ('Current', inverter.do_cmd('getGridC').data))
        print("%29s: %sW" % ('Power', inverter.do_cmd('getGridP').data))
        print("%29s: %sHz" % ('Frequency', inverter.do_cmd('getFrequency').data))
        print("%29s: %sV" % ('Average Voltage', inverter.do_cmd('getGridAvV').data))
        print("%29s: %sV" % ('Neutral Voltage', inverter.do_cmd('getGridNV').data))
        print("%29s: %sV" % ('Neutral Phase Voltage', inverter.do_cmd('getGridNPhV').data))
        print("-----------------------------------------------")
        print("String 1:")
        print("%29s: %sV" % ('Voltage', inverter.do_cmd('getStr1V').data))
        print("%29s: %sA" % ('Current', inverter.do_cmd('getStr1C').data))
        print("%29s: %sW" % ('Power', inverter.do_cmd('getStr1P').data))
        print("-----------------------------------------------")
        print("String 2:")
        print("%29s: %sV" % ('Voltage', inverter.do_cmd('getStr2V').data))
        print("%29s: %sA" % ('Current', inverter.do_cmd('getStr2C').data))
        print("%29s: %sW" % ('Power', inverter.do_cmd('getStr2P').data))
        print("-----------------------------------------------")
        print("Inverter:")
        print("%29s: %sV" % ('Voltage (DC/DC Booster)', inverter.do_cmd('getGridDcV').data))
        print("%29s: %sHz" % ('Frequency (DC/DC Booster)', inverter.do_cmd('getGridDcFreq').data))
        print("%29s: %sC" % ('Inverter Temp', inverter.do_cmd('getInverterT').data))
        print("%29s: %sC" % ('Booster Temp', inverter.do_cmd('getBoosterT').data))
        print("%29s: %sW" % ("Today's Peak Power", inverter.do_cmd('getDayPeakP').data))
        print("%29s: %sW" % ("Lifetime Peak Power", inverter.do_cmd('getPeakP').data))
        print("%29s: %sWh" % ("Today's Energy", inverter.do_cmd('getDayEnergy').data))
        print("%29s: %sWh" % ("This Weeks's Energy", inverter.do_cmd('getWeekEnergy').data))
        print("%29s: %sWh" % ("This Month's Energy", inverter.do_cmd('getMonthEnergy').data))
        print("%29s: %sWh" % ("This Year's Energy", inverter.do_cmd('getYearEnergy').data))
        print("%29s: %sWh" % ("Partial Energy", inverter.do_cmd('getPartialEnergy').data))
        print("%29s: %sWh" % ("Lifetime Energy", inverter.do_cmd('getTotalEnergy').data))
        print()
        print("%29s: %sV" % ('Bulk Voltage', inverter.do_cmd('getBulkV').data))
        print("%29s: %sV" % ('Bulk DC Voltage', inverter.do_cmd('getBulkDcV').data))
        print("%29s: %sV" % ('Bulk Mid Voltage', inverter.do_cmd('getBulkMidV').data))
        print()
        print("%29s: %sMOhms" % ('Insulation Resistance', inverter.do_cmd('getIsoR').data))
        print()
        print("%29s: %sA" % ('Leakage Current(Inverter)', inverter.do_cmd('getLeakC').data))
        print("%29s: %sA" % ('Leakage Current(Booster)', inverter.do_cmd('getLeakDcC').data))

    elif options.get_time:
        inverter_ts = inverter.getTime()
        _error = inverter_ts - time.time()
        print()
        print("Inverter date-time is %s" % (timestamp_to_string(inverter_ts)))
        print("    Clock error is %.3f seconds (positive is fast)" % _error)
    elif options.set_time:
        inverter_ts = inverter.getTime()
        _error = inverter_ts - time.time()
        print()
        print("Current inverter date-time is %s" % (timestamp_to_string(inverter_ts)))
        print("    Clock error is %.3f seconds (positive is fast)" % _error)
        print()
        print("Setting time...")
        inverter.setTime()
        inverter_ts = inverter.getTime()
        _error = inverter_ts - time.time()
        print()
        print("Updated inverter date-time is %s" % (timestamp_to_string(inverter_ts)))
        print("    Clock error is %.3f seconds (positive is fast)" % _error)
