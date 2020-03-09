"""
pvoutput.py

A WeeWX RESTful service to upload PV data to PVOutput.

Copyright (C) 2016 Gary Roderick                  gjroderick<at>gmail.com

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program.  If not, see http://www.gnu.org/licenses/.

Version: 0.4.0a1                                    Date: 8 March 2020

Revision History
    8 March 2020        v0.4.0
        - now WeeWX 4.0 python2/3 compatible
    1 February 2018     v0.3.0
        - release as a WeeWX extension
    24 February 2017    v0.2.3
        - added missing socket import
        - fixed incorrect FailedPost call
    14 February 2017    v0.2.2
        - fixed incorrect record fields used in PVOutputAPI.addbatchstatus()
        - removed some early development code
        - documented signatures for PVOutputAPI.request_with_retries(),
          PVOutputAPI._post_request() and PVOutputAPI.addbatchstatus()
        - PVOutputAPI.addstatus() now correctly returns the PVOutput response
        - added 'to do' list to comments
    13 February 2017    v0.2.1
        - fixed issue where an uncaught socket.timeout exception would crash
          PVOutputThread
    7 February 2017    v0.2.0
        - check to ensure that PVOutputThread has the minimum required fields
          to post a status to PVOutput
    17 December 2016   v0.1.0
        - initial release

Classes StdPVOutput and PVOutputThread are used as a WeeWX RESTful service to
post data to PVOutput.org.

Class PVOuputAPI provides the ability to add, update, read and delete system
data on PVOutput.org via the PVOutput API.

Pre-requisites:

Currently this uploader requires the following fields to be present in the
WeeWX archive:

    - dayEnergy
    - gridPower
    - energyCons
    - powerCons
    - inverterTemp
    - gridVoltage
    - extended1
    - extended2
    - extended3
    - extended4
    - extended5
    - extended6

    Note: 1. At least one of dayEnergy, gridPower, energyCons or powerCons must
             be present.
          2. extended1-6 only able to be used if a PVOutput donor.
          3. A future release of this uploader will enable the user to specify
             which WeeWX fields are to be uploaded to PVOutput.

To use:

1.  Copy this file to /home/weewx/bin/user.

2.  Edit weewx.conf as follows:

    - under [StdRESTful] add a [PVOutput]] stanza as follows entering
      your system settings for system_id and api_key:

    [[PVOutput]]
        # This section is for configuring posts to PVOutput.

        # If you wish to do this, set the option 'enable' to true,
        # and specify a station and password.
        enable = true
        system_id = ENTER_PVOUTPUT_SYSTEM_ID_HERE
        api_key = ENTER_PVOUTPUT_API_KEY_HERE

    - under [Engine] [[Services]] add user.pvoutput.StdPVOutput to
      restful_services

3.  Restart WeeWX.

4.  WeeWX will then upload a status record to PVOutput at the end of each WeeWX
    archive period.
"""

# Python imports
import datetime
import logging
import socket
import sys
import time

# Python 2/3 compatibility shims
from six.moves import queue
from six.moves import urllib
from six.moves import http_client

# WeeWX imports
import weedb
import weewx.restx
import weewx.units
from weeutil.weeutil import timestamp_to_string, startOfDay

