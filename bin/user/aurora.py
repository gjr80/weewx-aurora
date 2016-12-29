# aurora.py
#
# A weewx driver for the Power One Aurora PVI-6000 inverter.
#
# Copyright (C) 2016 Gary Roderick                  gjroderick<at>gmail.com
#
# This program is free software: you can redistribute it and/or modify it under 
# the terms of the GNU General Public License as published by the Free 
# Software Foundation, either version 3 of the License, or (at your option) any 
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT 
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS 
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more 
# details.
#
# You should have received a copy of the GNU General Public License along with 
# this program.  If not, see http://www.gnu.org/licenses/.
#
# Version: 0.1                                      Date: 6 December 2016
#
# Revision History
#  6 December 2016     v0.1    - initial release
#
"""A weewx driver for the Power One Aurora PVI-6000 inverter."""
from __future__ import with_statement
import datetime
import syslog
import time

from subprocess import Popen, PIPE, STDOUT

# weewx imports
import weewx.drivers

from weeutil.weeutil import timestamp_to_string

# our name and version number
DRIVER_NAME = 'Aurora'
DRIVER_VERSION = '0.1'

# command to execute aurora program
AURORA_CMD = '/usr/local/bin/aurora'

# aurora -d (DSP) response field names in order
DSP_RESP = ['STR1-V', 'STR1-C', 'STR1-P', 'STR2-V', 'STR2-C', 'STR2-P', 
            'Grid-V', 'Grid-C', 'Grid-P', 'Grid-Hz', 'DcAcCvrEff', 'InvTemp', 
            'EnvTemp']

# aurora -e (energy) response field names in order
ENERGY_RESP = ['DailyEnergy', 'WeeklyEnergy', 'Last7DaysEnergy', 
               'MonthlyEnergy', 'YearlyEnergy', 'TotalEnergy', 
               'PartialEnergy']

# aurora -D (DSP extended) response field names in order
DSP_EXT_RESP = ['Bulk-V', 'BilkM-V', 'BulkPlusC-V', 'BulkMinusC-V', 'Bulk-DC',
                'Leak-DC', 'Leak-C', 'IsoRes', 'GridV-DC', 'GridAvg-V', 
                'GridN-V', 'GridDC-Hz', 'PeakP-W', 'PeakTodayP-W', 'TempSupC', 
                'TempAlimC', 'TempHeatSinkC', 'Temp1C', 'Temp2C', 'Temp3C', 
                'FanSpd1C', 'FanSpd2C', 'FanSpd3C', 'FanSpd4C', 'FanSpd5C', 
                'Pin1-W', 'Pin2-W', 'PwrSatC-W', 'BilkRefRingC-V', 'MicroC-V', 
                'WindGen-Hz']

# default field map
DEFAULT_MAP = {'string1Voltage':  'STR1-V',
               'string1Current':  'STR1-C',
               'string1Power':    'STR1-P',
               'string2Voltage':  'STR2-V',
               'string2Current':  'STR2-C',
               'string2Power':    'STR2-P',
               'gridVoltage':     'Grid-V',
               'gridCurrent':     'Grid-C',
               'gridPower':       'Grid-P',
               'gridFrequency':   'Grid-Hz',
               'efficiency':      'DcAcCvrEff',
               'inverterTemp':    'InvTemp',
               'boosterTemp':     'EnvTemp',
               'bulkVoltage':     'Bulk-V',
               'isoResistance':   'IsoRes',
               'in1Power':        'Pin1-W',
               'in2Power':        'Pin2-W',
               'bulkmidVoltage':  'BilkM-V',
               'bulkdcVoltage':   'Bulk-DC',
               'leakdcCurrent':   'Leak-DC',
               'leakCurrent':     'Leak-C',
               'griddcVoltage':   'GridV-DC',
               'gridavgVoltage':  'GridAvg-V',
               'gridnVoltage':    'GridN-V',
               'griddcFrequency': 'GridDC-Hz',
               'dayEnergy':       'DailyEnergy'
              }
             
