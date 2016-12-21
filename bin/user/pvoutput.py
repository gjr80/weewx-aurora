# pvoutput.py
#
# A weewx schema for use with aurora-1.9.3 and an Aurora inverter.
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
# Version: 0.1                                      Date: 17 December 2016
#
# Revision History
#  17 December 2016     v0.1    - initial release
#
"""A class to interract with the PVOutput API."""
import datetime
import syslog
import time
import urllib
import urllib2

def read_api_key():
    """Read api_key from a file.

    Temporary convenience function used during development to read an api_key
    from a local file so that I don't have to put it in weewx.conf (that I am
    saving to github) or type it on the command line.

    Delete this from the production version.
    """
    with open('/home/gary/api_key.txt', 'r') as f:
        api_key = f.read()
    return api_key

def read_sid():
    """Read system ID from a file.

    Temporary convenience function used during development to read a system ID
    from a local file so that I don't have to put it in weewx.conf (that I am
    saving to github) or type it on the command line.

    Delete this from the production version.
    """
    with open('/home/gary/sid.txt', 'r') as f:
        sid = f.read()
    return sid

class HTTPResponseError(StandardError):
    """Raised when HTTP request returns an error."""

# ============================================================================
#                            class PVOutputAPI
# ============================================================================


class PVOutputAPI(object):
    """Class to interact with PVOutput API."""

    SERVICE_SCRIPT = {'addstatus': '/service/r2/addstatus.jsp',
                      'getstatus': '/service/r2/getstatus.jsp',
                      'deletestatus': '/service/r2/deletestatus.jsp',
                      'getoutput': '/service/r2/getoutput.jsp',
                      'getsystem': '/service/r2/getsystem.jsp'
                     }

    def __init__(self, **kwargs):
        """"Initialiase the PVOutputAPI object."""

        self.sid = kwargs.get('sid', read_sid())
        self.api_key = kwargs.get('api_key', read_api_key())
        self.base_url = kwargs.get('base_url', 'http://pvoutput.org')
        self.max_tries = kwargs.get('max_tries', 3)
        self.retry_wait = kwargs.get('retry_wait', 2)
        self.timeout = kwargs.get('timeout', 5)
        # do we have/use tariff information
        self.tariffs = False

    def request_with_retries(self, service_script, data=None):
        """Send a request to the PVOutput API retrying if required."""

        # get the url to be used
        url = self.base_url + service_script
        # create a Request object
        request = urllib2.Request(url=url, data=urllib.urlencode(data))
        # add our headers, in this case sid and api_key
        request.add_header('X-Pvoutput-Apikey', self.api_key)
        request.add_header('X-Pvoutput-SystemId', self.sid)
        # try to post the request up to max_tries times
        for _count in range(self.max_tries):
            # use a try..except to catch any errors
            try:
                # do the post and get the response
                _response = self._post_request(request)
                # check the response status code, PVOutput will return 200 if
                # all was OK
                _status_code = _response.getcode()
                if _status_code == 200:
                    # we have a good status so we are done
                    break
                else:
                    # somethign went wrong, so raise it
                    raise HTTPResponseError("%s returned a bad HTTP response code: %s" % (url,
                                                                                          _status_code))
            except urllib2.URLError as e:
                # If we have a reason for the error then we likely didn't get
                # to the server. Log the error and continue.
                if hasattr(e, 'reason'):
                    print "Failed to reach a server. Reason: %s" % e.reason
                # If we have a code we did get to the server but it returned an
                # error. Log the error and continue.
                if hasattr(e, 'code'):
                    print "The server returned an error. Error code: %s" % e.code
            time.sleep(self.retry_wait)
        return _response.read()

    def _post_request(self, request):
        """Post a request object."""

        try:
            # Python 2.5 and earlier does not have a 'timeout' parameter so be
            # prepared to catch the exception and try a Pythoin 2.5 compatible
            # call.
            _response = urllib2.urlopen(request, timeout=self.timeout)
        except TypeError:
            # Python 2.5 compatible call
            _response = urllib2.urlopen(request)
        return _response

    def getstatus(self, history=0, ascending=1, limit=288, extended=0, 
                  **kwargs):
        """Retieve system status information and live output data."""

        # map our kwargs input prarameters to the fields required by the API
        GETSTATUS_PARAMS = {'date': 'd',
                            'time': 't',
                            'from': 'from',
                            'to': 'to',
                            'sid1': 'sid1'}
        # define the fields returned by the API, there are 2 cases (1) for a 
        # single (ie non-history) request and (2) for a history request
        GETSTATUS_FIELDS = [['date', 'time', 'energy_generation',
                             'power_generation', 'energy_consumption',
                             'power_consumption', 'efficiency', 'temperature',
                             'voltage', 'ext1', 'ext2', 'ext3', 'ext4', 'ext5',
                             'ext6', ]]
        GETSTATUS_HISTORY_FIELDS = [['date', 'time', 'energy_generation',
                                     'energy_efficiency', 'inst_power', 
                                     'avg_power', 'normalised_output', 
                                     'energy_consumption', 'power_consumption', 
                                     'temperature', 'voltage', 'ext1', 'ext2', 
                                     'ext3', 'ext4', 'ext5', 'ext6']]

        # construct the parameter dict to be sent as part of our API request
        # first set those parameters that have a default value
        params = {}
        params['h'] = history
        params['asc'] = ascending
        params['limit'] = limit
        params['ext'] = extended

        # now trawl our kwargs and add
        for var, data in kwargs.iteritems():
            if var in GETSTATUS_PARAMS and data is not None:
                params[GETSTATUS_PARAMS[var]] = data
        
        # submit the request to the API
        _response = self.request_with_retries(self.SERVICE_SCRIPT['getstatus'], 
                                              params)
        # return our result as a list of dicts
        if params['h'] == 1:
            return self._to_dict(_response, GETSTATUS_HISTORY_FIELDS)
        else:
            return self._to_dict(_response, GETSTATUS_FIELDS, single_dict=True)

    def addstatus(self, **kwargs):
        """Add a status to the system."""

        # map our input prarameters to the fields required by the API
        ADDSTATUS_PARAMS = {'date': 'd',
                            'time': 't',
                            'energy': 'v1',
                            'powergen': 'v2',
                            'energycons': 'v3',
                            'powercons': 'v4',
                            'temperature': 'v5',
                            'voltage': 'v6',
                            'cumulative': 'c1',
                            'net': 'n',
                            'delay': 'delay',
                            'extended1': 'v7',
                            'extended2': 'v8',
                            'extended3': 'v9',
                            'extended4': 'v10',
                            'extended5': 'v11',
                            'extended6': 'v12'}

        # construct the parameter dict to be sent as part of our API request
        params = {}
        for var, data in kwargs.iteritems():
            if var in ADDSTATUS_PARAMS and data is not None:
                params[ADDSTATUS_PARAMS[var]] = data
        
        # submit the request to the API
        response = self.request_with_retries(self.SERVICE_SCRIPT['addstatus'], 
                                             params)
        
        # return the response
        return response

    def deletestatus(self, **kwargs):
        """Remove an existing status from the system."""

        DELETESTATUS_PARAMS = {'date': 'd',
                               'time': 't'}

        params = {}
        for var, data in kwargs.iteritems():
            if var in DELETESTATUS_PARAMS and data is not None:
                params[DELETESTATUS_PARAMS[var]] = data
        response = self.request_with_retries(self.SERVICE_SCRIPT['deletestatus'], 
                                             params)

    def getsystem(self, secondary_array=0, tariffs=0, teams=0, 
                  month_estimates=0, donations=1, sid1=0, extended=0):
        """Retrieve system information."""

        # define the fields returned by the API
        BASE = ['name', 'size', 'postcode', 'num_panels', 'panel_power', 
                'panel_brand', 'num_inverters', 'inverter_power', 
                'inverter_brand', 'orientation', 'tilt', 'shade', 
                'install_date', 'latitude', 'longitude', 'interval']
        SECONDARY = ['sec_num_panels', 'sec_panel_power', 'sec_panel_brand', 
                     'sec_num_inverters']
        TARIFF = ['export', 'import_peak', 'import_off_peak', 
                  'import_shoulder', 'import_high_shoulder', 
                  'import_daily_charge']
        TEAMS = ['teams']
        DONATIONS = ['donations']
        EXTENDED = ['extended']
        
        # construct the parameter dict to be sent as part of our API request
        params = {}
        params['array2'] = secondary_array
        params['tariffs'] = tariffs
        params['teams'] = teams
        params['est'] = month_estimates
        params['donations'] = donations
        params['sid1'] = sid1
        params['ext'] = extended
        
        # assemble a list of lists of the fields we expect to be returned
        GETSYSTEM_FIELDS = [BASE]
        if params['array2'] == 1:
            GETSYSTEM_FIELDS.append(SECONDARY)
        if self.tariffs:
            GETSYSTEM_FIELDS.append(TARIFF)
        if params['teams'] == 1:
            GETSYSTEM_FIELDS.append(TEAMS)
        GETSYSTEM_FIELDS.append(DONATIONS)
        if params['ext'] == 1:
            GETSYSTEM_FIELDS.append(EXTENDED)

        # submit the request to the API
        _response = self.request_with_retries(self.SERVICE_SCRIPT['getsystem'], 
                                              params)
        # return a list of dicts
        return self._to_dict(_response, GETSYSTEM_FIELDS, single_dict=True)

    def getoutput(self, **kwargs):
        """Retrieve system or team daily output information."""

        GETOUTPUT_PARAMS = {'from': 'df',
                            'to': 'dt',
                            'aggregate': 'a',
                            'limit': 'limit',
                            'team_id': 'tid',
                            'sid1': 'sid1'}

        params = {}
        for var, data in kwargs.iteritems():
            if var in GETOUTPUT_PARAMS and data is not None:
                params[GETOUTPUT_PARAMS[var]] = data
        return self.request_with_retries(self.SERVICE_SCRIPT['getoutput'], params)

    @staticmethod
    def _to_dict(data, fields, single_dict=False):
        """Parse PVOutput API csv output."""

        _csv = data.split(';')
        _result = []
        _multi_field_lists = len(fields) > 1
        for _row in _csv:
            _temp = _row.split(',')
            _row_list = [x if x != 'NaN' else None for x in _temp]
            for _field in fields:
                _row_tuple_list = zip(_field, _row_list)
                _result.append(dict(_row_tuple_list))
        if single_dict:
            result = {}
            for dictionary in _result:
                result.update(dictionary)
            return [result]
        else:
            return _result