# get a logger object
log = logging.getLogger(__name__)


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
        _pvoutput_dict = weewx.restx.get_site_dict(config_dict,
                                                   'PVOutput',
                                                   'system_id',
                                                   'api_key')
        if _pvoutput_dict is None:
            return
        _pvoutput_dict.setdefault('server_url', StdPVOutput.api_url)

        # get the manager dictionary:
        _manager_dict = weewx.manager.get_manager_dict_from_config(config_dict,
                                                                   'aurora_binding')

        # create a Queue object to pass records to the thread
        self.archive_queue = queue.Queue()
        # create our thread
        self.archive_thread = PVOutputThread(self.archive_queue,
                                             _manager_dict,
                                             protocol_name=StdPVOutput.protocol_name,
                                             **_pvoutput_dict)
        # start the thread
        self.archive_thread.start()
        # bind to NEW_ARCHIVE_RECORD event
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        log.info("%s: Data for system ID %s will be posted" % (StdPVOutput.protocol_name,
                                                               _pvoutput_dict['system_id']))

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
                 max_backlog=sys.maxsize, stale=None, log_success=True,
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

        # initialize my superclass:
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
        # now summarize what we are doing in a few log entries
        log.debug("server url=%s" % self.server_url)
        log.debug("cumulative_energy=%s net=%s net_delay=%d tariffs=%s" % (self.cumulative,
                                                                           self.net,
                                                                           self.net_delay,
                                                                           self.tariffs))
        log.debug("max batch size=%d max update period=%d days" % (self.max_batch_size,
                                                                   self.update_period))

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
        addstatus_params = {'dayEnergy': 'v1',
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
        required_params = ['v1', 'v2', 'v3', 'v4']

        # Get any extra data (that is not in record) required to post a status
        # to PVOutput. In this case we need today's cumulative energy.
        _full_record = self.get_record(record, dbmanager)

        # Do we have the minimum required fields to post a status ? Probably
        # should do this in skip_record() but to do so would require knowledge
        # of the record being posted and that would mean overriding run_loop()
        # just to change 1 line of code.
        for rec_field, api_field in addstatus_params.items():
            if api_field in required_params:
                if rec_field in record and record[rec_field] is not None:
                    # we have one, break so we can process the record
                    break
        else:
            # if we got here it is becase we have none of the required fields,
            # raise and AbortedPost exception and restx will skip posting
            raise weewx.restx.AbortedPost()

        # convert to metric if necessary
        _metric_rec = weewx.units.to_METRIC(_full_record)

        # initialise our parameter dictionary
        params = {}
        # add date and time for this record
        time_tt = time.localtime(_metric_rec['dateTime'])
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
        for rec_field, api_field in addstatus_params.items():
            if rec_field in _metric_rec and _metric_rec[rec_field] is not None:
                params[api_field] = _metric_rec[rec_field]

        # get the url to be used
        url = self.server_url + self.SERVICE_SCRIPT['addstatus']
        # create a Request object
        _request = urllib.request.Request(url=url)
        # if debug >= 2 then log some details of our request
        if weewx.debug >= 2:
            log.debug("%s: url: %s payload: %s" % (self.protocol_name,
                                                   url,
                                                   urllib.parse.urlencode(params)))
        # add our headers, in this case sid and api_key
        _request.add_header('X-Pvoutput-Apikey', self.api_key)
        _request.add_header('X-Pvoutput-SystemId', self.sid)
        decoded_response = self.post_with_retries(_request,
                                                  urllib.parse.urlencode(params))
        # if debug >= 2 then log some details of the response
        if weewx.debug >= 2:
            log.debug("%s: response: %s" % (self.protocol_name,
                                            decoded_response))

    def get_record(self, record, dbmanager):
        """Augment record data with additional data derived from the archive.

        PVOutput requires 'energy' in each status record to be a cumulative
        value (either day or lifetime). Cumulative values are not normally
        included in a weewx record/packet so we need to calculate the data
        from the archive. In this case we will use the day cumulative total.
        Returns results in the same units as the record.

        Input:
            record:    A weewx archive record containing the data to be added.
                       Dictionary.
            dbmanager: Manager object for the database being used. Object.
        Returns:
            A dictionary of values
        """

        _time_ts = record['dateTime']
        _sod_ts = startOfDay(_time_ts)

        # make a copy of the record, then start adding to it
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
                                         (_result[1], _result[2], record['usUnits']))
                    _datadict['dayEnergy'] = _result[0]
                else:
                    _datadict['dayEnergy'] = None

        except weedb.OperationalError as e:
            log.debug("%s: Database OperationalError '%s'" % (self.protocol_name, e))

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

        # retry up to max_tries times
        for _count in range(self.max_tries):
            try:
                # Do a single post. The function post_request() can be
                # specialized by a RESTful service to catch any unusual
                # exceptions.
                response = self.post_request(request, payload)
                # Get charset used so we can decode the stream correctly.
                # Unfortunately the way to get the charset depends on whether
                # we are running under python2 or python3. Assume python3 but be
                # prepared to catch the error if python2.
                try:
                    char_set = response.headers.get_content_charset()
                except AttributeError:
                    # must be python2
                    char_set = response.headers.getparam('charset')
                # now get the response decoding it appropriately
                decoded_response = response.read().decode(char_set)
                # now look at the response code
                if 200 <= response.code <= 299:
                    # No exception thrown and we got a good response code, but
                    # we're still not done.  Some protocols encode a bad
                    # station ID or password in the return message.
                    # Give any interested protocols a chance to examine it.
                    self.check_response(response)
                    # Does not seem to be an error. We're done.
                    response.close()
                    return decoded_response
                # We got a bad response code. By default, log it and try again.
                # Provide method for derived classes to behave otherwise if
                # necessary.
                self.handle_code(response.code, _count+1)
            except (urllib.error.URLError, socket.error,
                    http_client.BadStatusLine, http_client.IncompleteRead) as e:
                # An exception was thrown. By default, log it and try again.
                # Provide method for derived classes to behave otherwise if
                # necessary.
                self.handle_exception(e, _count+1)
            time.sleep(self.retry_wait)
        else:
            # This is executed only if the loop terminates normally, meaning
            # the upload failed max_tries times. Raise an exception. Caller
            # can decide what to do with it.
            raise weewx.restx.FailedPost("Failed upload after %d tries" %
                                         (self.max_tries,))

    def check_response(self, response):
        """Check the response from a HTTP post."""

        # The expected response code from PVOutput is 200. If we have something
        # else it must be in the range 201-299 incl, not an error just
        # unexpected so just log it and continue.
        if response.code != 200:
            log.debug("%s: Unexpected response code: %s" % (self.protocol_name,
                                                            response.code))

    def getsystem(self, secondary_array=0, tariffs=0, teams=0,
                  month_estimates=0, donations=1, sid1=0, extended=0):
        """Retrieve system information from PVOutput API."""

        # define the fields returned by the API
        base = ['name', 'size', 'postcode', 'num_panels', 'panel_power',
                'panel_brand', 'num_inverters', 'inverter_power',
                'inverter_brand', 'orientation', 'tilt', 'shade',
                'install_date', 'latitude', 'longitude', 'interval']
        secondary = ['sec_num_panels', 'sec_panel_power', 'sec_panel_brand',
                     'sec_num_inverters']
        tariff = ['export', 'import_peak', 'import_off_peak',
                  'import_shoulder', 'import_high_shoulder',
                  'import_daily_charge']
        teams = ['teams']
        donations = ['donations']
        extended = ['extended']

        # construct the parameter dict to be sent as part of our API request
        params = dict()
        params['array2'] = secondary_array
        params['tariffs'] = tariffs
        params['teams'] = teams
        params['est'] = month_estimates
        params['donations'] = donations
        params['sid1'] = sid1
        params['ext'] = extended

        # assemble a list of lists of the fields we expect to be returned
        getsystem_fields = [base]
        if params['array2'] == 1:
            getsystem_fields.append(secondary)
        if self.tariffs:
            getsystem_fields.append(tariff)
        if params['teams'] == 1:
            getsystem_fields.append(teams)
        getsystem_fields.append(donations)
        if params['ext'] == 1:
            getsystem_fields.append(extended)

        # get the url to be used
        url = self.server_url + self.SERVICE_SCRIPT['getsystem']
        # create a Request object
        _request = urllib.request.Request(url=url)
        # if debug >= 2 then log some details of our request
        if weewx.debug >= 2:
            log.debug("%s: url: %s payload: %s" % (self.protocol_name,
                                                   url,
                                                   urllib.parse.urlencode(params)))
        # add our headers, in this case sid and api_key
        _request.add_header('X-Pvoutput-Apikey', self.api_key)
        _request.add_header('X-Pvoutput-SystemId', self.sid)
        # post the request
        decoded_response = self.post_with_retries(_request, urllib.parse.urlencode(params))
        # if debug >= 2 then log some details of the response
        if weewx.debug >= 2:
            log.debug("%s: response: %s" % (self.protocol_name,
                                            decoded_response))
        # return a list of dicts
        return _to_dict(decoded_response, getsystem_fields, single_dict=True)

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
            how_old = time.time() - time_ts
            if how_old > self.stale:
                log.debug("%s: record %s is stale (%d > %d)." % (self.protocol_name,
                                                                 timestamp_to_string(time_ts),
                                                                 how_old,
                                                                 self.stale))
                return True

        # don't post if this record is older than that accepted by PVOutput
        if self.update_period is not None:
            now_dt = datetime.datetime.fromtimestamp(time.time())
            _earliest_dt = now_dt - datetime.timedelta(days=self.update_period)
            _earliest_ts = time.mktime(_earliest_dt.timetuple())
            if time_ts < _earliest_ts:
                how_old = (now_dt - datetime.datetime.fromtimestamp(time_ts)).days
                log.debug("%s: record %s is older than PVOutput imposed limits (%d > %d)." % (self.protocol_name,
                                                                                              timestamp_to_string(time_ts),
                                                                                              how_old,
                                                                                              self.self.update_period))
                return True

        # if we have a minimum interval between posts then don't post if that
        # interval has not passed
        if self.post_interval is not None:
            how_long = time_ts - self.lastpost
            if how_long < self.post_interval:
                log.debug("%s: wait interval (%d < %d) has not passed for record %s" % (self.protocol_name,
                                                                                        how_long,
                                                                                        self.post_interval,
                                                                                        timestamp_to_string(time_ts)))
                return True

        self.lastpost = time_ts
        return False


