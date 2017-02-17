# Aurora extension #

Using [weeWX](http://weewx.com/ "WeeWX - Open source software for your weather station") to record solar PV power generation data from a Power One Aurora inverter and optionally publish this data to [PVOutput](http://pvoutput.org/ "PVOutput.org")

## Description ##

The *Aurora* extension allows weeWX to download, record and report solar PV power generation data from a Power One Aurora inverter. The *Aurora* extension also allows optional posting of solar PV power generation data to PVOutput using the PVOutput API.

The *Aurora* extension consists of:
- a weeWX driver for the Power One Aurora inverter,
- a custom weeWX database schema to support the Aurora inverter,
- a RESTful service for posting data to PVOutput, and
- a utility for bulk uploading of solar PV generation data to PVOutput should Internet access be lost for some period of time.

**Note:** The weeWX driver used in the *Aurora* extension was developed using the *Power One Aurora Inverter Series Communication Protocol Rel 4.7 dated 19 May 2009* and tested on a Power One Aurora Inverter model PVI-6000-OUTD-AU manufactured in November 2010. Whilst there have been changes to the Aurora inverters manufactured since this time, it could reasonably be expected that the *Aurora* extension weeWX driver will work with other Aurora models covered by the *Communication Protocol Rel 4.7*.

## Pre-Requisites ##

The *Aurora* extension requires weeWX v3.7.0 or greater. Use of the *Aurora* extension to upload data to PVOutput requires a PVOutput account with system ID and API access key.

The *Aurora* extension requires a functioning serial communications link between the weeWX machine and the inverter. In my case, this was achieved using a Raspberry Pi 1 model B+ running Raspbian Jessie with a USB-RS485 converter interfacing to the inverter's RS-485 interface. This link functioned without the need for installation of any additional software other than the *Aurora* extension. There is a lot of information on the Internet, in particular the [Whirlpool discussion forum](http://forums.whirlpool.net.au/ "Whirlpool discussion forum"), on interfacing to Aurora inverters.

## Installation ##

The *Aurora* extension can be installed manually or automatically using the *wee_extension* utility. The preferred method of installation is through the use of *wee_extension*.

**Note:** Symbolic names are used below to refer to some file location on the weeWX system. These symbolic names allow a common name to be used to refer to a directory that may be different from system to system. The following symbolic names are used below:

-   *$DOWNLOAD_ROOT*. The path to the directory containing the downloaded *Aurora* extension.
-   *$HTML_ROOT*. The path to the directory where weeWX generated reports are saved. This directory is normally set in the *[StdReport]* section of *weewx.conf*. Refer to [where to find things](http://weewx.com/docs/usersguide.htm#Where_to_find_things "where to find things") in the weeWX [User's Guide](http://weewx.com/docs/usersguide.htm "User's Guide to the weeWX Weather System") for further information.
-   *$BIN_ROOT*. The path to the directory where weeWX executables are located. This directory varies depending on weeWX installation method. Refer to [where to find things](http://weewx.com/docs/usersguide.htm#Where_to_find_things "where to find things") in the weeWX [User's Guide](http://weewx.com/docs/usersguide.htm "User's Guide to the weeWX Weather System") for further information.
-   *$SKIN_ROOT*. The path to the directory where weeWX skin folders are located This directory is normally set in the *[StdReport]* section of *weewx.conf*. Refer to [where to find things](http://weewx.com/docs/usersguide.htm#Where_to_find_things "where to find things") in the weeWX [User's Guide](http://weewx.com/docs/usersguide.htm "User's Guide to the weeWX Weather System") for further information.

### Installation using the wee_extension utility ###

1.  Download the latest *Aurora* extension from the *Aurora* extension [releases page](https://github.com/gjr80/weewx-aurora/releases) into a directory accessible from the weeWX machine.
        
        wget -P $DOWNLOAD_ROOT https://github.com/gjr80/weewx-aurora/releases/download/v0.4.0/aurora-0.4.0.tar.gz

    where $DOWNLOAD_ROOT is the path to the directory where the *Aurora* extension is to be downloaded.  

1.  Stop weeWX:

        sudo /etc/init.d/weewx stop

    or

        sudo service weewx stop

1.  Install the *Aurora* extension downloaded at step 1 using the *wee_extension* utility:

        wee_extension --install=$DOWNLOAD_ROOT/aurora-0.4.0.tar.gz

    This will result in output similar to the following:

        Request to install '/var/tmp/aurora-0.4.0.tar.gz'
        Extracting from tar archive /var/tmp/aurora-0.4.0.tar.gz
        Saving installer file to /home/weewx/bin/user/installer/Aurora
        Saved configuration dictionary. Backup copy at /home/weewx/weewx.conf.20170215124410
        Finished installing extension '/var/tmp/aurora-0.4.0.tar.gz'

1.  Edit *weewx.conf*:

        vi weewx.conf
        
1.  Locate the *[Aurora]* section and change the settings to suit your configuration with particular attention to the correct setting of the *port* option:  

        [Aurora]
            model = Aurora PVI-6000
            port = /dev/ttyUSB0
            address = 2
            max_tries = 3
            loop_interval = 10
            use_inverter_time = False
            driver = user.aurora
            [[FieldMap]]
                string1Voltage = getStr1V
                string1Current = getStr1C
                string1Power = getStr1P
                string2Voltage = getStr2V
                string2Current = getStr2C
                string2Power = getStr2P
                gridVoltage = getGridV
                gridCurrent = getGridC
                gridPower = getGridP
                gridFrequency = getFrequency
                inverterTemp = getInverterT
                boosterTemp = getBoosterT
                bulkVoltage = getBulkV
                isoResistance = getIsoR
                bulkmidVoltage = getBulkMidV
                bulkdcVoltage = getBulkDcV
                leakdcCurrent = getLeakDcC
                leakCurrent = getLeakC
                griddcVoltage = getGridDcV
                gridavgVoltage = getGridAvV
                gridnVoltage = getPeakP
                griddcFrequency = getGridDcFreq
                dayEnergy = getDayEnergy

1.  If data is to be posted to PVOutput, locate the *[StdRESTful] [[PVOutput]]* section ensuring *enable* is set to *true* and *system_id* and *api_key* are set appropriately:  

        [StdRESTful]
            [[PVOutput]]
                enable = true
                system_id = replace_me
                api_key = replace_me

    **Note:** *enable* is set to *false* by default during the *Aurora* extension installation.

1.  Save *weewx.conf*.

1.  Edit *$BIN_ROOT/user/extension.py*:

        $ vi extensions.py

1.  Add the following lines to *extensions.py*:

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

1.  Save *extensions.py*.
 
1.  Start weeWX:

        sudo /etc/init.d/weewx start

    or

        sudo service weewx start

The weeWX log should be monitored to verify data is being read from the inverter and, if posting to PVOutput is enabled, data is being posted to PVOutput at the end of each archive period. Setting *debug = 1* or *debug = 2* in *weewx.conf* will provide additional information in the log. Using *debug = 2* will generate significant amounts of log output and should only be used for verification of operation or testing.

### Manual installation ###

1.  Download the latest *Aurora* extension from the *Aurora* extension [releases page](https://github.com/gjr80/weewx-aurora/releases) into a directory accessible from the weeWX machine.

     
        wget -P $DOWNLOAD_ROOT https://github.com/gjr80/weewx-aurora/releases/download/v0.4.0/aurora-0.4.0.tar.gz

    where $DOWNLOAD_ROOT is the path to the directory where the *Aurora* extension is to be downloaded.  

1.  Stop weeWX:

        sudo /etc/init.d/weewx stop

    or

        sudo service weewx stop
        
1.  To be written....

## Support ##

General support issues may be raised in the Google Groups [weewx-user forum](https://groups.google.com/group/weewx-user "Google Groups weewx-user forum"). Specific bugs in the *Aurora* extension code should be the subject of a new issue raised via the *Aurora* extension [Issues Page](https://github.com/gjr80/weewx-aurora/issues "Aurora extension issues").
 
## Licensing ##

The *Aurora* extension is licensed under the [GNU Public License v3](https://github.com/gjr80/weewx-aurora/blob/master/LICENSE "Aurora extension license").