# aurora 1.9.3 argument lookup dict
ARGS = {'firmware': '-f',
        'alarms': '-A',
        'manufacturing_date': '-g',
        'daily_kwh': '-k',
        'system_config': '-m',
        'serial_no': '-n',
        'part_no': '-p',
        'state': '-s',
        'date_time': '-t',
        'version': '-v',
        'aurora_version': '-V',
        'dsp': '-d 0',
        'dsp_extended': '-D',
        'dsp_3phase': '-3',
        'energy': '-e',
        'energy_central': '-E'
       }
           
def logmsg(level, msg):
    syslog.syslog(level, 'aurora: %s' % msg)

def logdbg(msg):
    logmsg(syslog.LOG_DEBUG, msg)

def logdbg2(msg):
    if weewx.debug >= 2:
        logmsg(syslog.LOG_DEBUG, msg)

def loginf(msg):
    logmsg(syslog.LOG_INFO, msg)

def logerr(msg):
    logmsg(syslog.LOG_ERR, msg)

def loader(config_dict, engine):  # @UnusedVariable
    return Aurora(**config_dict[DRIVER_NAME])

class Aurora(weewx.drivers.AbstractDevice):
    """Class to interract with an Aurora inverter using aurora."""
    
    def __init__(self, **stn_dict):
        """Initialise the inverter object."""
        
        self.model = stn_dict.get('model', 'Aurora')
        logdbg('%s driver version is %s' % (self.model, DRIVER_VERSION))
        self.port = stn_dict.get('port', '/dev/ttyUSB0')
        self.max_tries = int(stn_dict.get('max_tries', 3))
        self.polling_interval = int(stn_dict.get('loop_interval', 10))
        logdbg('inverter will be polled on port %s every %d seconds' % (self.port, self.polling_interval))
        
        # contruct the stem of our aurora command
        self.aurora_cmd = AURORA_CMD
        self.address = int(stn_dict.get('address', 2))
        self.aurora_retries = int(stn_dict.get('aurora_retries', 10))
        # Time to wait to lock serial port in ms. Valid values are 10 to 30000. 
        # Value of 0 will cause there to be one try to lock the serial port.
        self.lock_wait = int(stn_dict.get('lock_wait', 10))
        if self.lock_wait < 10 and self.lock_wait != 0.0:
            self.lock_wait = 10
            logdbg('wait time for serial port lock out of range (10-30000ms), using 10ms')
        elif self.lock_wait > 30000:
            self.lock_wait = 30000
            logdbg('wait time for serial port lock out of range (10-30000ms), using 30000ms')
        elif self.lock_wait == 0.0:
            logdbg('aurora will try once to lock the serial port')
        else:
            logdbg('aurora will wait %dms to lock the serial port' % self.lock_wait)
        self.cmd_preamble = '-Y %d -w %d -a %d' % (self.aurora_retries, 
                                                   self.lock_wait, 
                                                   self.address)
        logdbg('aurora command preamble is %s' % self.cmd_preamble)

        # Build a list of field names (excluding date time) being returned by 
        # aurora based upon the data sets being sought. aurora presents 
        # columised data in the following data set order:
        # 1. dsp
        # 2. energy
        # 3. dsp extended
        # 4. 3 Phase
        # 5. energy central
        # so order matters! Build up our field list depending upon what data
        # sets we are requesting.
        self.data_sets = stn_dict.get('data_sets', ['dsp', 'energy'])
        _fields = []
        if 'dsp' in self.data_sets:
            _fields += DSP_RESP
        if 'energy' in self.data_sets:
            _fields += ENERGY_RESP
        if 'dsp_extended' in self.data_sets:
            _fields += DSP_EXT_RESP
        if 'dsp_3phase' in self.data_sets:
            _fields += []
        if 'energy_central' in self.data_sets:
            _fields += []
        self.fields = _fields
        logdbg('aurora field list is %s' % self.fields)
        
        # get the field map
        self.field_map = stn_dict.get('FieldMap', DEFAULT_MAP)
        logdbg('field map is %s' % self.field_map)

        # initialise last energy value
        self.last_energy = None
        
    def genLoopPackets(self):
        """Generator function that returns 'loop' packets."""
        
        for count in range(self.max_tries):
            while True:
                try:
                    # get the current time as timestamp
                    _ts = int(time.time())
                    # poll the inverter and obtain raw data
                    raw_data = self.get_data()
                    # process raw data and return a dict that can be used as a 
                    # LOOP packet
                    packet = self.data_to_packet(raw_data, 
                                                 last_energy=self.last_energy,
                                                 ts=_ts,
                                                 field_map=self.field_map)
                    self.last_energy = packet['dayEnergy'] if 'dayEnergy' in packet else None
                    yield packet
                    # wait until its time to poll again
                    while int(time.time()) % self.polling_interval != 0:
                        time.sleep(0.2)
                except IOError, e:
                    logerr("aurora: LOOP try #%d; error: %s" % (count + 1, e))
                    break
                    
        logerr("aurora: LOOP max tries (%d) exceeded." % self.max_tries)
        raise weewx.RetriesExceeded("Max tries exceeded while getting LOOP data.")

    def send_command(self, args=''):
        """Send a command using aurora and return any response.
        
        Uses aurora program to send commands to the Aurora inverter. The raw 
        inverter response is returned.
        """
        
        try:
            # construct the command string to use
            cmd = ' '.join([self.aurora_cmd, self.cmd_preamble,
                            args, self.port])
            p = Popen(cmd, shell=True, stdout=PIPE, stderr=STDOUT)
            o = p.communicate()[0]
        except (ValueError, IOError, KeyError), e:
            logerr('send_command failed: %s' % e)
        return o
        
    def get_data(self, col=True):
        """Obtain data from inverter.
        
        Uses send_command to send a command to the inverter and checks the 
        returned data is complete. Raw data is returned stripped of any 
        leading or training whitespace.
        """
        
        # Construct our aurora argument list based on the data sets requested. 
        # Include inverter time.
        _args = '-T ' + ' '.join(ARGS[x] for x in self.data_sets)
        # add the argument to make sure we get columised data
        _args = '-c ' + _args if col else _args
        # get the data
        response = self.send_command(_args)
        # was the response complete ie does it end with OK?
        if response.strip()[-2:] != 'OK':
            # it could be because the inverter is asleep
            if response.upper().find("ERROR: RECEIVED BAD RETURN CODE") > 0:
                # looks like the inverter is asleep, either way we can't get 
                # any response so return None
                return None
            else:
                # could be an incomplete response, so eaise an error
                raise IOError('Invalid or incomplete response received from inverter.')
        return response.strip()
        
    def data_to_packet(self, data, ts, last_energy=None, 
                       field_map=DEFAULT_MAP):
        """Parse raw data string from inverter and create a weewx loop packet.
        
        Parses raw data string from inverters and produces a dict of field 
        names and values. Then maps aurora fields to weewx fields.
        """
        
        # initialise a packet
        _packet = {}
        # add in dateTime
        _packet['dateTime'] = ts
        # and usUnits
        _packet['usUnits'] = weewx.METRIC

        # Do we have any data? If the inverter is asleep or otherwise 
        # uncontactable data will be None
        if data is not None:
            # Process our raw data string and convert to a dict of aurora field 
            # names and values.
            
            # split our raw data string into individual data fields
            _data = raw_data.split()
            # pop off the trailing 'OK'
            _data.pop()
            # pop off our date-time string
            _data.pop(0)
            # convert our elements to floats
            _data = [float(x) for x in _data]
            # pair up with our field list
            data = dict(zip(self.fields, _data))
            
            # Take the aurora data dict and map to a weewx packet dict
            for weewx_field, data_field in DEFAULT_MAP.iteritems():
                if data_field in data:
                    _packet[weewx_field] = data[data_field]
            # A few fields require some special attention.
            # dayEnergy is cumulative by day but we need incremental values so we 
            # need to calculate it based on the last cumulative value
            _packet['energy'] = self.calculate_energy(_packet['dayEnergy'], 
                                                      last_energy)
            # scale our resistance, its in Mohms but we need ohms
            try:
                _packet['isoResistance'] *= 1000000.0
            except KeyError:
                # there is no isoResistance field so leave it
                pass
            except TypeError:
                # isoResitance exists but is not numeric
                _packet['isoResistance'] = None
        # whether data was None or contained data _packet has our result, so 
        # return it
        return _packet

    @property
    def hardware_name(self):
        return self.model
    
    @property
    def firmware_version(self):
        """Get inverter firmware version string."""
        
        return self.send_command(ARGS['firmware'])
    
    @property
    def last_alarms(self):
        """Get last fours alarms from inverter."""
        
        return self.send_command(ARGS['alarms'])
    
    @property
    def manufacturing_date(self):
        """Get inverter manufacturing date."""
        
        return self.send_command(ARGS['manufacturing_date'])
    
    @property
    def daily_kwh(self, days=7):
        """Get daily kWh values."""
        
        return self.send_command(' '.join([ARGS['daily_kwh'], days]))
    
    @property
    def system_config(self):
        """Get inverter system configuration."""
        
        return self.send_command(ARGS['system_config'])
    
    @property
    def serial_no(self):
        """Get inverter serial number."""
        
        return self.send_command(ARGS['serial_no'])
    
    @property
    def part_no(self):
        """Get inverter part number."""
        
        return self.send_command(ARGS['part_no'])
    
    @property
    def state(self):
        """Get inverter state."""
        
        return self.send_command(ARGS['state'])
    
    @property
    def date_time(self):
        """Get inverter date-time."""
        
        return self.send_command(ARGS['date_time'])
    
    @property
    def version(self):
        """Get inverter version string."""
        
        return self.send_command(ARGS['version'])
    
    def getAuroraVersion(self):
        """Get aurora software version."""
        
        return self.send_command('-V')
    
    @staticmethod
    def calculate_energy(newtotal, oldtotal):
        """Calculate the energy differential given two cumulative measurements."""
        
        if newtotal is not None and oldtotal is not None:
            if newtotal >= oldtotal:
                delta = newtotal - oldtotal
            else:
                delta = None
        else:
            delta = None
        return delta
        
# define a main entry point for basic testing without the weewx engine and 
# service overhead. To invoke this:
#
# PYTHONPATH=/home/weewx/bin python /home/weewx/bin/user/aurora.py

if __name__ == '__main__':
    
    import optparse

    def sort(rec):
        return ", ".join(["%s: %s" % (k, rec.get(k)) for k in sorted(rec, 
                                                                     key=str.lower)])

    usage = """%prog [options] [--help]"""

    syslog.openlog('aurora', syslog.LOG_PID | syslog.LOG_CONS)
    syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--version', dest='version', action='store_true',
                      help='Display driver version')
    (options, args) = parser.parse_args()

    if options.version:
        print "Aurora driver version %s" % DRIVER_VERSION
        exit(0)

    inverter = Aurora()
    last_energy = None
    while True:
        _ts = int(time.time())
        raw_data = inverter.get_data()
        packet = inverter.data_to_packet(raw_data, 
                                         last_energy=last_energy,
                                         ts=_ts,
                                         field_map=inverter.field_map)
        last_energy = packet['dayEnergy']
        print "LOOP:  ", timestamp_to_string(packet['dateTime']), sort(packet)
        while int(time.time()) % inverter.polling_interval != 0:
            time.sleep(0.2)