# ============================================================================
#                  error classes used by class PVOutputAPI
# ============================================================================


class PVUploadError(Exception):
    """Raised when data to PV Output does not upload correctly."""


class HTTPResponseError(Exception):
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
        """"Initialise the PVOutputAPI object."""

        self.sid = kwargs.get('sid')
        self.api_key = kwargs.get('api_key')
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
        """Send a request to the PVOutput API retrying if required.

        Inputs:
            service_script: Path and script name of a PVOutput service.
                            Normally a value from the SERVICE_SCRIPT dict.
            data:           The data payload to be sent with the request.

        Returns:
            The data in the file like object response to a urllib2.urlopen()
            call.
        """

        # get the url to be used
        url = self.base_url + service_script
        payload = urllib.parse.urlencode(data)
        # create a Request object
        request = urllib.request.Request(url=url)
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
                    break
                else:
                    # something went wrong, so raise it
                    raise HTTPResponseError("%s returned a bad HTTP response code: %s" %
                                            (url, _status_code))
            except urllib.error.URLError as e:
                # If we have a reason for the error then we likely didn't get
                # to the server. Log the error and continue.
                if hasattr(e, 'reason'):
                    print("Failed to reach a server. Reason: %s" % e.reason)
                # If we have a code we did get to the server but it returned an
                # error. Log the error and continue.
                if hasattr(e, 'code'):
                    print("The server returned an error. Error code: %s" % e.code)
            time.sleep(self.retry_wait)
        return _response.read()

    def _post_request(self, request, payload=None):
        """Post a request object.

        Inputs:
            request: A class urllib2.Request object.
            payload: A 'percent' encoded data string to be sent with the
                     request.

        Returns:
            The file like object response from a urllib2.urlopen() call.
        """

        _response = urllib.request.urlopen(request,
                                           data=payload,
                                           timeout=self.timeout)
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

        # map our kwargs input parameters to the fields required by the API
        getstatus_params = {'date': 'd',
                            'time': 't',
                            'from': 'from',
                            'to': 'to',
                            'sid1': 'sid1'}
        # define the fields returned by the API, there are 2 cases (1) for a
        # single (ie non-history) request and (2) for a history request
        getstatus_fields = [['date', 'time', 'energy_generation',
                             'power_generation', 'energy_consumption',
                             'power_consumption', 'efficiency', 'temperature',
                             'voltage', 'ext1', 'ext2', 'ext3', 'ext4', 'ext5',
                             'ext6', ]]
        getstatus_history_fields = [['date', 'time', 'energy_generation',
                                     'energy_efficiency', 'inst_power',
                                     'avg_power', 'normalised_output',
                                     'energy_consumption', 'power_consumption',
                                     'temperature', 'voltage', 'ext1', 'ext2',
                                     'ext3', 'ext4', 'ext5', 'ext6']]

        # construct the parameter dict to be sent as part of our API request
        # first set those parameters that have a default value
        params = dict()
        params['h'] = history
        params['asc'] = ascending
        params['limit'] = limit
        params['ext'] = extended

        # now trawl our kwargs and add
        for var, data in kwargs.items():
            if var in getstatus_params and data is not None:
                params[getstatus_params[var]] = data

        # submit the request to the API
        decoded_response = self.request_with_retries(self.SERVICE_SCRIPT['getstatus'],
                                                     params)
        # return our result as a list of dicts
        if params['h'] == 1:
            return _to_dict(decoded_response, getstatus_history_fields)
        else:
            return _to_dict(decoded_response, getstatus_fields, single_dict=True)

    def addstatus(self, record, cumulative=False, net=False, net_delay=0):
        """Add a status to the system.

        Input:
            record:     A weewx archive record containing the data to be added.
            cumulative: Set if energy field passed is lifetime cumulative
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
        addstatus_params = {'energy': 'v1',
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
        for rec_field, API_field in addstatus_params.items():
            if rec_field in record and record[rec_field] is not None:
                params[API_field] = record[rec_field]

        # submit the request to the API and return the response
        try:
            return self.request_with_retries(self.SERVICE_SCRIPT['addstatus'],
                                             params)
        except HTTPResponseError as e:
            # log the error
            log.info("Failed to upload status for %s:" % timestamp_to_string(record['dateTime']))
            log.info("      %s" % e)

    def addbatchstatus(self, records, cumulative=False):
        """Add a batch status to the system.

        Input:
            records:    A list of WeeWX archive record containing the data to
                        be added.
            cumulative: Set if energey field passed is lifetime cumulative
                        (rather than daytime cumulative). Boolean, default
                        False.
        Returns:
            PVOutput API response code for addstatus request
            eg 'OK 200: Added Status' if successful. returns None if addstatus
            unsuccessful.
        """

        # list of fields (excluding date and time) in order as required by
        # the API
        addbatchstatus_params = ['energy', 'gridPower', 'energyCons',
                                 'powerCons', 'inverterTemp', 'gridVoltage',
                                 'extended1', 'extended2', 'extended3',
                                 'extended4', 'extended5', 'extended6']

        # construct the 'data' parameter string
        _data_list = []
        # step through each record
        for record in records:
            # reset the parameter list for this record
            _param_list = []
            # add date and time for this record
            time_tt = time.localtime(record['dateTime'])
            _param_list.append(time.strftime("%Y%m%d", time_tt))
            _param_list.append(time.strftime("%H:%M", time_tt))
            # step through each of the optional parameters for the record and
            # add them to the parameter list if they are not None. Add a ''
            # as a placeholder if we don't have a value for a given parameter.
            for _param in addbatchstatus_params:
                if _param in record:
                    if record[_param]:
                        _param_list.append(str(record[_param]))
                    else:
                        _param_list.append('')
                else:
                    _param_list.append('')
            # convert the completed parameter list to a comma separated string
            # stripping off any right hand repeated commas then add the string
            # to our 'data' list
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
            raise PVUploadError("addbatchstatus: Unexpected number of results.")
        # Now go through each records result and check for success. If a record
        # failed to upload then log it and at the end raise it.
        for _result in results:
            # split an individual records result into its component fields
            _date, _time, _status = _result.split(",")
            # if we failed to upload the records successfully
            if _status != "1":
                # get a timestamp of the record
                datetime_dt = datetime.datetime.strptime(" ".join((_date, _time)), "%Y%m%d %H;%M")
                datetime_ts = time.mktime(datetime_dt.timetuple())
                # raise the error
                raise PVUploadError("addbatchstatus: Failed to upload status for %s" % timestamp_to_string(datetime_ts))
        # if we made it here everything uploaded without error so return the
        # response for use by the caller if required
        return response

    def deletestatus(self, ts):
        """Remove an existing status from the system.

        Deletes the status matching a given timestamp. A ts of None results in
        no action and a returned value of None. Note that PVOutput API returns
        a response message of 'OK 200: Deleted Status' even when deleting a
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
        base = ['name', 'size', 'postcode', 'num_panels', 'panel_power',
                'panel_brand', 'num_inverters', 'inverter_power',
                'inverter_brand', 'orientation', 'tilt', 'shade',
                'install_date', 'latitude', 'longitude', 'interval']
        secondary = ['sec_num_panels', 'sec_panel_power', 'sec_panel_brand',
                     'sec_num_inverters']
        tariff = ['export', 'import_peak', 'import_off_peak',
                  'import_shoulder', 'import_high_shoulder',
                  'import_daily_charge']
        teams = ['teams']
        donations = ['donations']
        extended = ['extended']

        # construct the parameter dict to be sent as part of our API request
        params = dict()
        params['array2'] = secondary_array
        params['tariffs'] = tariffs
        params['teams'] = teams
        params['est'] = month_estimates
        params['donations'] = donations
        params['sid1'] = sid1
        params['ext'] = extended

        # assemble a list of lists of the fields we expect to be returned
        getsystem_fields = [base]
        if params['array2'] == 1:
            getsystem_fields.append(secondary)
        if self.tariffs:
            getsystem_fields.append(tariff)
        if params['teams'] == 1:
            getsystem_fields.append(teams)
        getsystem_fields.append(donations)
        if params['ext'] == 1:
            getsystem_fields.append(extended)

        # submit the request to the API
        decoded_response = self.request_with_retries(self.SERVICE_SCRIPT['getsystem'],
                                                     params)
        # return a list of dicts
        return _to_dict(decoded_response, getsystem_fields, single_dict=True)

    def getoutput(self, **kwargs):
        """Retrieve system or team daily output information."""

        getoutput_params = {'from': 'df',
                            'to': 'dt',
                            'aggregate': 'a',
                            'limit': 'limit',
                            'team_id': 'tid',
                            'sid1': 'sid1'}

        params = {}
        for var, data in kwargs.items():
            if var in getoutput_params and data is not None:
                params[getoutput_params[var]] = data
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
            _row_tuple_list = list(zip(_field, _row_list))
            _result.append(dict(_row_tuple_list))
    if single_dict:
        result = {}
        for dictionary in _result:
            result.update(dictionary)
        return [result]
    else:
        return _result
