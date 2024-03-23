"""
aurora.py

A WeeWX driver for Power One Aurora inverters.

Copyright (C) 2016-2024 Gary Roderick                  gjroderick<at>gmail.com

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program.  If not, see https://www.gnu.org/licenses/.

Version: 0.7.3                                        Date: 23 March 2024

Revision History
    23 March 2024       v0.7.3
        - fix incorrect exception name
    23 January 2024     v0.7.2
        - refactor power and energy unit/group config to align with existing
          WeeWX equivalents
    22 January 2024     v0.7.1
        - installer change only
    5 January 2024      v0.7.0
        - now WeeWX v5 compatible
        - python v3.6 and earlier no longer supported
        - significant refactoring to move all intimate inverter knowledge out
          of the driver class (class AuroraDriver) into class AuroraInverter
        - added support for weectl device
        - added class DirectAurora to better support running the driver
          directly or via weectl device
        - driver output when running directly or via weectl device now supports
          unit conversion and formatting of displayed data
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
        - AuroraDriver execute_cmd_with_crc() method now accepts additional
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

1.  Copy this file to ~/weewx-data/bin/user.

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

    $ PYTHONPATH=/home/user_account/weewx-data/bin python3 /home/user_account/weewx-data/bin/user/aurora.py --help
"""


# Python imports
import logging
import serial
import struct
import time

# WeeWX imports
import weeutil
import weewx.defaults
import weewx.drivers
import weewx.units
from weeutil.weeutil import bcolors, timestamp_to_string

# get a logger object
log = logging.getLogger(__name__)

# our name and version number
DRIVER_NAME = 'Aurora'
DRIVER_VERSION = '0.7.2'

