# Aurora driver extension #

A [weeWX](http://weewx.com/ "WeeWX - Open source software for your weather station") driver for Power One Aurora inverters.

## Description ##

The *Aurora driver* extension allows weeWX to interact with a Power One Aurora inverter to obtain and archive solar PV data from the inverter. The driver interacts with the inverter over a serial connection using the Power One Aurora Inverter Series Communications Protocol to query the inverter state. The driver maps various inverter readings to weeWX loop packet fields and emits loop packets at a user configurable rate.

The *Aurora driver* extension consists of:

- a weeWX driver for the Power One Aurora inverter
- a custom weeWX database schema to support the Aurora inverter

## Pre-Requisites ##

The *Aurora driver* extension requires:

-   weeWX v3.7.0 or greater
-   the *python-serial* package

## Installation ##

The *Aurora driver* extension can be installed manually or automatically using the [*wee_extension* utility](http://weewx.com/docs/utilities.htm#wee_extension_utility). The preferred method of installation is through the use of *wee_extension*.

**Note:** Symbolic names are used below to refer to some file location on the weeWX system. These symbolic names allow a common name to be used to refer to a directory that may be different from system to system. The following symbolic names are used below:

-   *$DOWNLOAD_ROOT*. The path to the directory containing the downloaded *Aurora driver* extension.
-   *$BIN_ROOT*. The path to the directory where weeWX executables are located. This directory varies depending on weeWX installation method. Refer to [where to find things](http://weewx.com/docs/usersguide.htm#Where_to_find_things "where to find things") in the [weeWX User's Guide](http://weewx.com/docs/usersguide.htm "User's Guide to the weeWX Weather System") for further information.

### Installation using the wee_extension utility ###

1.  Download the latest *Aurora driver* extension from the *Aurora driver* extension [releases page](https://github.com/gjr80/weewx-aurora/releases) into a directory accessible from the weeWX machine.

        $ wget -P $DOWNLOAD_ROOT https://github.com/gjr80/weewx-aurora/releases/download/v0.5.0-v0.3.0/aurora-0.5.0.tar.gz

    where *$DOWNLOAD_ROOT* is the path to the directory where the *Aurora driver* extension is to be downloaded.

1.  Stop weeWX:

        $ sudo /etc/init.d/weewx stop

    or

        $ sudo service weewx stop

3.  Install the *Aurora driver* extension downloaded at step 1 using the *wee_extension* utility:

        $ wee_extension --install=$DOWNLOAD_ROOT/aurora-0.5.0.tar.gz

    This will result in output similar to the following:

        Request to install '/var/tmp/aurora-0.5.0.tar.gz'
        Extracting from tar archive /var/tmp/aurora-0.5.0.tar.gz
        Saving installer file to /home/weewx/bin/user/installer/aurora
        Saved configuration dictionary. Backup copy at /home/weewx/weewx.conf.20180128124410
        Finished installing extension '/var/tmp/aurora-0.5.0.tar.gz'

1.  Select and configure the driver:

        $ sudo wee_config --reconfigure

1.  [Run weeWX directly](http://weewx.com/docs/usersguide.htm#Running_directly) and confirm that loop packets and archive records are being generated and the data is appears valid:

        $ sudo weewxd weewx.conf

    **Note:** Depending on the present working directory and your weeWX installation type it may be necessary to prefix *weewxd* and *weewx.conf* with appropriate paths.

    You should now see something like below with a series of loop packets (indicated by *LOOP:* preceding each line) every 10 seconds and archive records (indicated by *REC:* preceding each line) every archive interval seconds:   
    
        LOOP:   2018-02-03 15:54:50 AEST (1517637290) boosterTemp: 96.5233505249, bulkdcVoltage: 381.726715088, bulkmidVoltage: 199.653121948, bulkVoltage: 382.354553223, dateTime: 1517637290, dayEnergy: 8636, energy: 2, gridavgVoltage: 243.444396973, gridCurrent: 2.02972531319, griddcFrequency: 50.0600738525, griddcVoltage: 243.019439697, gridFrequency: 50.0600738525, gridnVoltage: 305.367279053, gridPower: 494.799346924, gridVoltage: 242.946365356, inverterTemp: 95.6759544373, isoResistance: 6.53649520874, leakCurrent: 0.00441941944882, leakdcCurrent: 0.0, string1Current: 0.758069634438, string1Power: 253.94921875, string1Voltage: 359.214996338, string2Current: 0.767736792564, string2Power: 258.066558838, string2Voltage: 357.547058105, timeDate: 1517637291, usUnits: 1
        LOOP:   2018-02-03 15:55:00 AEST (1517637300) boosterTemp: 96.5189491272, bulkdcVoltage: 381.098876953, bulkmidVoltage: 199.653121948, bulkVoltage: 382.354553223, dateTime: 1517637300, dayEnergy: 8637, energy: 1, gridavgVoltage: 243.432281494, gridCurrent: 2.02972531319, griddcFrequency: 50.0841407776, griddcVoltage: 242.313354492, gridFrequency: 50.0831375122, gridnVoltage: 305.144683838, gridPower: 496.422271729, gridVoltage: 242.982879639, inverterTemp: 95.6770530701, isoResistance: 6.53649520874, leakCurrent: 0.00441941944882, leakdcCurrent: 0.0, string1Current: 0.757264018059, string1Power: 253.298355103, string1Voltage: 358.233856201, string2Current: 0.772570431232, string2Power: 257.640594482, string2Voltage: 359.038391113, timeDate: 1517637301, usUnits: 1
        LOOP:   2018-02-03 15:55:10 AEST (1517637310) boosterTemp: 96.5321601868, bulkdcVoltage: 381.098876953, bulkmidVoltage: 199.025268555, bulkVoltage: 382.354553223, dateTime: 1517637310, dayEnergy: 8639, energy: 2, gridavgVoltage: 243.395889282, gridCurrent: 2.0580675602, griddcFrequency: 50.1042175293, griddcVoltage: 242.240203857, gridFrequency: 50.1042175293, gridnVoltage: 306.149841309, gridPower: 497.233734131, gridVoltage: 242.970703125, inverterTemp: 95.6792640686, isoResistance: 6.53649520874, leakCurrent: 0.00441941944882, leakdcCurrent: 0.0, string1Current: 0.757264018059, string1Power: 255.268432617, string1Voltage: 359.882171631, string2Current: 0.775792837143, string2Power: 258.421295166, string2Voltage: 357.488189697, timeDate: 1517637311, usUnits: 1
        LOOP:   2018-02-03 15:55:20 AEST (1517637320) boosterTemp: 96.5244491577, bulkdcVoltage: 381.726715088, bulkmidVoltage: 199.653121948, bulkVoltage: 386.749420166, dateTime: 1517637320, dayEnergy: 8640, energy: 1, gridavgVoltage: 243.347320557, gridCurrent: 2.0580675602, griddcFrequency: 50.1132545471, griddcVoltage: 242.873519897, gridFrequency: 50.1122512817, gridnVoltage: 305.666992188, gridPower: 499.668151855, gridVoltage: 243.116577148, inverterTemp: 95.6946929932, isoResistance: 6.53649520874, leakCurrent: 0.00441941944882, leakdcCurrent: 0.0, string1Current: 0.758069634438, string1Power: 255.205551147, string1Voltage: 360.176513672, string2Current: 0.774987220764, string2Power: 258.839141846, string2Voltage: 357.174224854, timeDate: 1517637321, usUnits: 1
        REC:    2018-02-03 15:55:00 AEST (1517637300) boosterTemp: 96.5136605835, bulkdcVoltage: 381.475579834, bulkmidVoltage: 199.52755127, bulkVoltage: 382.982391357, dateTime: 1517637300.0, dayEnergy: 8634.4, energy: 5.0, gridavgVoltage: 243.495370483, gridCurrent: 2.02964129448, griddcFrequency: 50.0747131348, griddcVoltage: 242.812478638, gridFrequency: 50.0753143311, gridnVoltage: 305.237585449, gridPower: 493.501000977, gridVoltage: 242.841641235, interval: 5, inverterTemp: 95.6761741638, isoResistance: 6.53649520874, leakCurrent: 0.00441941944882, leakdcCurrent: 0.0, string1Current: 0.755330586433, string1Power: 252.531326294, string1Voltage: 358.532122803, string2Current: 0.767897939682, string2Power: 256.399765015, string2Voltage: 359.328808594, timeDate: 1517637281.0, usUnits: 1
        LOOP:   2018-02-03 15:55:30 AEST (1517637330) boosterTemp: 96.5409767151, bulkdcVoltage: 382.354553223, bulkmidVoltage: 199.025268555, bulkVoltage: 382.982391357, dateTime: 1517637330, dayEnergy: 8641, energy: 1, gridavgVoltage: 243.310913086, gridCurrent: 2.0580675602, griddcFrequency: 50.1152648926, griddcVoltage: 242.471786499, gridFrequency: 50.1152648926, gridnVoltage: 305.666992188, gridPower: 500.479614258, gridVoltage: 242.81262207, inverterTemp: 95.7321769714, isoResistance: 6.53649520874, leakCurrent: 0.00441941944882, leakdcCurrent: 0.00441941944882, string1Current: 0.758875250816, string1Power: 255.55909729, string1Voltage: 358.920654297, string2Current: 0.778209626675, string2Power: 260.399230957, string2Voltage: 358.547821045, timeDate: 1517637331, usUnits: 1

    The above indicates that the inverter is being interrogated, valid data being received and weeWX is constructing archive records from the accumulated loop data.

1.  If all appears correct when run directly you can stop weeWX by entering *Ctl-Z* in the terminal and you can now start weeWX as a daemon:
    
        $ sudo /etc/init.d/weewx start
    
    or

        $ sudo service weewx start

1.  The weeWX log should be monitored to verify archive records are being saved.

### Manual installation ###

1.  Download the latest *Aurora driver* extension from the *Aurora driver* extension [releases page](https://github.com/gjr80/weewx-aurora/releases) into a directory accessible from the weeWX machine.

        $ wget -P $DOWNLOAD_ROOT https://github.com/gjr80/weewx-aurora/releases/download/v0.5.0-v0.3.0/aurora-0.5.0.tar.gz

    where *$DOWNLOAD_ROOT* is the path to the directory where the *Aurora driver* extension is to be downloaded.

1.  Stop weeWX:

        $ sudo /etc/init.d/weewx stop

    or

        $ sudo service weewx stop

1.  Unpack the extension as follows:

        $ tar xvfz aurora-0.5.0.tar.gz

1.  Copy files from within the resulting directory as follows:

        $ cp aurora/bin/user/*.py $BIN_ROOT/user

    replacing the symbolic name *$BIN_ROOT* with the nominal locations for your installation.

1.  Edit *weewx.conf*:

        $ vi weewx.conf

1.  Add a new stanza *[Aurora]* as follows entering an appropriate values for model, port and address:

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

1.  Add a new stanza *[Accumulator]* as follows:
 
        [Accumulator]
            [[energy]]
                extractor = sum
        
1.  Confirm/change as required the following settings:

    - *[Station]*:

            station_type = Aurora

    - *[StdArchive]*:
    
            record_generation = software 


1.  Save *weewx.conf*.

1.  [Run weeWX directly](http://weewx.com/docs/usersguide.htm#Running_directly) and confirm that loop packets and archive records are being generated and the data is appears valid:

        $ sudo weewxd weewx.conf

    **Note:** Depending on the present working directory and your weeWX installation type it may be necessary to prefix *weewxd* and *weewx.conf* with appropriate paths.

    You should now see something like below with a series of loop packets (indicated by *LOOP:* preceding each line) every 10 seconds and archive records (indicated by *REC:* preceding each line) every archive interval seconds:   
    
        LOOP:   2018-02-03 15:54:50 AEST (1517637290) boosterTemp: 96.5233505249, bulkdcVoltage: 381.726715088, bulkmidVoltage: 199.653121948, bulkVoltage: 382.354553223, dateTime: 1517637290, dayEnergy: 8636, energy: 2, gridavgVoltage: 243.444396973, gridCurrent: 2.02972531319, griddcFrequency: 50.0600738525, griddcVoltage: 243.019439697, gridFrequency: 50.0600738525, gridnVoltage: 305.367279053, gridPower: 494.799346924, gridVoltage: 242.946365356, inverterTemp: 95.6759544373, isoResistance: 6.53649520874, leakCurrent: 0.00441941944882, leakdcCurrent: 0.0, string1Current: 0.758069634438, string1Power: 253.94921875, string1Voltage: 359.214996338, string2Current: 0.767736792564, string2Power: 258.066558838, string2Voltage: 357.547058105, timeDate: 1517637291, usUnits: 1
        LOOP:   2018-02-03 15:55:00 AEST (1517637300) boosterTemp: 96.5189491272, bulkdcVoltage: 381.098876953, bulkmidVoltage: 199.653121948, bulkVoltage: 382.354553223, dateTime: 1517637300, dayEnergy: 8637, energy: 1, gridavgVoltage: 243.432281494, gridCurrent: 2.02972531319, griddcFrequency: 50.0841407776, griddcVoltage: 242.313354492, gridFrequency: 50.0831375122, gridnVoltage: 305.144683838, gridPower: 496.422271729, gridVoltage: 242.982879639, inverterTemp: 95.6770530701, isoResistance: 6.53649520874, leakCurrent: 0.00441941944882, leakdcCurrent: 0.0, string1Current: 0.757264018059, string1Power: 253.298355103, string1Voltage: 358.233856201, string2Current: 0.772570431232, string2Power: 257.640594482, string2Voltage: 359.038391113, timeDate: 1517637301, usUnits: 1
        LOOP:   2018-02-03 15:55:10 AEST (1517637310) boosterTemp: 96.5321601868, bulkdcVoltage: 381.098876953, bulkmidVoltage: 199.025268555, bulkVoltage: 382.354553223, dateTime: 1517637310, dayEnergy: 8639, energy: 2, gridavgVoltage: 243.395889282, gridCurrent: 2.0580675602, griddcFrequency: 50.1042175293, griddcVoltage: 242.240203857, gridFrequency: 50.1042175293, gridnVoltage: 306.149841309, gridPower: 497.233734131, gridVoltage: 242.970703125, inverterTemp: 95.6792640686, isoResistance: 6.53649520874, leakCurrent: 0.00441941944882, leakdcCurrent: 0.0, string1Current: 0.757264018059, string1Power: 255.268432617, string1Voltage: 359.882171631, string2Current: 0.775792837143, string2Power: 258.421295166, string2Voltage: 357.488189697, timeDate: 1517637311, usUnits: 1
        LOOP:   2018-02-03 15:55:20 AEST (1517637320) boosterTemp: 96.5244491577, bulkdcVoltage: 381.726715088, bulkmidVoltage: 199.653121948, bulkVoltage: 386.749420166, dateTime: 1517637320, dayEnergy: 8640, energy: 1, gridavgVoltage: 243.347320557, gridCurrent: 2.0580675602, griddcFrequency: 50.1132545471, griddcVoltage: 242.873519897, gridFrequency: 50.1122512817, gridnVoltage: 305.666992188, gridPower: 499.668151855, gridVoltage: 243.116577148, inverterTemp: 95.6946929932, isoResistance: 6.53649520874, leakCurrent: 0.00441941944882, leakdcCurrent: 0.0, string1Current: 0.758069634438, string1Power: 255.205551147, string1Voltage: 360.176513672, string2Current: 0.774987220764, string2Power: 258.839141846, string2Voltage: 357.174224854, timeDate: 1517637321, usUnits: 1
        REC:    2018-02-03 15:55:00 AEST (1517637300) boosterTemp: 96.5136605835, bulkdcVoltage: 381.475579834, bulkmidVoltage: 199.52755127, bulkVoltage: 382.982391357, dateTime: 1517637300.0, dayEnergy: 8634.4, energy: 5.0, gridavgVoltage: 243.495370483, gridCurrent: 2.02964129448, griddcFrequency: 50.0747131348, griddcVoltage: 242.812478638, gridFrequency: 50.0753143311, gridnVoltage: 305.237585449, gridPower: 493.501000977, gridVoltage: 242.841641235, interval: 5, inverterTemp: 95.6761741638, isoResistance: 6.53649520874, leakCurrent: 0.00441941944882, leakdcCurrent: 0.0, string1Current: 0.755330586433, string1Power: 252.531326294, string1Voltage: 358.532122803, string2Current: 0.767897939682, string2Power: 256.399765015, string2Voltage: 359.328808594, timeDate: 1517637281.0, usUnits: 1
        LOOP:   2018-02-03 15:55:30 AEST (1517637330) boosterTemp: 96.5409767151, bulkdcVoltage: 382.354553223, bulkmidVoltage: 199.025268555, bulkVoltage: 382.982391357, dateTime: 1517637330, dayEnergy: 8641, energy: 1, gridavgVoltage: 243.310913086, gridCurrent: 2.0580675602, griddcFrequency: 50.1152648926, griddcVoltage: 242.471786499, gridFrequency: 50.1152648926, gridnVoltage: 305.666992188, gridPower: 500.479614258, gridVoltage: 242.81262207, inverterTemp: 95.7321769714, isoResistance: 6.53649520874, leakCurrent: 0.00441941944882, leakdcCurrent: 0.00441941944882, string1Current: 0.758875250816, string1Power: 255.55909729, string1Voltage: 358.920654297, string2Current: 0.778209626675, string2Power: 260.399230957, string2Voltage: 358.547821045, timeDate: 1517637331, usUnits: 1

    The above indicates that the inverter is being interrogated, valid data being received and weeWX is constructing archive records from the accumulated loop data.

1.  If all appears correct when run directly you can stop weeWX by entering *Ctl-Z* in the terminal and you can now start weeWX as a daemon:
    
        $ sudo /etc/init.d/weewx start
    
    or

        $ sudo service weewx start

1.  The weeWX log should be monitored to verify archive records are being saved.

## Support ##

General support issues may be raised in the Google Groups [weewx-user forum](https://groups.google.com/group/weewx-user) . Specific bugs in the *Aurora driver* extension code should be the subject of a new issue raised via the [*Aurora driver* extension issues page](https://github.com/gjr80/weewx-aurora/issues).

## Licensing ##

The *Aurora driver* extension is licensed under the [GNU Public License v3](https://github.com/gjr80/weewx-aurora/blob/master/LICENSE).
