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
# Version: 0.1                                      Date: 6 December 2016
#
# Revision History
#   6 December 2016     v0.1
#       - initial implementation
#

from __future__ import with_statement
import datetime
import syslog
import time

from subprocess import Popen, PIPE

# are these needed ?
import math

from datetime import datetime as dt

AURORA_VERSION = '0.1'

DSP_RESP = ['STR1-V', 'STR1-C', 'STR1-P', 'STR2-V', 'STR2-C', 'STR2-P', 
            'Grid-V', 'Grid-C', 'Grid-P', 'Grid-Hz', 'DcAcCvrEff', 'InvTemp', 
            'EnvTemp']
ENERGY_RESP = ['DailyEnery', 'WeeklyEnergy', 'Last7DaysEnergy', 
               'MonthlyEnergy', 'YearlyEnergy', 'TotalEnergy', 
               'PartialEnergy']
DSP_EXT_RESP = ['Bulk-V', 'BilkM-V', 'BulkPlusC-V', 'BulkMinusC-V', 'Bulk-DC',
                'Leak-DC', 'Leak-C', 'IsoRes', 'GridV-DC', 'GridAvg-V', 
                'GridN-V', 'GridDC-Hz', 'PeakP-W', 'PeakTodayP-W', 'TempSupC', 
                'TempAlimC', 'TempHeatSinkC', 'Temp1C', 'Temp2C', 'Temp3C', 
                'FanSpd1C', 'FanSpd2C', 'FanSpd3C', 'FanSpd4C', 'FanSpd5C', 
                'Pin1-W', 'Pin2-W', 'PwrSatC-W', 'BilkRefRingC-V', 'MicroC-V', 
                'WindGen-Hz']
DSP_3PH_RESP = []
ENERGY_CEN_RESP = []
FIELD_MAP = {'STR1-V': 'string1Voltage',
             'STR1-C': 'string1Current',
             'STR1-P': 'string1Power',
             'STR2-V': 'string2Voltage',
             'STR2-C': 'string2Current',
             'STR2-P': 'string2Power',
             'Grid-V': 'gridVoltage',
             'Grid-C': 'gridCurrent',
             'Grid-P': 'gridPower',
             'Grid-Hz': 'gridFrequency',
             'DcAcCvrEff': 'efficiency',
             'InvTemp': 'inverterTemp',
             'EnvTemp': 'boosterTemp',
             'Bulk-V': 'bulkVoltage',
             'IsoRes': 'isoResistance',
             'Pin1-W': 'in1Power',
             'Pin2-W': 'in2Power',
             'BilkM-V': 'bulkmidVoltage',
             'Bulk-DC': 'bulkdcVoltage',
             'Leak-DC': 'leakdcCurrent',
             'Leak-C': 'leakCurrent',
             'GridV-DC': 'griddcVoltage',
             'GridAvg-V': 'gridavgVoltage',
             'GridN-V': 'gridnVoltage',
             'GridDC-Hz': 'griddcFrequency'}
             
def logmsg(level, src, msg):
    syslog.syslog(level, '%s %s' % (src, msg))

def logdbg(src, msg):
    logmsg(syslog.LOG_DEBUG, src, msg)

def logdbg2(src, msg):
    if weewx.debug >= 2:
        logmsg(syslog.LOG_DEBUG, src, msg)

def loginf(src, msg):
    logmsg(syslog.LOG_INFO, src, msg)

def logerr(src, msg):
    logmsg(syslog.LOG_ERR, src, msg)

class Inverter(object):
    """Class to interract with an Aurora inverter using aurora."""
    
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
    
    def __init__(self):
        # weewx.conf paramaters
        PORT = '/dev/ttyUSB0'
        INVERTER_ADDRESS = 2
        # DATA = ['dsp', 'dsp_extended', 'energy']
        DATA = ['dsp', 'dsp_extended']
        # DATA = ['dsp']
        AURORA_CMD = '/usr/local/bin/aurora'
        RETRIES = 100
        LOCK_WAIT = 10
        
        # Initialise our class
        self.port = PORT
        self.aurora_cmd = AURORA_CMD
        self.cmd_preamble = '-Y %d -w %d -a %d' % (RETRIES, 
                                                   LOCK_WAIT, 
                                                   INVERTER_ADDRESS)
        self.data = DATA
        self.address = INVERTER_ADDRESS
        # build list of field names in our data
        # aurora columised data is presented in the following order:
        # 1. date-time
        # 2. dsp
        # 3. energy
        # 4. dsp extended
        # 5. 3 Phase
        # 6. energy central
        # so order matters! Build up our field list depending upon what data 
        # we are requesting.
        _fields = ['dateTime']
        if 'dsp' in self.data:
            _fields += DSP_RESP
        if 'energy' in self.data:
            _fields += ENERGY_RESP
        if 'dsp_extended' in self.data:
            _fields += DSP_EXT_RESP
        if 'dsp_3phase' in self.data:
            _fields += DSP_3PH_RESP
        if 'energy_central' in self.data:
            _fields += ENERGY_CEN_RESP
        self.fields = _fields
        
    # def __enter__(self):
        # pass

    # def __exit__(self):
        # pass

    def _get_aurora_info(self, args=''):
        
        record = dict()
        try:
            t1 = time.time()
            cmd = ' '.join([self.aurora_cmd, self.cmd_preamble,
                            args, self.port])