# config defaults
DEFAULT_POLL_INTERVAL = 20
DEFAULT_COMMAND_DELAY = 0.05
DEFAULT_BAUDRATE = 19200
DEFAULT_READ_TIMEOUT = 2
DEFAULT_WRITE_TIMEOUT = 2
DEFAULT_MAX_COMMAND_TRIES = 3
DEFAULT_ADDRESS = 2
DEFAULT_WAIT_BEFORE_RETRY = 1


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

    # set default formats and labels for megawatt hours
    weewx.units.default_unit_format_dict['megawatt_hour'] = '%.1f'
    weewx.units.default_unit_label_dict['megawatt_hour'] = ' MWh'

    # define conversion functions for energy
    weewx.units.conversionDict['watt_hour'] = {'kilowatt_hour': lambda x: x / 1000.0,
                                               'megawatt_hour': lambda x: x / 1000000.0}
    weewx.units.conversionDict['kilowatt_hour'] = {'watt_hour': lambda x: x * 1000.0,
                                                   'megawatt_hour': lambda x: x / 1000.0}
    weewx.units.conversionDict['megawatt_hour'] = {'watt_hour': lambda x: x * 1000000.0,
                                                   'kilowatt_hour': lambda x: x * 1000.0}

    # set default formats and labels for mega watts
    weewx.units.default_unit_format_dict['megawatt'] = '%.1f'
    weewx.units.default_unit_label_dict['megawatt'] = ' MW'

    # define conversion functions for energy
    weewx.units.conversionDict['watt'] = {'kilowatt': lambda x: x / 1000.0,
                                          'megawatt': lambda x: x / 1000000.0}
    weewx.units.conversionDict['kilowatt'] = {'watt': lambda x: x * 1000.0,
                                              'megawatt': lambda x: x / 1000.0}
    weewx.units.conversionDict['megawatt'] = {'watt': lambda x: x * 1000000.0,
                                              'kilowatt': lambda x: x * 1000.0}

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
    return AuroraDriver(**config_dict[DRIVER_NAME])


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

    # available DSP fields
    DSP_FIELDS = ['grid_voltage', 'grid_current', 'grid_power', 'frequency',
                  'bulk_voltage', 'leak_dc_current', 'leak_current',
                  'string1_power', 'string2_power', 'inverter_temp',
                  'booster_temp', 'string1_voltage', 'string1_current',
                  'string2_voltage', 'string2_current', 'grid_dc_voltage',
                  'grid_dc_frequency', 'isolation_resistance',
                  'bulk_dc_voltage', 'grid_average_voltage',
                  'bulk_mid_voltage', 'peak_power', 'day_peak_power',
                  'grid_voltage_neutral', 'grid_voltage_neutral_phase',
                  'time_date', 'day_energy', 'week_energy', 'month_energy',
                  'year_energy', 'total_energy', 'partial_energy'
                  ]
    # default sensor map, format:
    #   loop packet field: raw data field
    DEFAULT_SENSOR_MAP = {'inverterDateTime': 'time_date',
                          'string1Voltage': 'string1_voltage',
                          'string1Current': 'string1_current',
                          'string1Power': 'string1_power',
                          'string2Voltage': 'string2_voltage',
                          'string2Current': 'string2_current',
                          'string2Power': 'string2_power',
                          'gridVoltage': 'grid_voltage',
                          'gridCurrent': 'grid_current',
                          'gridPower': 'grid_power',
                          'gridFrequency': 'frequency',
                          'inverterTemp': 'inverter_temp',
                          'boosterTemp': 'booster_temp',
                          'bulkVoltage': 'bulk_voltage',
                          'isoResistance': 'isolation_resistance',
                          'bulkmidVoltage': 'bulk_mid_voltage',
                          'bulkdcVoltage': 'bulk_dc_voltage',
                          'leakdcCurrent': 'leak_dc_current',
                          'leakCurrent': 'leak_current',
                          'griddcVoltage': 'grid_dc_voltage',
                          'gridavgVoltage': 'grid_average_voltage',
                          'gridnVoltage': 'grid_voltage_neutral',
                          'griddcFrequency': 'grid_dc_frequency',
                          'dayEnergy': 'day_energy',
                          'weekEnergy': 'week_energy',
                          'monthEnergy': 'month_energy',
                          'yearEnergy': 'year_energy',
                          'totalEnergy': 'total_energy',
                          'partialEnergy': 'partial_energy'
                          }

    def __init__(self, **inverter_dict):
        """Initialise an object of type AuroraDriver."""

        # model
        self.model = inverter_dict.get('model', 'Aurora')
        log.info('%s driver version is %s', self.model, DRIVER_VERSION)
        # serial comms options
        try:
            port = inverter_dict.get('port')
        except KeyError:
            raise Exception("Required parameter 'port' was not specified.")
        baudrate = int(inverter_dict.get('baudrate', DEFAULT_BAUDRATE))
        # get the read timeout to be used, we need to handle the legacy timeout
        # config option if it was used
        _legacy_timeout = inverter_dict.get('timeout')
        _read_timeout = inverter_dict.get('read_timeout')
        if _read_timeout is not None:
            read_timeout = float(_read_timeout)
        elif _legacy_timeout is not None:
            read_timeout = float(_legacy_timeout)
        else:
            read_timeout = DEFAULT_READ_TIMEOUT
        write_timeout = float(inverter_dict.get('write_timeout', DEFAULT_WRITE_TIMEOUT))
        wait_before_retry = float(inverter_dict.get('wait_before_retry', DEFAULT_WAIT_BEFORE_RETRY))
        command_delay = float(inverter_dict.get('command_delay', DEFAULT_COMMAND_DELAY))

        log.info("   port: '%s' baudrate: %d read_timeout: %.1f write_timeout: %.1f",
                 port,
                 baudrate,
                 read_timeout,
                 write_timeout)
        log.info('   wait_before_retry: %.1f command_delay: %.2f',
                 wait_before_retry,
                 command_delay)
        # driver options
        max_command_tries = int(inverter_dict.get('max_command_tries',
                                                  DEFAULT_MAX_COMMAND_TRIES))
        # get the inverter poll interval to be used, we need to handle the
        # legacy loop_interval config option if it was used
        _legacy_loop_interval = inverter_dict.get('loop_interval')
        _poll_interval = inverter_dict.get('poll_interval')
        if _poll_interval is not None:
            self.poll_interval = int(_poll_interval)
        elif _legacy_loop_interval is not None:
            self.poll_interval = int(_legacy_loop_interval)
        else:
            self.poll_interval = DEFAULT_POLL_INTERVAL
        address = int(inverter_dict.get('address', DEFAULT_ADDRESS))
        # get the sensor map
        self.sensor_map = inverter_dict.get('sensor_map',
                                            AuroraDriver.DEFAULT_SENSOR_MAP)
        log.info("   inverter address: %d poll_interval: %d seconds",
                 address,
                 self.poll_interval)
        log.info('   max_command_tries: %d ', max_command_tries)
        log.info('   sensor_map: %s', self.sensor_map)
        # get an AuroraInverter object
        self.inverter = AuroraInverter(port,
                                       baudrate=baudrate,
                                       address=address,
                                       read_timeout=read_timeout,
                                       write_timeout=write_timeout,
                                       wait_before_retry=wait_before_retry,
                                       command_delay=command_delay,
                                       max_tries=max_command_tries)
        # initialise last energy value
        self.last_energy = None
        # build a 'none' packet to use when the inverter is offline, first
        # create an empty dict
        self.none_packet = {}
        # now iterate over the fields we expect entering their 'none packet'
        # values in the dict
        for field in self.sensor_map.values():
            self.none_packet[field] = None

    def openPort(self):
        """Open the connection to the inverter."""

        self.inverter.open_port()

    def closePort(self):
        """Close the connection to the inverter."""

        self.inverter.close_port()

    def genLoopPackets(self):
        """Generator function that returns 'loop' packets.

        Poll the inverter every self.poll_interval seconds and generate a
        loop packet. Sleep between loop packets.
        """

        while int(time.time()) % self.poll_interval != 0:
            time.sleep(0.2)
        while True:
            # get the current time as timestamp
            _ts = int(time.time())
            # log that we are about to poll for data
            if weewx.debug >= 2:
                log.debug("genLoopPackets: polling inverter for data")

            # poll the inverter and obtain a packet of inverter data
            # if the inverter is known to be running then just get the packet
            if self.inverter.is_running:
                _inverter_packet = self.get_dsp_packet()
            else:
                # The inverter isn't running, but the last check may have been
                # up to poll_interval seconds ago and the inverter may have
                # since started running. Get the inverter state, this will
                # force an update of the inverter is_running property.
                try:
                    _state = self.inverter.get_state()
                except weewx.WeeWxIOError:
                    pass
                # now try to get a data packet from the inverter, if we cannot
                # get a data packet use a 'None' packet
                if self.inverter.is_running:
                    # the inverter is running so get a data packet
                    _inverter_packet = self.get_dsp_packet()
                else:
                    # the inverter is not running so use a 'None' packet
                    _inverter_packet = self.none_packet

            # log the inverter data
            if weewx.debug >= 2:
                log.debug("genLoopPackets: received inverter data packet: %s",
                          weeutil.weeutil.to_sorted_string(_inverter_packet))
            # create a limited loop packet by mapping the inverter data as per
            # the sensor map
            packet = self.map_inverter_packet(_inverter_packet)
            # log the inverter data
            if weewx.debug >= 2:
                log.debug("genLoopPackets: mapped inverter data packet: %s",
                          weeutil.weeutil.to_sorted_string(packet))
            # now add in/set any fields that require special consideration
            if packet:
                # dateTime, use our timestamp from earlier
                packet['dateTime'] = _ts
                # usUnits - set to METRIC
                packet['usUnits'] = weewx.METRIC
                # energy - the per-period energy value. The inverter reports
                # dayEnergy which is cumulative by day, but we need a
                # per-period value. So calculate the per-period value as the
                # difference between the current and previous dayEnergy values.
                if 'dayEnergy' in packet:
                    packet['energy'] = self.calculate_energy(packet['dayEnergy'],
                                                             self.last_energy)
                    self.last_energy = packet['dayEnergy']
                else:
                    # dayEnergy is not in the packet so we should not add
                    # energy to the packet, even with a None value. However, we
                    # need to set the last_energy property None.
                    self.last_energy = None
                # log the loop packet
                if weewx.debug >= 2:
                    log.debug("genLoopPackets: generated loop packet: %s",
                              weeutil.weeutil.to_sorted_string(packet))
                # yield the packet
                yield packet
            # wait until it's time to poll again
            if weewx.debug >= 2:
                log.debug("genLoopPackets: sleeping")
            while time.time() < _ts + self.poll_interval:
                time.sleep(0.2)

    def get_dsp_packet(self):
        """Get a loop packet from the inverter."""

        # the inverter 'API' returns Metric values, so create a suitable packet
        # to save the inverter data
        _packet = {'usUnits': weewx.METRIC}
        # iterate over the list of available DSP fields and attempt to obtain
        # each field from the inverter
        for dsp_field in self.DSP_FIELDS:
            # get the field value, be prepared to catch a weewx.WeeWxIOError if
            # the field cannot be obtained from the inverter
            if self.inverter.is_running:
                try:
                    _packet[dsp_field] = self.inverter.get_field(dsp_field)
                except weewx.WeeWxIOError:
                    # for some reason we could not get the field, most likely
                    # because the inverter is asleep, but it could otherwise be
                    # off-line. In any case we should ignore the exception and
                    # continue.
                    continue
            else:
                # the inverter is not running, most likely asleeep, so there is
                # no point continuing, break out of the loop so we can return
                break
        # carry out any special processing on the packet
        self.process_inverter_packet(_packet)
        # finally return the packet
        return _packet

    @staticmethod
    def process_inverter_packet(inverter_packet):
        """Apply any special processing to an inverter data packet.

        Input:
            inverter_packet: A dict holding unmapped inverter data.

        Returns:
            Nothing, modifies (if required) inverter_packet in place.
        """

        # isoR is reported in Mohms, we want ohms
        if 'isolation_resistance' in inverter_packet:
            try:
                inverter_packet['isolation_resistance'] *= 1000000.0
            except TypeError:
                # field is not numeric so leave it
                pass

    def map_inverter_packet(self, inverter_packet):
        """Map inverter data packet fields to WeeWX fields.

        Input:
            inverter_packet: A dict holding unmapped inverter data.

        Returns:
            A limited WeeWX loop packet of mapped raw inverter data.
        """

        # create an empty dict to hold the mapped data
        _packet = {}
        # iterate over each sensor map entry
        for weewx_field, inverter_field in self.sensor_map.items():
            # does the inverter (source) field exist
            if inverter_field in inverter_packet:
                # the inverter (source) field exists so map it to the
                # applicable WeeWX field
                _packet[weewx_field] = inverter_packet[inverter_field]
        # return the mapped data
        return _packet

    def getTime(self):
        """Get inverter system time.

        During startup WeeWX uses the 'console' time if available. The way the
        driver tells WeeWX the 'console' time is not available is by raising a
        NotImplementedError error when getTime is called. This is what is
        normally done for stations that do not keep track of time. In the case
        of the Aurora inverter, when it is asleep we cannot get the time so in
        that case raise a NotImplementedError, but if the inverter is awake then
        return the time.

        Returns:
            An epoch timestamp representing the inverter date-time.
        """

        # get the current inverter time, wrap in a try .. except in case we get
        # an exception due to the inverter sleeping
        try:
            _time_ts = self.inverter.get_time()
        except weewx.WeeWxIOError:
            # If we have a weewx.WeeWxIOError the inverter could not be
            # contacted or did not return valid data, most likely the inverter
            # is asleep. Assume the inverter is asleep, log it and raise a
            # NotImplementedError
            log.error("getTime: Could not contact inverter, it may be asleep")
            raise NotImplementedError("Could not contact inverter, it may be asleep")
        except Exception as e:
            # some other exception occurred, log it and raise it
            log.error("getTime: Unexpected exception")
            log.error("  ***** %s", e)
            raise
        else:
            # we received a response, but is it a valid timestamp or None
            if _time_ts is None:
                # a valid response was received from the inverter, but it could
                # not be decoded. Log it and continue, we will return the None
                # value.
                log.debug("getTime: Invalid timestamp received")
            return _time_ts

    def setTime(self):
        """Set inverter system time.

        The WeeWX StdTimeSync service will periodically check the inverter's
        internal clock and use setTime() to adjust the inverter's clock to
        match the WeeWX system time if required. As the inverter's clock cannot
        be read or set when the inverter is asleep, setTime() will take one of
        two actions. If the inverter is asleep a NotImplementedError is raised,
        this will cause WeeWX to continue normal operation. If the inverter is
        awake the time is set.
        """

        # get the current WeeWX system time, offset by 2 seconds to allow for
        # rounding (0.5) and the delay in the command being issued and acted on
        # by the inverter (1.5)
        _ts = int(time.time() + 2)
        # call the AuroraDriver set_time method using the timestamp just
        # calculated and obtain the response, be prepared to catch the
        # WeeWxIOError raised if the inverter is asleep
        try:
            _response = self.inverter.set_time(_ts)
        except weewx.WeeWXIOError as e:
            raise NotImplementedError(e)
        except Exception as e:
            # some other exception occurred, log it and raise it
            log.error("setTime: Unexpected exception")
            log.error("  ***** %s", e)
            raise
        else:
            # If the inverter time was successfully set, set_time() will return
            # True, otherwise it will return False. Use the response to log the
            # result.
            if _response:
                # set_time() completed successfully so log it
                log.info("Inverter time set")
            else:
                # something went wrong and the inverter time was not set; it's
                # not fatal, but we need to log the failure. Assume any errors
                # were logged further down the chain, so we just simply log the
                # failure.
                log.error("Inverter time was not set")

    @property
    def hardware_name(self):
        """The name by which this hardware is known."""

        return self.model

    @staticmethod
    def calculate_energy(newtotal, oldtotal):
        """Calculate energy differential given two cumulative measurements."""

        delta = None
        if newtotal is not None and oldtotal is not None and newtotal >= oldtotal:
            delta = newtotal - oldtotal
        return delta


