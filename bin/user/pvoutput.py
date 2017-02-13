# pvoutput.py
#
# Classes for interracting the PVOutput API.
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
# Version: 0.2.1                                    Date: 13 February 2017
#
# Revision History
#  13 February 2017     v0.2.1  - fixed issue where an uncaught socket.timeout
#                                 exception would crash PVOutputThread
#   7 February 2017     v0.2    - check to ensure that PVOutputThread has the
#                                 minimum required fields to post a status to
#                                 PVOutput
#   17 December 2016    v0.1    - initial release
#
"""Classes to interract with the PVOutput API.

Classes StdPVOutput and PVOutputThread are used as a weeWX RESTful service to
post data to PVOutput.org.

Class PVOuputAPI provides the ability to add, update, read and delete system
data on PVOutput.org via the PVOutput API.
"""

import datetime
import httplib
import Queue
import sys
import syslog
import time
import urllib
import urllib2

# weewx imports
import weewx.restx
import weewx.units
from weeutil.weeutil import timestamp_to_string, startOfDay


# ============================================================================
#                            class StdPVOutput
# ============================================================================


class StdPVOutput(weewx.restx.StdRESTful):
    """Specialised RESTful class for PVOutput."""

    # base url for PVOutput API
    api_url = 'http://pvoutput.org'
    # give our protocol a name
    protocol_name = 'PVOutput-API'

    def __init__(self, engine, config_dict):
        # initialize my superclass
        super(StdPVOutput, self).__init__(engine, config_dict)

        # get the PVOutput settings from [StdRESTful] in our config dict
        _pvoutput_dict = weewx.restx.get_site_dict(config_dict, 'PVOutput',
                                                   'system_id', 'api_key')
        if _pvoutput_dict is None:
            return
        _pvoutput_dict.setdefault('server_url', StdPVOutput.api_url)

        # Get the manager dictionary:
        _manager_dict = weewx.manager.get_manager_dict_from_config(config_dict,
                                                                   'aurora_binding')

        # create a Queue object to pass records to the thread
        self.archive_queue = Queue.Queue()
        # create our thread
        self.archive_thread = PVOutputThread(self.archive_queue,
                                             _manager_dict,
                                             protocol_name=StdPVOutput.protocol_name,
                                             **_pvoutput_dict)
        # start the thread
        self.archive_thread.start()
        # bind to NEW_ARCHIVE _RECORD event
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        syslog.syslog(syslog.LOG_INFO, "pvoutput: %s: "
                      "Data for system ID %s will be posted" %
                      (StdPVOutput.protocol_name, _pvoutput_dict['system_id']))

    def new_archive_record(self, event):
        """Put new archive records in the archive queue.

        Each archive record placed in the queue will be posted as a status to
        PVOutput.org.
        """

        self.archive_queue.put(event.record)


# ============================================================================
#                           class PVOutputThread
# ============================================================================


