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

        $ wget -P $DOWNLOAD_ROOT https://github.com/gjr80/weewx-aurora/releases/download/v0.5.0/aurora-0.5.0.tar.gz

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

4.  Select and configure the driver:

        $ sudo wee_config --reconfigure

5.  Start weeWX:

        $ sudo /etc/init.d/weewx start

	or

        $ sudo service weewx start

This will result in .....

### Manual installation ###

To be written....

## Support ##

General support issues may be raised in the Google Groups [weewx-user forum](https://groups.google.com/group/weewx-user) . Specific bugs in the *Aurora driver* extension code should be the subject of a new issue raised via the [*Aurora driver* extension issues page](https://github.com/gjr80/weewx-aurora/issues).


## Licensing ##

The *Aurora driver* extension is licensed under the [GNU Public License v3](https://github.com/gjr80/weewx-aurora/blob/master/LICENSE).