# ============================================================================
#                            class AuroraInverter
# ============================================================================

class AuroraInverter(object):
    """Class to support serial comms with an Aurora PVI-6000 inverter.

    An AuroraInverter object knows how to:
    - communicate directly with the inverter
    - utilise the 'inverter API' to get inverter status/set inverter options
    """

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
    ALARM = {0:  {'description': 'No Alarm',          'code': 'No alarm code'},
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

    def __init__(self, port, baudrate=DEFAULT_BAUDRATE, address=DEFAULT_ADDRESS,
                 read_timeout=DEFAULT_READ_TIMEOUT, write_timeout=DEFAULT_WRITE_TIMEOUT,
                 wait_before_retry=DEFAULT_WAIT_BEFORE_RETRY, command_delay=0.05, max_tries=3):
        """Initialise an AuroraInverter object."""

        self.port = port
        self.baudrate = baudrate
        self.address = address
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.wait_before_retry = wait_before_retry
        self.command_delay = command_delay
        self.max_tries = max_tries

        # Inverter commands that I know about. Each entry contains the command
        # code to be sent to the inverter as well as the decode function to
        # decode the returned data.
        self.commands = {
            'state_request':    {'cmd_code': 50, 'decode_fn': self._dec_state},
            'part_number':      {'cmd_code': 52, 'decode_fn': self._dec_ascii},
            'version':          {'cmd_code': 58, 'decode_fn': self._dec_ascii_and_state},
            'measure':          {'cmd_code': 59, 'decode_fn': self._dec_float},
            'serial_number':    {'cmd_code': 63, 'decode_fn': self._dec_ascii},
            'manufacture_date': {'cmd_code': 65, 'decode_fn': self._dec_week_year},
            'read_time_date':   {'cmd_code': 70, 'decode_fn': self._dec_ts},
            'set_time_date':    {'cmd_code': 71, 'decode_fn': self._dec_raw},
            'firmware_release': {'cmd_code': 72, 'decode_fn': self._dec_ascii_and_state},
            'cumulated_energy': {'cmd_code': 78, 'decode_fn': self._dec_int},
            'last_alarms':      {'cmd_code': 86, 'decode_fn': self._dec_alarms}
        }
        # 'Fields' that I can populate. Each entry contains the command and, if
        # applicable, any sub-command code to be sent to the inverter.
        self.field_commands = {
            'state':                      {'cmd': 'state_request'},
            'part_number':                {'cmd': 'part_number'},
            'version':                    {'cmd': 'version'},
            'grid_voltage':               {'cmd': 'measure', 'payload': b'\x01'},
            'grid_current':               {'cmd': 'measure', 'payload': b'\x02'},
            'grid_power':                 {'cmd': 'measure', 'payload': b'\x03'},
            'frequency':                  {'cmd': 'measure', 'payload': b'\x04'},
            'bulk_voltage':               {'cmd': 'measure', 'payload': b'\x05'},
            'leak_dc_current':            {'cmd': 'measure', 'payload': b'\x06'},
            'leak_current':               {'cmd': 'measure', 'payload': b'\x07'},
            'string1_power':              {'cmd': 'measure', 'payload': b'\x08'},
            'string2_power':              {'cmd': 'measure', 'payload': b'\x09'},
            'inverter_temp':              {'cmd': 'measure', 'payload': b'\x15'},
            'booster_temp':               {'cmd': 'measure', 'payload': b'\x16'},
            'string1_voltage':            {'cmd': 'measure', 'payload': b'\x17'},
            'string1_current':            {'cmd': 'measure', 'payload': b'\x19'},
            'string2_voltage':            {'cmd': 'measure', 'payload': b'\x1a'},
            'string2_current':            {'cmd': 'measure', 'payload': b'\x1b'},
            'grid_dc_voltage':            {'cmd': 'measure', 'payload': b'\x1c'},
            'grid_dc_frequency':          {'cmd': 'measure', 'payload': b'\x1d'},
            'isolation_resistance':       {'cmd': 'measure', 'payload': b'\x1e'},
            'bulk_dc_voltage':            {'cmd': 'measure', 'payload': b'\x1f'},
            'grid_average_voltage':       {'cmd': 'measure', 'payload': b'\x20'},
            'bulk_mid_voltage':           {'cmd': 'measure', 'payload': b'\x21'},
            'peak_power':                 {'cmd': 'measure', 'payload': b'\x22'},
            'day_peak_power':             {'cmd': 'measure', 'payload': b'\x23'},
            'grid_voltage_neutral':       {'cmd': 'measure', 'payload': b'\x24'},
            'grid_voltage_neutral_phase': {'cmd': 'measure', 'payload': b'\x26'},
            'serial_number':              {'cmd': 'serial_number'},
            'manufacture_date':           {'cmd': 'manufacture_date'},
            'time_date':                  {'cmd': 'read_time_date'},
            'firmware_release':           {'cmd': 'firmware_release'},
            'day_energy':                 {'cmd': 'cumulated_energy', 'payload': b'\x00'},
            'week_energy':                {'cmd': 'cumulated_energy', 'payload': b'\x01'},
            'month_energy':               {'cmd': 'cumulated_energy', 'payload': b'\x03'},
            'year_energy':                {'cmd': 'cumulated_energy', 'payload': b'\x04'},
            'total_energy':               {'cmd': 'cumulated_energy', 'payload': b'\x05'},
            'partial_energy':             {'cmd': 'cumulated_energy', 'payload': b'\x06'},
            'last_alarms':                {'cmd': 'last_alarms'}
        }
        # initialise transmission state and global state properties
        self.transmission_state = None
        self.global_state = None
        # open the port to the inverter
        self.serial_port = None
        self.open_port()
        # Attempt to obtain the inverter state so that we can update the
        # transmission state and global state properties. If the inverter is
        # asleep (or otherwise cannot be contacted) a WeeWxIOError exception
        # will be raised, meaning the transmission state and global state
        # properties will not be updated. We can just swallow the exception,
        # the driver will continue to poll the inverter or if being run
        # directly or with weectl device, the relevant action will catch an
        # exception later.
        try:
            _ = self.get_state()
        except weewx.WeeWxIOError:
            pass

    @property
    def is_running(self) -> bool:
        """Is the inverter running.

        Updated whenever an inverter command is sent that elicits a response
        that include inverter and global state.
        """

        return self.global_state == 6

    def open_port(self):
        """Open a serial port."""

        try:
            self.serial_port = serial.Serial(port=self.port,
                                             baudrate=self.baudrate,
                                             timeout=self.read_timeout,
                                             write_timeout=self.write_timeout)
        except serial.SerialException as e:
            # we encountered a serial exception, log it and re-raise
            log.error("SerialException on open.")
            log.error("  ***** %s", e)
            # re-raise as a WeeWX IO error
            raise
        else:
            log.debug("Opened serial port '%s' baudrate: %d read_timeout: %.2f write_timeout: %.2f",
                      self.port,
                      self.baudrate,
                      self.read_timeout,
                      self.write_timeout)

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
        except serial.SerialTimeoutException as e:
            # we encountered a write timeout, log it and re-raise as a WeeWX IO
            # error
            log.error("SerialTimeoutException on write.")
            log.error("  ***** %s", e)
            # re-raise as a WeeWX IO error
            raise weewx.WeeWxIOError(e)
        except serial.SerialException as e:
            # we encountered some other serial exception, log it and re-raise
            # as a WeeWX IO error
            log.error("SerialException on write.")
            log.error("  ***** %s", e)
            # re-raise as a WeeWX error I/O error:
            raise weewx.WeeWxIOError(e)
        # Check the serial.Serial.write() return value. write() always returns
        # 'None' for pyserial version 2.5 and earlier, so if we received 'None'
        # it may have been a successful write. We can only infer an error if we
        # received a non-None value and it does not match the number of bytes
        # we intended to send.
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
        except serial.SerialTimeoutException as e:
            # we encountered a read timeout, log it and re-raise as a WeeWX IO
            # error
            log.error("SerialTimeoutException on read.")
            log.error("  ***** %s", e)
            log.error("  ***** Is there a competing process running??")
            # re-raise as a WeeWX IO error
            raise weewx.WeeWxIOError(e)
        except serial.SerialException as e:
            log.error("SerialException on read.")
            log.error("  ***** %s", e)
            log.error("  ***** Is there a competing process running??")
            # re-raise as a WeeWX I/O error:
            raise weewx.WeeWxIOError(e)
        n = len(_buffer)
        if n != bytes_to_read:
            raise weewx.WeeWxIOError("Expected to read %d bytes; got %d instead" % (bytes_to_read,
                                                                                    n))
        return _buffer

    def get_field(self, field_name):
        """Obtain the value of a given field using the API.

        Call execute_cmd_with_crc() to obtain the data required, if valid data
        cannot be obtained a weewx.WeeWxIOError will be raised by
        execute_cmd_with_crc(), our caller needs to be prepared to catch the
        exception.
        """

        response_t = self.execute_cmd_with_crc(command=self.field_commands[field_name]['cmd'],
                                               payload=self.field_commands[field_name].get('payload'))
        return response_t.data

    def execute_cmd_with_crc(self, command, payload=None):
        """Send a command with CRC to the inverter and return the decoded
        response.

        Inputs:
            command: The inverter command being issued, eg 'state_request'.
                     String.
            payload: Data to be sent to the inverter as part of the command.
                     Occupies part or all of bytes 2,3,4,5,6 and 7. Bytestring.

        The transmission_state and/or global_state properties are updated from
        any command response that includes inverter Transmission State and/or
        Global State data.

        Any call to execute_cmd_with_crc() should be prepared to catch a
        weewx.WeeWxIOError should the inverter not respond with a valid
        response.

        Returns:
            The decoded inverter response to the command as a Response Tuple.
        """

        # get the command message to be sent including CRC
        _command_bytes_crc = self.construct_cmd_message(command_code=self.commands[command]['cmd_code'],
                                                        payload=payload)
        # now send the assembled command retrying up to max_tries times
        for count in range(self.max_tries):
            if weewx.debug >= 2:
                log.debug("execute_cmd_with_crc: sent %d",
                          format_byte_to_hex(_command_bytes_crc))
            try:
                self.write(_command_bytes_crc)
                # wait before reading
                time.sleep(self.command_delay)
                # look for the response
                _resp = self.read_with_crc()
            except weewx.CRCError:
                # We seem to get occasional CRC errors, once they start they
                # continue indefinitely. Closing then opening the serial port
                # seems to reset the error and allow proper communication to
                # continue (until the next one). So if we get a CRC error then
                # cycle the port and continue.

                if count < self.max_tries - 1:
                    # log that we are about to cycle the port
                    log.info("CRC error on try #%d. Cycling port.", count + 1)
                    # close the port, wait 0.2 sec then open the port
                    self.close_port()
                    time.sleep(0.2)
                    self.open_port()
                    # log that the port has been cycled
                    log.info("Port cycle complete.")
                else:
                    log.info("CRC error on try #%d.", count + 1)
            except weewx.WeeWxIOError as e:
                # Sometimes we seem to get stuck with continuous IO errors.
                # Cycling the serial port after the second IO error or (one try
                # before the max_tries limit) usually fixes the problem.
                if count < self.max_tries - 1:
                    # this is not our last attempt
                    if count >= 1 or self.max_tries < 3:
                        # it's either our second attempt or our first attempt
                        # if max_tries < 3 so cycle the port
                        if weewx.debug >= 2:
                            log.debug("%s: attempt #%d unsuccessful... cycling port",
                                      "execute_cmd_with_crc",
                                      count + 1)
                        # to cycle the port close the port, wait 0.2 sec then
                        # open the port
                        self.close_port()
                        time.sleep(0.2)
                        self.open_port()
                        # log that the port has been cycled
                        if weewx.debug >= 2:
                            log.debug("execute_cmd_with_crc: port cycle complete.")
                    else:
                        # it must be our first attempt, so log the failure and
                        # have a short sleep until the next attempt
                        if weewx.debug >= 2:
                            log.debug("%s: try #%d unsuccessful... sleeping",
                                      "execute_cmd_with_crc",
                                      count + 1)
                        time.sleep(self.wait_before_retry)
                    # we are going to have another attempt, so log it
                    if weewx.debug >= 2:
                        log.debug("execute_cmd_with_crc: retrying")
                else:
                    # this was our last attempt, so log it as unsuccessful
                    if weewx.debug >= 2:
                        log.debug("execute_cmd_with_crc: try #%d unsuccessful",
                                  count + 1)
            else:
                # We have a response that has passed the CRC check, now decode
                # it. Wrap in a try .. except in case there is a problem
                # decoding the response
                try:
                    _response_t = self.commands[command]['decode_fn'](_resp)
                except (IndexError, TypeError):
                    # for some reason the data could not be decoded, log it but
                    # at a higher debug level
                    if weewx.debug >= 2:
                        log.debug("%s: '%s' could not decode response '%s'",
                                  "execute_cmd_with_crc",
                                  self.commands[command]['decode_fn'].__name__,
                                  format_byte_to_hex(_resp))
                    # return a 'None' ResponseTuple
                    return ResponseTuple(None, None, None)
                else:
                    # we received a valid, decoded response
                    # update the global_state and transmission_state properties
                    # from the response if they are not None
                    if _response_t.transmission_state is not None:
                        self.transmission_state = _response_t.transmission_state
                    if _response_t.global_state is not None:
                        self.global_state = _response_t.global_state
                    # finally return the ResponseTuple
                    return _response_t
        # if we made it here we have exhausted our attempts to obtain data from
        # the inverter, log it and raise a WeeWxIOError
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
            log.debug("read %s", format_byte_to_hex(_response))
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
        """Strip CRC bytes from an inverter response.

        Input:

            buffer:

        Returns:
             a bytearray"""

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
            log.error("  ***** response=%s", format_byte_to_hex(buffer))
            log.error("  *****     data=%s        CRC=%s  expected CRC=%s",
                      format_byte_to_hex(data),
                      format_byte_to_hex(crc_bytes),
                      format_byte_to_hex(crc))
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

    def construct_cmd_message(self, command_code, payload=None):
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

        Bytes 2 to 7 inclusive are used with some command codes as additional
        parameters or a command payload. Unused bytes can be anything, but in
        this implementation they are padded with 0x00.

        Inputs:
            command_code: The inverter command being issued, eg 'getGridV'.
                          Must be a key to the AuroraInverter.commands dict.
                          Mandatory, string.
            payload:      Data to be sent to the inverter as part of the
                          command. Will occupy part or all of bytes 2, 3, 4, 5,
                          6 and 7. Optional, bytestring.

        The command sequence bytestring is constructed by creating a tuple of
        bytes from the command parameters. The tuple is padded with '0's to
        give a length of 10 elements. The tuple is converted to a bytestring,
        its CRC16 calculated and appended to the bytestring to give the final
        command sequence.

        Returns:
            A bytes object (aka bytestring) 10 bytes in length containing the
            command message.
        """

        # First construct a tuple of the bytes we are to send, starting with byte 0,
        # ending with byte 9. Then convert to a bytestring,  and then convert the tup

        # all command sequences start with the inverter address and command
        # code, this is the start of our command sequence tuple
        _command_b_str = struct.pack('2B', self.address, command_code)
        # the rest of the command sequence tuple depends on what we have been
        # asked to send

        # do we have a payload?
        if payload is not None:
            # as the payload is a bytestring we can simply add it to the
            # command sequence bytestring
            _command_b_str += payload
        # now pad out the command sequence with 0s until it's length is 8
        # (10 bytes - 2 bytes for CRC)
        _command_b_str += b'\x00' * (8 - len(_command_b_str))
        # add the CRC and return our byte sequence
        return _command_b_str + self.word2struct(self.crc16(_command_b_str))

    def get_state(self):
        """Get the inverter state.

        Call execute_cmd_with_crc() to obtain the inverter state data, if valid
        data cannot be obtained a weewx.WeeWxIOError will be raised by
        execute_cmd_with_crc(), our caller needs to be prepared to catch the
        exception. If valid data is returned this will also cause the
        global_state and transmission_state properties to be updated.
        """

        return self.execute_cmd_with_crc("state_request").data

    def get_time(self):
        """Get inverter system time.

        Obtain the inverter system time and return as an epoch timestamp. If
        the inverter is asleep the value None will be returned. If valid data
        cannot be obtained a weewx.WeeWxIOError will have been raised, our
        caller needs to be prepared to catch the exception.

        Returns:
            An epoch timestamp or None.
        """

        return self.get_field('time_date')

    def set_time(self, epoch_ts):
        """Set inverter system time.

        Set the inverter system time to the offset timestamp value inverter_ts.
        If the 'set_time_date' command executed successfully the command
        returns a ResponseTuple object where:
        - inverter transmission state == 0
        - inverter global state == 6 (ie self.is_running == True)
        - a valid CRC

        The validity of the CRC is confirmed as part of the command execution,
        the other two conditions we check here and if met we return True. If
        the other two conditions were not met we return False indicating the
        command did not complete successfully.

        The inverter may be asleep so will not respond to any commands. In such
        cases a weewx.WeeWxIOError will have been raised. In such cases the
        error is logged and the exception re-raised to be handled by the
        caller.

        Returns:
            True for successful execution or raises a or False for unsuccessful execution.
        """

        # the inverters epoch is midnight 1 January 2000 so offset our epoch
        # timestamp accordingly
        _inverter_ts = epoch_ts - 946648800
        # pack the value into a Struct object so we can get the offset
        # timestamp as a bytestring, this will be our payload for set_time_date
        _inverter_ts_b_str = struct.pack('>i', _inverter_ts)
        try:
            response_t = self.execute_cmd_with_crc('set_time_date',
                                                   payload=_inverter_ts_b_str)
        except weewx.WeeWxIOError as e:
            # If we have a weewx.WeeWxIOError the inverter could not be
            # contacted or did not return valid data, most likely the inverter
            # is asleep. Assume the inverter is asleep, log it and return
            # False.
            log.error("set_time: Could not contact inverter, it may be asleep")
            log.error("     %s" % e)
            # re-raise the error with a slightly different message for our
            # caller
            raise weewx.WeeWxIOError("set_time: Could not contact inverter, it may be asleep")
        else:
            # update the global state and transmission state properties
            self.global_state = response_t.global_state
            self.transmission_state = response_t.transmission_state
            # return True or False
            return self.transmission_state == 0 and self.is_running

    @property
    def last_alarms(self):
        """Get the last four alarms.

        If valid data cannot be obtained a weewx.WeeWxIOError will have been
        raised, our caller needs to be prepared to catch the exception.
        """

        return self.execute_cmd_with_crc('last_alarms').data

    @property
    def part_number(self):
        """The inverter part number.

        If valid data cannot be obtained a weewx.WeeWxIOError will have been
        raised, our caller needs to be prepared to catch the exception.
        """

        return self.execute_cmd_with_crc('part_number').data

    @property
    def version(self):
        """The inverter hardware version.

        If valid data cannot be obtained a weewx.WeeWxIOError will have been
        raised, our caller needs to be prepared to catch the exception.
        """

        return self.execute_cmd_with_crc('version').data

    @property
    def serial_number(self):
        """The inverter serial number.

        If valid data cannot be obtained a weewx.WeeWxIOError will have been
        raised, our caller needs to be prepared to catch the exception.
        """

        return self.execute_cmd_with_crc('serial_number').data

    @property
    def manufacture_date(self):
        """The inverter manufacture date.

        If valid data cannot be obtained a weewx.WeeWxIOError will have been
        raised, our caller needs to be prepared to catch the exception.
        """

        return self.execute_cmd_with_crc('manufacture_date').data

    @property
    def firmware_release(self):
        """The inverter firmware release.

        The firmware release provided by the inverter is a four character
        string (eg, 'C016'); however, the firmware release is commonly
        displayed as four characters separated by periods (eg, 'C.0.1.6').
        Since the firmware release obtained by the driver is typically for
        display purposes we will return the firmware release as a string with
        each character separated by a period.

        If valid data cannot be obtained a weewx.WeeWxIOError will have been
        raised, our caller needs to be prepared to catch the exception.
        """

        # obtain the firmware release as four character string
        _fw = self.execute_cmd_with_crc('firmware_release').data
        # return the firmware release as a string with each character separated
        # by a period
        return '.'.join([c for c in _fw])

    @staticmethod
    def _dec_state(v):
        """Decode an inverter state request response.

        An inverter state request response is in the following format:

        byte 0: transmission state
        byte 1: global state
        byte 2: inverter state
        byte 3: DC/DC channel 1 state
        byte 4: DC/DC channel 2 state
        byte 5: alarm state

        where each byte represents am integer value.

        Input:
            v: bytearray containing the 6 byte response

        Returns:
            A ResponseTuple where the data attribute is a 4-way tuple of
            integers representing (in order) the inverter state, DC/DC
            channel 1 state, DC/DC channel 2 state and the alarm state.
        """

        try:
            return ResponseTuple(int(v[0]), int(v[1]),
                                 (int(v[2]), int(v[3]), int(v[4]), int(v[5])))
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
            return ResponseTuple(int(v[0]), int(v[1]), str(v[2:6].decode()))
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

        where bytes 2 to 5 inclusive are ASCII character codes of the digit
        concerned, eg if bytes 2 and 3 are hex 34 and 36 respectively
        (ie decimal 52 and 54) bytes 2 and 3 are the ASCII
        characters 4 and 6 respectively meaning the week is decimal 46.

        Input:
            v: bytearray containing the 6 byte response

        Returns:
           A ResponseTuple where the data attribute is a 2 way tuple of (week,
           year).
        """

        try:
            return ResponseTuple(int(v[0]),
                                 int(v[1]),
                                 (int(str(v[2:4].decode())), int(str(v[4:6].decode()))))
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

        return AuroraInverter._dec_ascii_and_state(v)

    @staticmethod
    def _dec_alarms(v):
        """Decode a response containing the last 4 alarms and inverter state.

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
           A ResponseTuple where data attribute is a 4-way tuple of alarm
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

        return f"""{bcolors.BOLD}%prog --help
       %prog --version 
       %prog --gen-packets [FILENAME|--config=FILENAME]
       %prog --live-data [FILENAME|--config=FILENAME]
       %prog --status [FILENAME|--config=FILENAME]
       %prog --info [FILENAME|--config=FILENAME]
       %prog --get-time [FILENAME|--config=FILENAME]
       %prog --set-time [FILENAME|--config=FILENAME]{bcolors.ENDC}"""

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
        parser.add_option('--gen-packets',
                          dest='gen',
                          action='store_true',
                          help='Output LOOP packets indefinitely.')
        parser.add_option('--live-data',
                          dest='live',
                          action='store_true',
                          help='Display current inverter data.')
        parser.add_option('--status',
                          dest='status',
                          action='store_true',
                          help='Display inverter status.')
        parser.add_option('--info',
                          dest='info',
                          action='store_true',
                          help='Display inverter information.')
        parser.add_option('--get-time',
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

        # define custom unit settings
        define_units()

        # get an Aurora driver object
        aurora = DirectAurora(options, parser, **stn_dict)
        aurora.process_arguments()


# ============================================================================
#                           Class AuroraConfEditor
# ============================================================================

class AuroraConfEditor(weewx.drivers.AbstractConfEditor):
    """Config editor for the Aurora driver."""

    # define the default port used during config editing
    DEFAULT_CONFIG_PORT = '/dev/ttyUSB0'

    @property
    def default_stanza(self):
        return f"""
[Aurora]
    # This section is for the Power One Aurora series of inverters.

    # The inverter model, e.g., Aurora PVI-6000, Aurora PVI-5000
    model = INSERT_MODEL_HERE

    # Serial port such as /dev/ttyS0, /dev/ttyUSB0, or /dev/cua0
    port = {AuroraConfEditor.DEFAULT_CONFIG_PORT}

    # inverter address, usually 2
    address = {DEFAULT_ADDRESS}

    # The driver to use:
    driver = user.aurora
"""

    def prompt_for_settings(self):

        print("Specify the inverter model, for example: Aurora PVI-6000 or Aurora PVI-5000")
        model = self._prompt('model', 'Aurora PVI-6000')
        print("Specify the serial port on which the inverter is connected, for")
        print("example: /dev/ttyUSB0 or /dev/ttyS0 or /dev/cua0.")
        port = self._prompt('port', AuroraConfEditor.DEFAULT_CONFIG_PORT)
        print("Specify the inverter address, normally 2")
        address = self._prompt('address', DEFAULT_ADDRESS)
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

    # obtain a bytearray of the byte sequence
    _b_array = bytearray(byte_seq)
    # use a list comprehension to obtain a space delimited string of our byte
    # sequence formatted as hex characters
    return ' '.join(['%02X' % b for b in _b_array])


# ============================================================================
#                            class ResponseTuple
# ============================================================================

class ResponseTuple(tuple):
    """Class to represent a raw inverter command response.

    An inverter response consists of 8 bytes as follows:

        byte 0: transmission state
        byte 1: global state
        byte 2: data
        byte 3: data
        byte 4: data
        byte 5: data
        byte 6: CRC low byte
        byte 7: CRC high byte

    The CRC bytes are stripped away by the Aurora class when validating the
    inverter response. The four data bytes may represent ASCII characters, a
    4 byte float or some other coded value. An inverter response can be
    represented as a 3-way tuple called a response tuple:

        Item  Attribute     Meaning
        0     transmission  The transmission state code (an integer)
        1     global        The global state code (an integer)
        2     data          The four bytes in decoded form (eg 4 character
                            ASCII string, ANSI float)

    Some inverter responses do not include the transmission state and global
    state, in these cases those response tuple attributes are set to None.

    It is also valid to have a data attribute of None. In these cases the data
    could not be decoded and the driver will handle this appropriately.
    """

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
#                             class DirectAurora
# ============================================================================

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

    # inverter observation group dict, this maps all inverter 'fields' to a
    # WeeWX unit group
    inverter_obs_group_dict = {
        'grid_voltage': 'group_volt',
        'grid_current': 'group_amp',
        'grid_power': 'group_power',
        'frequency': 'group_frequency',
        'bulk_voltage': 'group_volt',
        'leak_dc_current': 'group_amp',
        'leak_current': 'group_amp',
        'string1_power': 'group_power',
        'string2_power': 'group_power',
        'inverter_temp': 'group_temperature',
        'booster_temp': 'group_temperature',
        'string1_voltage': 'group_volt',
        'string1_current': 'group_amp',
        'string2_voltage': 'group_volt',
        'string2_current': 'group_amp',
        'grid_dc_voltage': 'group_volt',
        'grid_dc_frequency': 'group_frequency',
        'isolation_resistance': 'group_resistance',
        'bulk_dc_voltage': 'group_volt',
        'grid_average_voltage': 'group_volt',
        'bulk_mid_voltage': 'group_volt',
        'peak_power': 'group_power',
        'day_peak_power': 'group_power',
        'grid_voltage_neutral': 'group_volt',
        'grid_voltage_neutral_phase': 'group_volt',
        'time_date': 'group_time',
        'day_energy': 'group_energy',
        'week_energy': 'group_energy',
        'month_energy': 'group_energy',
        'year_energy': 'group_energy',
        'total_energy': 'group_energy',
        'partial_energy': 'group_energy'
    }

    def __init__(self, namespace, parser, **aurora_dict):
        """Initialise a DirectAurora object."""

        # save the argparse arguments and parser
        self.namespace = namespace
        self.parser = parser
        # save our config dict
        self.aurora_dict = aurora_dict
        # obtain the command line options that override our config dict options
        self.config_from_command_line()

    def config_from_command_line(self):
        """Override the config dict with any command line options.

        Following config options are used/overridden as indicated:
        port:
            - if specified use the port from the command line
            - if a port was not specified on the command line obtain the port
              from the inverter config dict
            - if the inverter config dict does not specify a port use the
              default /dev/ttyUSB0
        poll_interval:
            - if specified use the poll_interval from the command line
            - if poll_interval was not specified on the command line obtain
              poll_interval from the inverter config dict
            - if the inverter config dict does not specify a poll_interval
              the driver will use DEFAULT_POLL_INTERVAL
        """

        if hasattr(self.namespace, 'port') and self.namespace.port:
            self.aurora_dict['port'] = self.namespace.port
        if hasattr(self.namespace, 'poll_interval') and self.namespace.poll_interval:
            self.aurora_dict['poll_interval'] = int(self.namespace.poll_interval)

    def process_arguments(self):
        """Call the appropriate method based on the argparse arguments."""

        # run the driver
        if hasattr(self.namespace, 'gen') and self.namespace.gen:
            self.test_driver()
        # display the inverter status
        elif hasattr(self.namespace, 'status') and self.namespace.status:
            self.status()
        # display inverter info
        elif hasattr(self.namespace, 'info') and self.namespace.info:
            self.info()
        # display current inverter data
        elif hasattr(self.namespace, 'live_data') and self.namespace.live_data:
            self.live_data()
        # display the inverter time
        elif hasattr(self.namespace, 'get_time') and self.namespace.get_time:
            self.get_inverter_time()
        # set the inverter time
        elif hasattr(self.namespace, 'set_time') and self.namespace.set_time:
            self.set_inverter_time()
        # no valid option selected, display the help text
        else:
            print()
            print("No option selected, nothing done")
            print()
            self.parser.print_help()

    def test_driver(self):
        """Exercise the aurora driver.

        Exercises the Aurora driver. Continuously generates, emits and prints
        loop packets (only) a keyboard interrupt occurs.

        The station config dict is used with some config options may be
        overriden by relevant command line options.
        """

        # log that this is a test
        log.info("Testing Aurora driver...")
        # now get an AuroraDriver object, wrap in a try .. except to catch
        # any exceptions, particularly if the inverter is asleep
        try:
            driver = AuroraDriver(**self.aurora_dict)
        except Exception as e:
            # could not load the driver, inform the user and display any error
            # message
            print()
            print("Unable to load driver: %s" % e)
        else:
            print()
            try:
                # identify the device being used
                print(f"Interrogating {driver.model} at {driver.inverter.port}")
                print()
                # loop forever continuously generating loop packets and
                # printing them to console, only stop if we see an exception
                # or a keyboard interrupt
                for pkt in driver.genLoopPackets():
                    print(f"{weeutil.weeutil.timestamp_to_string(pkt['dateTime'])}: "
                          f"{weeutil.weeutil.to_sorted_string(pkt)})")
            except Exception as e:
                # some exception occurred, this will cause us to abort
                print()
                print("Unable to connect to device: %s" % e)
            except KeyboardInterrupt:
                # we have a keyboard interrupt so shut down
                driver.closePort()
        # log completion of the test
        log.info("Aurora driver testing complete")

    def live_data(self):
        """Display the current inverter data.

        Obtain and display the current inverter data. Data is presented is unit
        converted and formatted as necessary. Unit labels are included.
        """

        # get an AuroraDriver object, wrap in a try .. except to catch any
        # exceptions, particularly if the inverter is asleep
        try:
            driver = AuroraDriver(**self.aurora_dict)
        except Exception as e:
            # could not load the driver, inform the user and display any error
            # message
            print()
            print("Unable to load driver: %s" % e)
        else:
            # get a packet containing the current DSP data
            try:
                _current_dsp_data_dict = driver.get_dsp_packet()
            except weewx.WeeWxIOError as e:
                print()
                print(f'Unable to connect to device: {e}')
            except Exception as e:
                print()
                print(f'An unexpected error occurred: {e}')
            else:
                # we have a data dict to work with, but we need to convert and
                # format the packet data for display

                # prepend the inverter obs_group_dict to the WeeWX
                # obs_group_dict to handle the case where there is already be
                # an entry of the same name in weewx.units.obs_group_dict
                weewx.units.obs_group_dict.prepend(DirectAurora.inverter_obs_group_dict)
                # the live data is in Metric units, get a suitable converter
                # based on our output units
                if self.namespace.units.lower() == 'us':
                    _unit_system = weewx.US
                elif self.namespace.units.lower() == 'metricwx':
                    _unit_system = weewx.METRICWX
                else:
                    _unit_system = weewx.METRIC
                c = weewx.units.StdUnitConverters[_unit_system]
                # now get a formatter, the defaults should be fine
                f = weewx.units.Formatter(unit_format_dict=weewx.defaults.defaults['Units']['StringFormats'],
                                          unit_label_dict=weewx.defaults.defaults['Units']['Labels'])
                # build a new data dict with our converted and formatted data
                result = {}
                # iterate over the fields in our original data dict
                for key, value in _current_dsp_data_dict.items():
                    # we don't need usUnits in the result so skip it
                    if key == 'usUnits':
                        continue
                    # get our key as a ValueTuple
                    key_vt = weewx.units.as_value_tuple(_current_dsp_data_dict, key)
                    # now get a ValueHelper which will do the conversion and
                    # formatting
                    key_vh = weewx.units.ValueHelper(key_vt, formatter=f, converter=c)
                    # and add the converted and formatted value to our dict
                    result[key] = key_vh.toString(None_string='None')
                # display the data
                print()
                print(f"{driver.model} Current Data:")
                print(f'  (using WeeWX {weewx.units.unit_nicknames.get(_unit_system)} units)')
                print(f"Inverter time: {result.get('time_date', 'no data')}")
                print("-----------------------------------------------")
                print("Grid:")
                print(f"{'Voltage':>29}: {result.get('grid_voltage', 'no data')}")
                print(f"{'Current':>29}: {result.get('grid_current', 'no data')}")
                print(f"{'Power':>29}: {result.get('grid_power', 'no data')}")
                print(f"{'Frequency':>29}: {result.get('frequency', 'no data')}")
                print(f"{'Average Voltage':>29}: {result.get('grid_average_voltage', 'no data')}")
                print(f"{'Neutral Voltage':>29}: {result.get('grid_voltage_neutral', 'no data')}")
                print(f"{'Neutral Phase Voltage':>29}: {result.get('grid_voltage_neutral_phase', 'no data')}")
                print("-----------------------------------------------")
                print("String 1:")
                print(f"{'Voltage':>29}: {result.get('string1_voltage', 'no data')}")
                print(f"{'Current':>29}: {result.get('string1_current', 'no data')}")
                print(f"{'Power':>29}: {result.get('string1_power', 'no data')}")
                print("-----------------------------------------------")
                print("String 2:")
                print(f"{'Voltage':>29}: {result.get('string2_voltage', 'no data')}")
                print(f"{'Current':>29}: {result.get('string2_current', 'no data')}")
                print(f"{'Power':>29}: {result.get('string2_power', 'no data')}")
                print("-----------------------------------------------")
                print("Inverter:")
                print(f"""{"Voltage (DC/DC Booster)":>29}: {result.get("grid_dc_voltage", "no data")}""")
                print(f"""{"Frequency (DC/DC Booster)":>29}: {result.get("grid_dc_frequency", "no data")}""")
                print(f"""{"Inverter Temp":>29}: {result.get("inverter_temp", "no data")}""")
                print(f"""{"Booster Temp":>29}: {result.get("booster_temp", "no data")}""")
                print(f"""{"Today's Peak Power":>29}: {result.get("day_peak_power", "no data")}""")
                print(f"""{"Lifetime Peak Power":>29}: {result.get("peak_power", "no data")}""")
                print(f"""{"Today's Energy":>29}: {result.get("day_energy", "no data")}""")
                print(f"""{"This Weeks's Energy":>29}: {result.get("week_energy", "no data")}""")
                print(f"""{"This Month's Energy":>29}: {result.get("month_energy", "no data")}""")
                print(f"""{"This Year's Energy":>29}: {result.get("year_energy", "no data")}""")
                print(f"""{"Partial Energy":>29}: {result.get("partial_energy", "no data")}""")
                print(f"""{"Lifetime Energy":>29}: {result.get("total_energy", "no data")}""")
                print()
                print(f"{'Bulk Voltage':>29}: {result.get('bulk_voltage', 'no data')}")
                print(f"{'Bulk DC Voltage':>29}: {result.get('bulk_dc_voltage', 'no data')}")
                print(f"{'Bulk Mid Voltage':>29}: {result.get('bulk_mid_voltage', 'no data')}")
                print()
                print(f"{'Isolation Resistance':>29}: {result.get('isolation_resistance', 'no data')}")
                print()
                print(f"{'Leakage Current(Inverter)':>29}: {result.get('leak_current', 'no data')}")
                print(f"{'Leakage Current(Booster)':>29}: {result.get('leak_dc_current', 'no data')}")

    def status(self):
        """Display the inverter status."""

        # get an AuroraDriver object, wrap in a try .. except to catch any
        # exceptions, particularly if the inverter is asleep
        try:
            driver = AuroraDriver(**self.aurora_dict)
        except Exception as e:
            # could not load the driver, inform the user and display any error
            # message
            print()
            print("Unable to load driver: %s" % e)
        else:
            # obtain the inverter state
            try:
                state_rt = driver.inverter.get_state()
            except weewx.WeeWxIOError as e:
                print()
                print(f'Unable to connect to device: {e}')
            except Exception as e:
                print()
                print(f'An unexpected error occurred: {e}')
            else:
                # now display the inverter status
                print()
                print(f"{driver.model} Status:")
                if driver.inverter.transmission_state is not None:
                    print(f'{"Transmission state":>22}: {driver.inverter.transmission_state} '
                          f'({AuroraInverter.TRANSMISSION[driver.inverter.transmission_state]})')
                else:
                    print(f'{"Transmission state":>22}: None (---)')
                if driver.inverter.global_state is not None:
                    print(f'{"Global state":>22}: {driver.inverter.global_state} '
                          f'({AuroraInverter.GLOBAL[driver.inverter.global_state]})')
                else:
                    print(f'{"Global state":>22}: None (---)')
                if state_rt is not None and state_rt[0] is not None:
                    print(f'{"Inverter state":>22}: {state_rt[0]} '
                          f'({AuroraInverter.INVERTER[state_rt[0]]})')
                else:
                    print(f'{"Inverter state":>22}: None (---)')
                if state_rt is not None and state_rt[1] is not None:
                    print(f'{"DcDc1 state":>22}: {state_rt[1]} '
                          f'({AuroraInverter.DCDC[state_rt[1]]})')
                else:
                    print(f'{"DcDc1 state":>22}: None (---)')
                if state_rt is not None and state_rt[2] is not None:
                    print(f'{"DcDc2 state":>22}: {state_rt[2]} '
                          f'({AuroraInverter.DCDC[state_rt[2]]})')
                else:
                    print(f'{"DcDc2 state":>22}: None (---)')
                if state_rt is not None and state_rt[3] is not None:
                    print(f'{"Alarm state":>22}: {state_rt[3]} '
                          f'({AuroraInverter.ALARM[state_rt[3]]["description"]})'
                          f'[{AuroraInverter.ALARM[state_rt[3]]["code"]}]')
                else:
                    print(f'{"Alarm state":>22}: None (---)')

    def info(self):
        """Display inverter information.

        Obtain an AuroraDriver object then display various fixed inverter
        properties.
        """

        # get an AuroraDriver object, wrap in a try .. except to catch any
        # exceptions, particularly if the inverter is asleep
        try:
            driver = AuroraDriver(**self.aurora_dict)
        except Exception as e:
            # could not load the driver, inform the user and display any error
            # message
            print()
            print("Unable to load driver: %s" % e)
        else:
            # we have an AuroraDriver object now display the inverter info
            print()
            try:
                # display inverter info
                print(f'{driver.model} Information:')
                print(f'{"Part Number":>21}: {driver.inverter.part_number}')
                print(f'{"Version":>21}: {driver.inverter.version}')
                print(f'{"Serial Number":>21}: {driver.inverter.serial_number}')
                _man_date = driver.inverter.manufacture_date
                print(f'{"Manufacture Date":>21}: week {_man_date[0]} year {_man_date[1]}')
                print(f'{"Firmware Release":>21}: {driver.inverter.firmware_release}')
            except weewx.WeeWxIOError as e:
                print()
                print(f'Unable to connect to device: {e}')
            except Exception as e:
                print()
                print(f'An unexpected error occurred: {e}')

    def get_inverter_time(self):
        """Obtain and display the inverter date-time."""

        # get an AuroraDriver object, wrap in a try .. except to catch any
        # exceptions, particularly if the inverter is asleep
        try:
            driver = AuroraDriver(**self.aurora_dict)
        except Exception as e:
            # could not load the driver, inform the user and display any error
            # message
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

    def set_inverter_time(self):
        """Set the inverter date-time."""

        # get an AuroraDriver object, wrap in a try .. except to catch any
        # exceptions, particularly if the inverter is asleep
        try:
            driver = AuroraDriver(**self.aurora_dict)
        except Exception as e:
            # could not load the driver, inform the user and display any error
            # message
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
            # calculate the difference to system time
            _error = inverter_ts - time.time()
            # display the results
            print()
            print(f"Current inverter date-time is {timestamp_to_string(inverter_ts)}")
            print(f"    Clock error is {_error:.3f} seconds (positive is fast)")
            print()
            print("Setting inverter date-time...")
            # set the inverter time to the system time
            driver.setTime()
            print("Successfully set inverter date-time")
            # now obtain and display the inverter time
            inverter_ts = driver.getTime()
            _error = inverter_ts - time.time()
            print()
            print(f"Current inverter date-time is {timestamp_to_string(inverter_ts)}")
            print(f"    Clock error is {_error:.3f} seconds (positive is fast)")


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

    # WeeWX imports
    import weecfg
    import weeutil.logger

    from weeutil.weeutil import bcolors, to_sorted_string

    usage = f"""{bcolors.BOLD}%(prog)s --help
                 --version 
                 --gen-packets
                    [FILENAME|--config=FILENAME]
                    [--port=PORT] [poll_interval=POLL_INTERVAL]
                    [--units=UNIT_SYSTEM]
                 --live-data
                    [FILENAME|--config=FILENAME]
                    [--port=PORT] [--units=UNIT_SYSTEM]
                 --status 
                    [FILENAME|--config=FILENAME]
                 --info
                    [FILENAME|--config=FILENAME]
                 --get-time
                    [FILENAME|--config=FILENAME]
                 --set-time
                    [FILENAME|--config=FILENAME]{bcolors.ENDC}
    """
    description = """Interact with a Power One Aurora inverter."""

    parser = argparse.ArgumentParser(usage=usage,
                                     description=description,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('--config',
                        type=str,
                        metavar="CONFIG_FILE",
                        help="Use configuration file CONFIG_FILE.")
    parser.add_argument('--version',
                        action='store_true',
                        help='Display driver version.')
    parser.add_argument('--gen-packets',
                        dest='gen',
                        action='store_true',
                        help='Output LOOP packets indefinitely.')
    parser.add_argument('--live-data',
                        dest='live_data',
                        action='store_true',
                        help='Display current inverter data.')
    parser.add_argument('--status',
                        dest='status',
                        action='store_true',
                        help='Display inverter status.')
    parser.add_argument('--info',
                        dest='info',
                        action='store_true',
                        help='Display inverter information.')
    parser.add_argument('--get-time',
                        dest='get_time',
                        action='store_true',
                        help='Display current inverter date-time.')
    parser.add_argument('--set-time',
                        dest='set_time',
                        action='store_true',
                        help='Set inverter date-time to the current system date-time.')
    parser.add_argument('--port',
                        type=str,
                        metavar="PORT",
                        help='Use port PORT.')
    parser.add_argument('--poll-interval',
                        type=str,
                        metavar="POLL_INTERVAL",
                        help='Poll the inverter every POLL_INTERVAL seconds.')
    parser.add_argument('--units',
                        dest='units',
                        metavar='UNIT_SYSTEM',
                        default='metric',
                        help='unit system to use when displaying live data')
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

    # define custom unit settings
    define_units()

    # now get a config dict for the inverter
    aurora_dict = config_dict.get('Aurora')

    weeutil.logger.setup('weewx', config_dict)

    # get a DirectAurora object
    direct_aurora = DirectAurora(namespace, parser, **aurora_dict)
    # now let the DirectAurora object process the arguments
    direct_aurora.process_arguments()
    exit(1)


if __name__ == "__main__":
    # start the program
    main()