class PVOutputThread(weewx.restx.RESTThread):
    """Class for threads posting to PVOutput using the PVIOutput API."""

    # PVOutput API scripts that we know about
    SERVICE_SCRIPT = {'addstatus': '/service/r2/addstatus.jsp',
                      'getsystem': '/service/r2/getsystem.jsp'
                     }

    def __init__(self, queue, manager_dict, system_id, api_key, server_url,
                 protocol_name="Unknown-RESTful", post_interval=None,
                 max_backlog=sys.maxint, stale=None, log_success=True,
                 log_failure=True, timeout=5, max_tries=3, retry_wait=2,
                 skip_upload=False, cumulative_energy=False, net=False,
                 net_delay=0, tariffs=False):

        """Initializer for the PVOutputThread class.

        Parameters specific to this class:

            system_id:  The PVOutput allocated ID for the system, eg '1234'

            api_key:    The PVOutput allocated key used to update a given
                        system's data on PVOutput.

            server_url: The base URL for the PVOuputr API server.
        """

        # Initialize my superclass:
        super(PVOutputThread, self).__init__(queue,
                                             protocol_name=protocol_name,
                                             manager_dict=manager_dict,
                                             post_interval=post_interval,
                                             max_backlog=max_backlog,
                                             stale=stale,
                                             log_success=log_success,
                                             log_failure=log_failure,
                                             timeout=timeout,
                                             max_tries=max_tries,
                                             retry_wait=retry_wait,
                                             skip_upload=skip_upload)

        self.sid = system_id
        self.api_key = api_key
        self.server_url = server_url
        self.cumulative = cumulative_energy
        self.net = net
        self.net_delay = net_delay
        self.tariffs = tariffs
        # Donors to PVOutput receive benefits such as the ability to upload
        # larger batches of status data and being able to add older historical
        # status data. Check to see if this system ID is a donor or not and set
        # the appropriate limits.
        system = self.getsystem(donations=1)
        if system[0]['donations'] == '1':
            self.max_batch_size = 100
            self.update_period = 90
        else:
            self.max_batch_size = 30
            self.update_period = 14
        # Now summarize what we are doing in a few syslog DEBUG lines
        syslog.syslog(syslog.LOG_DEBUG, "pvoutput: server url=%s" % self.server_url)
        syslog.syslog(syslog.LOG_DEBUG,
                      "pvoutput: cumulative_energy=%s net=%s net_delay=%d tariffs=%s" %
                      (self.cumulative, self.net, self.net_delay, self.tariffs))
        syslog.syslog(syslog.LOG_DEBUG,
                      "pvoutput: max batch size=%d max update period=%d days" %
                      (self.max_batch_size, self.update_period))

    def process_record(self, record, dbmanager):
        """Add a status to the system.

        Input:
            record:     A weewx archive record containing the data to be added.
                        Dictionary.
            cumulative: Set if energy field passed is lifetime cumulative
                        rather than a daytime cumulative. Boolean, default
                        False.
            net:        Set if the power values passed are net export/import
                        rather than gross generation/consumption. Boolean,
                        default False.
            net_delay:  Delay processing of the data by specified number of
                        minutes. Numeric, default 0.
        Returns:
            PVOutput API response code for addstatus request
            eg 'OK 200: Added Status' if successful. returns None if addstatus
            unsuccessful.
        """

        # map our record fields to the optional addstatus fields accepted by
        # the API
        ADDSTATUS_PARAMS = {'dayEnergy': 'v1',
                            'gridPower': 'v2',
                            'energyCons': 'v3',
                            'powerCons': 'v4',
                            'inverterTemp': 'v5',
                            'gridVoltage': 'v6',
                            'extended1': 'v7',
                            'extended2': 'v8',
                            'extended3': 'v9',
                            'extended4': 'v10',
                            'extended5': 'v11',
                            'extended6': 'v12'}
        # addstatus service requires data in at least one of the following
        # fields
        REQUIRED_PARAMS = ['v1', 'v2', 'v3', 'v4']

        # Get any extra data (that is not in record) required to post a status
        # to PVOutput. In this case we need today's cumulative energy.
        _full_record = self.get_record(record, dbmanager)

        # Do we have the minimum required fields to post a status ? Probably
        # should do this in skip_record() but to do so would require knowledge
        # of the record being posted and that would mean overriding run_loop()
        # just to change 1 line of code.
        for rec_field, api_field in ADDSTATUS_PARAMS.iteritems():
            if api_field in REQUIRED_PARAMS:
                if rec_field in record and record[rec_field] is not None:
                    # we have one, break so we can process the record
                    break
        else:
            # if we got here it is becase we have none of the required fields,
            # raise and AbortedPost exception and restx will skip posting
            raise weewx.restx.AbortedPost()

        # convert to metric if necessary
        _metric_record = weewx.units.to_METRIC(_full_record)

        # initialise our parameter dictionary
        params = {}
        # add date and time for this record
        time_tt = time.localtime(_metric_record['dateTime'])
        params['d'] = time.strftime("%Y%m%d", time_tt)
        params['t'] = time.strftime("%H:%M", time_tt)
        # add c1 parameter if cumulative is set
        if self.cumulative:
            params['c1'] = 1
        # add n parameter if net is set
        if self.net:
            params['n'] = 1
        # add delay parameter if we have a value
        if self.net_delay > 0:
            params['delay'] = self.net_delay

        # add any optional parameters from our data
        for rec_field, api_field in ADDSTATUS_PARAMS.iteritems():
            if rec_field in _metric_record and _metric_record[rec_field] is not None:
                params[api_field] = _metric_record[rec_field]

        # get the url to be used
        url = self.server_url + self.SERVICE_SCRIPT['addstatus']
        # create a Request object
        _request = urllib2.Request(url=url)
        # if debug >= 2 then log some details of our request
        if weewx.debug >= 2:
            syslog.syslog(syslog.LOG_DEBUG, "pvoutput: %s: url: %s payload: %s" %
                              (self.protocol_name, url, urllib.urlencode(params)))
        # add our headers, in this case sid and api_key
        _request.add_header('X-Pvoutput-Apikey', self.api_key)
        _request.add_header('X-Pvoutput-SystemId', self.sid)
        response = self.post_with_retries(_request, urllib.urlencode(params))
        # if debug >= 2 then log some details of the response
        if weewx.debug >= 2:
            syslog.syslog(syslog.LOG_DEBUG,
                          "pvoutput: %s: response: %s" % (self.protocol_name,
                                                          response.read()))

    def get_record(self, record, dbmanager):
        """Augment record data with additional data derived from the archive.

        PVOutput requires 'energy' in each status record to be a cumulative
        value (either day or lifetime). Cumulative values are not normally
        included in a weewx record/packet so we need to calculate the data
        from the archive. In this case we will use the day cumualtive total.
        Returns results in the same units as the record.

        Input:
            record:    A weewx archive record containing the data to be added.
                       Dictionary.
            dbmanager: Manager object for the database being used.
        Returns:
            A dictionary of values
        """

        _time_ts = record['dateTime']
        _sod_ts = startOfDay(_time_ts)

        # Make a copy of the record, then start adding to it:
        _datadict = dict(record)

        # If the type 'energy' does not appear in the archive schema, or the
        # database is locked, an exception will be raised. Be prepared to catch
        # it.
        try:
            if 'dayEnergy' not in _datadict:
                _result = dbmanager.getSql(
                    "SELECT SUM(energy), MIN(usUnits), MAX(usUnits) FROM %s "
                    "WHERE dateTime>? AND dateTime<=?" %
                    dbmanager.table_name, (_sod_ts, _time_ts))
                if _result is not None and _result[0] is not None:
                    if not _result[1] == _result[2] == record['usUnits']:
                        raise ValueError("Inconsistent units (%s vs %s vs %s) when querying for dayEnergy" %
                                             (_result[1],
                                              _result[2],
                                              record['usUnits']))
                    _datadict['dayEnergy'] = _result[0]
                else:
                    _datadict['dayEnergy'] = None

        except weedb.OperationalError, e:
            syslog.syslog(syslog.LOG_DEBUG,
                          "pvoutput: %s: Database OperationalError '%s'" %
                          (self.protocol_name, e))

        return _datadict

    def post_with_retries(self, request, payload=None):
        """Post a request, retrying if necessary and returning a response.

        Attempts to post the request object up to max_tries times and returns
        the response. Catches a set of generic exceptions.

        Identical to the abstract class post_with_retries() method except that
        this method returns the server response to the post.

        Input:
            request: An instance of urllib2.Request

            payload: If given, the request will be done as a POST. Otherwise,
                     as a GET. [optional]

        Returns:
            PVOutput API response.
        """

        # Retry up to max_tries times:
        for _count in range(self.max_tries):
            try:
                # Do a single post. The function post_request() can be
                # specialized by a RESTful service to catch any unusual
                # exceptions.
                _response = self.post_request(request, payload)
                if 200 <= _response.code <= 299:
                    # No exception thrown and we got a good response code, but
                    # we're still not done.  Some protocols encode a bad
                    # station ID or password in the return message.
                    # Give any interested protocols a chance to examine it.
                    self.check_response(_response)
                    # Does not seem to be an error. We're done.
                    return _response
                # We got a bad response code. By default, log it and try again.
                # Provide method for derived classes to behave otherwise if
                # necessary.
                self.handle_code(_response.code, _count+1)
            except (urllib2.URLError, socket.error, httplib.BadStatusLine, httplib.IncompleteRead), e:
                # An exception was thrown. By default, log it and try again.
                # Provide method for derived classes to behave otherwise if
                # necessary.
                self.handle_exception(e, _count+1)
            time.sleep(self.retry_wait)
        else:
            # This is executed only if the loop terminates normally, meaning
            # the upload failed max_tries times. Raise an exception. Caller
            # can decide what to do with it.
            raise FailedPost("Failed upload after %d tries" % (self.max_tries,))

    def check_response(self, response):
        """Check the response from a HTTP post."""

        # The expected response code from PVOutput is 200. If we have something
        # else it must be in the range 201-299 incl, not an error just
        # unexpected so just log it and continue.
        if response.code != 200:
            syslog.syslog(syslog.LOG_INFO,
                          "pvoutput: %s: Unexpected response code: %s" %
                          (self.protocol_name, response.code))

    def getsystem(self, secondary_array=0, tariffs=0, teams=0,
                  month_estimates=0, donations=1, sid1=0, extended=0):
        """Retrieve system information from PVOutput API."""

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

        # get the url to be used
        url = self.server_url + self.SERVICE_SCRIPT['getsystem']
        # create a Request object
        _request = urllib2.Request(url=url)
        # if debug >= 2 then log some details of our request
        if weewx.debug >= 2:
            syslog.syslog(syslog.LOG_DEBUG,
                          "pvoutput: %s: url: %s payload: %s" %
                              (self.protocol_name, url, urllib.urlencode(params)))
        # add our headers, in this case sid and api_key
        _request.add_header('X-Pvoutput-Apikey', self.api_key)
        _request.add_header('X-Pvoutput-SystemId', self.sid)
        # post the request
        _response = self.post_with_retries(_request, urllib.urlencode(params))
        # if debug >= 2 then log some details of the response
        if weewx.debug >= 2:
            syslog.syslog(syslog.LOG_DEBUG,
                          "pvoutput: %s: response: %s" % (self.protocol_name,
                                                          _response.read()))
        # return a list of dicts
        return _to_dict(_response.read(), GETSYSTEM_FIELDS, single_dict=True)

    def skip_this_post(self, time_ts):
        """Determine whether a post is to be skipped or not.

        Use one or more checks to determine whether a post is to be skipped or
        not. In this case the post is skipped if the record is:
        -   Too old (based on the 'stale' property). This check is kept to
            honor the existing 'stale' property, PVOutput has a max age for
            which status data can be posted, we store this value as
            self.update_period.
        -   Outside the maximum age that PVOutput will accept (varies by
            donation status)
        -   Posted too soon after our last post.
        """

        # don't post if this record is too old (stale)
        if self.stale is not None:
            _how_old = time.time() - time_ts
            if _how_old > self.stale:
                syslog.syslog(syslog.LOG_DEBUG,
                              "pvoutput: %s: record %s is stale (%d > %d)." %
                                  (self.protocol_name,
                                   timestamp_to_string(time_ts),
                                   _how_old,
                                   self.stale))
                return True

        # don't post if this record is older than that accepted by PVOutput
        if self.update_period is not None:
            now_dt = datetime.datetime.fromtimestamp(time.time())
            _earliest_dt = now_dt - datetime.timedelta(days=self.update_period)
            _earliest_ts = time.mktime(_earliest_dt.timetuple())
            if time_ts < _earliest_ts:
                how_old = (now_dt - datetime.datetime.fromtimestamp(time_ts)).days
                syslog.syslog(syslog.LOG_DEBUG,
                              "pvoutput: %s: record %s is older than PVOuptut imposed limits (%d > %d)." %
                                  (self.protocol_name,
                                   timestamp_to_string(time_ts),
                                   _how_old,
                                   self.self.update_period))
                return True

        # if we have a minimum interval between posts then don't post if that
        # interval has not passed
        if self.post_interval is not None:
            _how_long = time_ts - self.lastpost
            if _how_long < self.post_interval:
                syslog.syslog(syslog.LOG_DEBUG,
                              "pvoutput: %s: wait interval (%d < %d) has not passed for record %s" %
                                  (self.protocol_name,
                                   _how_long,
                                   self.post_interval,
                                   timestamp_to_string(time_ts)))
                return True

        self.lastpost = time_ts
        return False