###            print "cmd=%s" % cmd
            p = Popen(cmd, shell=True, stdout=PIPE)
            o = p.communicate()[0]
        except (ValueError, IOError, KeyError), e:
            logerr('_get_aurora_info failed: %s' % e)
###        print "o=%s" % o
        print "time taken=%s" % (time.time()-t1, )
        return o
        
    def getData(self, col=True):
        """Get readings from inverter."""
        
        _args = '-T ' + ' '.join(self.ARGS[x] for x in self.data)
        _args = '-c ' + _args if col else _args
###        print "_args=%s" % _args
        # get the data
        response = self._get_aurora_info(_args)
        # was the response complete ie does it end with OK?
        if response.strip()[-2:] != 'OK':
            raise IOError('Invalid or incomplete response received from inverter.')
        return response.strip()
        
    @property
    def firmware_version(self):
        """Get inverter firmware version string."""
        
        return self._get_aurora_info(self.ARGS['firmware'])
    
    @property
    def last_alarms(self):
        """Get last fours alarms from inverter."""
        
        return self._get_aurora_info(self.ARGS['alarms'])
    
    @property
    def manufacturing_date(self):
        """Get inverter manufacturing date."""
        
        return self._get_aurora_info(self.ARGS['manufacturing_date'])
    
    @property
    def daily_kwh(self, days=7):
        """Get daily kWh values."""
        
        return self._get_aurora_info(' '.join([self.ARGS['daily_kwh'], days]))
    
    @property
    def system_config(self):
        """Get inverter system configuration."""
        
        return self._get_aurora_info(self.ARGS['system_config'])
    
    @property
    def serial_no(self):
        """Get inverter serial number."""
        
        return self._get_aurora_info(self.ARGS['serial_no'])
    
    @property
    def part_no(self):
        """Get inverter part number."""
        
        return self._get_aurora_info(self.ARGS['part_no'])
    
    @property
    def state(self):
        """Get inverter state."""
        
        return self._get_aurora_info(self.ARGS['state'])
    
    @property
    def date_time(self):
        """Get inverter date-time."""
        
        return self._get_aurora_info(self.ARGS['date_time'])
    
    @property
    def version(self):
        """Get inverter version string."""
        
        return self._get_aurora_info(self.ARGS['version'])
    
    def getAuroraVersion(self):
        """Get aurora software version."""
        
        return self._get_aurora_info('-V')
    
    def parse_data(self, raw_data):
        """Parse raw columnised data from inverter."""
        
        # split our string into individual data fields
        _data = raw_data.split()
        # remove the trailing 'OK'
        _data.pop()
        # get our date-time string, parse it, save it then remove it from our 
        # raw data
        _datetime_str = _data.pop(0)
        _datetime_dt = dt.strptime(_datetime_str, '%Y%m%d-%H:%M:%S', )
        _datetime_ts = time.mktime(_datetime_dt.timetuple())
        # convert our elements to floats
        _data = [float(x) for x in _data]
        # pair up with our field list
        _record = dict(zip(self.fields, _data))
        _record['dateTime'] = int(_datetime_ts)
        return _record

    def map_data(self, data):
        """Map data record from aurora to schema."""
        
        _record = {}
        for data_field, field in FIELD_MAP.iteritems():
            if data_field in data:
                _record[field] = data[data_field]
        return _record

# define a main entry point for basic testing without the weewx engine and 
# service overhead. To invoke this:
#
# python /home/gary/scripts/python/aurora.py

if __name__ == '__main__':
    
    import optparse

    usage = """%prog [options] [--help]"""

    syslog.openlog('aurora', syslog.LOG_PID | syslog.LOG_CONS)
    syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--version', dest='version', action='store_true',
                      help='Display driver version')
    (options, args) = parser.parse_args()

    if options.version:
        print "Aurora driver version %s" % AURORA_VERSION
        exit(0)

    delay = 10
##    with Inverter() as inverter:
    inverter = Inverter()
    while True:
        _raw_data = inverter.getData()
        print "raw data=%s" % _raw_data
        _data = inverter.parse_data(_raw_data)
        print "parsed data=%s" % _data
        record = inverter.map_data(_data)
        print "record=%s" % record
        time.sleep(delay)