# ============================================================================
#                  error classes used by class PVOutputAPI
# ============================================================================


class PVUploadError(StandardError):
    """Raised when data to PV Output does not upload correctly."""

class HTTPResponseError(StandardError):
    """Raised when HTTP request returns an error."""


# ============================================================================
#                            class PVOutputAPI
# ============================================================================


class PVOutputAPI(object):
    """Class to interact with PVOutput API."""

    SERVICE_SCRIPT = {'addstatus': '/service/r2/addstatus.jsp',
                      'addbatchstatus': '/service/r2/addbatchstatus.jsp',
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
        system = self.getsystem(donations=1)
        if system[0]['donations'] == '1':
            self.max_batch_size = 100
            self.oldest_batch_date = 90
        else:
            self.max_batch_size = 30
            self.oldest_batch_date = 14

    def request_with_retries(self, service_script, data=None):
        """Send a request to the PVOutput API retrying if required."""

        # get the url to be used
        url = self.base_url + service_script
        payload = urllib.urlencode(data)
        # create a Request object
        # request = urllib2.Request(url=url, data=urllib.urlencode(data))
        request = urllib2.Request(url=url)
        # add our headers, in this case sid and api_key
        request.add_header('X-Pvoutput-Apikey', self.api_key)
        request.add_header('X-Pvoutput-SystemId', self.sid)
        # try to post the request up to max_tries times
        for _count in range(self.max_tries):
            # use a try..except to catch any errors
            try:
                # do the post and get the response
                _response = self._post_request(request, payload)
                # check the response status code, PVOutput will return 200 if
                # all was OK
                _status_code = _response.getcode()
                if _status_code == 200:
                    # we have a good status so we are done
                    ##if service_script == '/service/r2/addstatus.jsp':
                    ##    raise HTTPResponseError("%s returned a bad HTTP response code: %s" % (url,
                    ##                                                                          _status_code))
                    break
                else:
                    # something went wrong, so raise it
                    raise HTTPResponseError("%s returned a bad HTTP response code: %s" %
                                                (url, _status_code))
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

    def _post_request(self, request, payload=None):
        """Post a request object."""

        try:
            # Python 2.5 and earlier does not have a 'timeout' parameter so be
            # prepared to catch the exception and try a Pythoin 2.5 compatible
            # call.
            _response = urllib2.urlopen(request,
                                        data=payload,
                                        timeout=self.timeout)
        except TypeError:
            # Python 2.5 compatible call
            _response = urllib2.urlopen(request, data=payload)
        return _response

    def request_with_retries_orig(self, service_script, data=None):
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
                    if service_script == '/service/r2/addstatus.jsp':
                        raise HTTPResponseError("%s returned a bad HTTP response code: %s" %
                                                    (url, _status_code))
                    break
                else:
                    # something went wrong, so raise it
                    raise HTTPResponseError("%s returned a bad HTTP response code: %s" %
                                                (url, _status_code))
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

    def _post_request_orig(self, request):
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
        """Retrieve system status information and live output data.

        Inputs:
            date: Date for which status information is sought. String, format
                  YYYYMMDD.
            time: Time for which status information is sought. String, format
                  hh:mm.
            from: Time from when status information is required. String,
                  format hh:mm.
            to:   Time to when status information is required. String, format
                  hh:mm.
            history: If set to 1 return all status information for a given date.
                     If time is set then only information after this time is
                     returned. Number.
            ascending: If set to 1 return all status information in ascending
                       order of time. Number.
            limit: Limit number of status information records returned. Number
                   1 to 288. Default 30.

        Returns a list of dictionaries containing the requested status
        information.
        """

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
            return _to_dict(_response, GETSTATUS_HISTORY_FIELDS)
        else:
            return _to_dict(_response, GETSTATUS_FIELDS, single_dict=True)

    def addstatus(self, record, cumulative=False, net=False, net_delay=0):
        """Add a status to the system.

        Input:
            record:     A weewx archive record containing the data to be added.
                        Dictionary.
            cumulative: Set if energey field passed is lifetime cumulative
                        (rather than daytime cumulative). Boolean, default
                        False.
            net:        Set if the power values passed are net export/import
                        (rather than gross generation/consumption). Boolean,
                        default False.
            net_delay:  Delay processing of the data by specified number of
                        minutes. Numeric, default 0.
        Returns:
            PVOutput API response code for addstatus request
            eg 'OK 200: Added Status' if successful. returns None if addstatus
            unsuccessful.
        """

        # map our record fields to the optional fields accepted by the API
        ADDSTATUS_PARAMS = {'energy': 'v1',
                            'gridPower': 'v2',
                            'energyCons': 'v3',
                            'powerCons': 'v4',
                            'inverterTemp': 'v5',
                            'gridVoltage': 'v6',
                            'extended1': 'v7',
                            'extended2': 'v8',
                            'extended3': 'v9',
                            'extended4': 'v10',
                            'extended5': 'v11',
                            'extended6': 'v12'}

        # initialise our parameter dictionary
        params = {}
        # add date and time for this record
        time_tt = time.localtime(record['dateTime'])
        params['d'] = time.strftime("%Y%m%d", time_tt)
        params['t'] = time.strftime("%H:%M", time_tt)
        # add c1 parameter if cumulative is set
        if cumulative:
            params['c1'] = 1
        # add n parameter if net is set
        if net:
            params['n'] = 1
        # add delay parameter if we have a value
        if net_delay > 0:
            params['delay'] = net_delay

        # add any optional parameters from our record
        for rec_field, API_field in ADDSTATUS_PARAMS.iteritems():
            if rec_field in record and record[rec_field] is not None:
                params[API_field] = record[rec_field]

        # submit the request to the API and return the response
        try:
            response = self.request_with_retries(self.SERVICE_SCRIPT['addstatus'],
                                                 params)
        except HTTPResponseError, e:
            # should be syslog
            print ("addstatus: Failed to upload status for %s:" %
                       timestamp_to_string(record['dateTime']))
            print "addstatus:      %s" % e

    def addbatchstatus(self, records, cumulative=False):
        """Add a batch status to the system."""

        # list of fields (excluding date and time) in order as required by
        # the API
        ADDBATCHSTATUS_PARAMS = ['energy', 'powergen', 'energycons',
                                 'powercons', 'temperature', 'voltage',
                                 'extended1', 'extended2', 'extended3',
                                 'extended4', 'extended5', 'extended6']

        # construct the 'data' parameter string
        _data_list = []
        # step through each record
        for record in records:
            # resest the parameter list for this record
            _param_list = []
            # add date and time for this record
            time_tt = time.localtime(record['dateTime'])
            _param_list.append(time.strftime("%Y%m%d", time_tt))
            _param_list.append(time.strftime("%H:%M", time_tt))
            # step through each of the optional parameters for the record and
            # add them to the parameter list if they are not None. Add a ''
            # as a placeholder if we don't have a value for a given parameter.
            for _param in ADDBATCHSTATUS_PARAMS:
                if _param in record:
                    if record[_param]:
                        _param_list.append(str(record[_param]))
                    else:
                        _param_list.append('')
                else:
                    _param_list.append('')
            # Convert the completed parameter list to a comma separated string
            # stripping off any right hand repeated commas then add the string
            # to our 'data' list.
            _data_list.append(','.join(_param_list).rstrip(','))
        # convert the data list to a string of semi-colon separated individual
        # status parameter strings
        _data_str = ';'.join(_data_list)

        # define the parameter dict for the API request
        params = {'data': _data_str}
        # add c1 parameter if cumulative is set
        if cumulative:
            params['c1'] = 1

        # submit the request to the API
        response = self.request_with_retries(self.SERVICE_SCRIPT['addbatchstatus'],
                                             params)

        # Check any response. request_with_retires() took care of whether
        # there were any HTTP error codes, we just need to check that each
        # status was accepted.
        # split the response into individual record responses
        results = response.split(";")
        # did we get the same number of responses as records we sent?
        if len(results) != len(records):
            raise PVUploadError("addbatchstatus: Unexpected number results.")
        # Now go through each records result and check for success. If a record
        # failed to upload then log raise it.
        for _result in results:
            # split an individual records result into its component fields
            _date, _time, _status = _result.split(",")
            # if we failed to upload the records sucessfully
            if _status != "1":
                # get a timestamp of the record
                datetime_dt = datetime.datetime.strptime("%Y%m%d %H;%M",
                                                         " ".join(_date, _time))
                datetime_ts = time.mktime(datetime_dt.timetuple())
                # raise the error
                raise PVUploadError("addbatchstatus: Failed to upload status for %s" %
                                        timestamp_to_string(datetime_ts))
        # if we made it here everything uploaded without error so return the
        # response for use by the caller if required
        return response

    def deletestatus(self, ts):
        """Remove an existing status from the system.

        Deletes the status matching a given timestamp. A ts of None results in
        no action and a returned value of None. Note that PVOutput API returns
        a respone message of 'OK 200: Deleted Status' even when deleting a
        non-existent status.

        Input:
            ts: timestamp to be deleted
        Returns:
            PVOutput API response code for deletestatus request
            eg 'OK 200: Deleted Status' if successful. None is ts is None.
        """

        # construct the parameter dict for the request
        params = {}
        time_tt = time.localtime(ts)
        params['d'] = time.strftime("%Y%m%d", time_tt)
        params['t'] = time.strftime("%H:%M", time_tt)
        # submit the request
        return self.request_with_retries(self.SERVICE_SCRIPT['deletestatus'],
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
        return _to_dict(_response, GETSYSTEM_FIELDS, single_dict=True)

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
        return self.request_with_retries(self.SERVICE_SCRIPT['getoutput'],
                                         params)

# ============================================================================
#                            Utility Functions
# ============================================================================


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

# define a main entry point used for basic testing of the PVOutpu thread during
# development. Does away with the need for the weewx engine and service
# overhead. To invoke this:
#
# PYTHONPATH=/home/weewx/bin python /home/weewx/bin/user/pvoutput.py

if __name__ == '__main__':
    import weewx.engine
    import os.path
    import Queue
    import weewx.manager
    import weewx.restx

    config_path = os.path.abspath('/home/weewx/weewx.conf')
    config_dict = weewx.engine.getConfiguration(config_path)
    q = Queue.Queue()
    _manager_dict = weewx.manager.get_manager_dict_from_config(config_dict,
                                                               'aurora_binding')
    _pvoutput_dict = weewx.restx.get_site_dict(config_dict,
                                               'PVOutput',
                                               'system_id',
                                               'api_key')
    _pvoutput_dict.setdefault('server_url', StdPVOutput.api_url)
    pv_thread = PVOutputThread(q,
                               _manager_dict,
                               protocol_name="PVOutput-API",
                               **_pvoutput_dict)
    pv_thread.start()
    record = {'dateTime':1482743100, 'energy':31590,
              'temperature':37.5, 'voltage':250.0}
    time.sleep(2)

    q.put(record)
    record = {'dateTime':1482743400, 'energy':31590,
              'temperature':37.5, 'voltage':250.0}
    time.sleep(2)
    q.put(record)
    time.sleep(10)
