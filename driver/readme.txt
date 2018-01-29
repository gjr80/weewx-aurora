This driver support the Power One Aurora inverters. The driver interacts with
the inverter over a serial connection using the Power One Aurora Inverter
Series Communications Protocol to query the inverter state. The driver maps
various inverter readings to weeWX loop packet format and emits loop packets at
a user configurable rate.

Pre-Requisites

The Aurora driver requires:

-   weeWX v3.7.0 or greater, and
-   the python-serial package

Installation Instructions

Installation using the wee_extension utility

Note:   Symbolic names are used below to refer to some file location on the
weeWX system. These symbolic names allow a common name to be used to refer to
a directory that may be different from system to system. The following symbolic
names are used below:

-   $DOWNLOAD_ROOT. The path to the directory containing the downloaded
    Realtime gauge-data extension.

1.  Download the latest Aurora driver extension from the Aurora driver releases
page (https://github.com/gjr80/weewx-aurora/releases) into a directory
accessible from the weeWX machine.

    $ wget -P $DOWNLOAD_ROOT https://github.com/gjr80/weewx-aurora/releases/download/v0.5.0/aurora-0.5.0.tar.gz

	where $DOWNLOAD_ROOT is the path to the directory where the Aurora driver
    extension is to be downloaded.

2.  Stop weeWX if it is running:

    $ sudo /etc/init.d/weewx stop

	or

    $ sudo service weewx stop

3.  Install the Aurora driver extension downloaded at step 1 using the
*wee_extension* utility:

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

Manual installation

To be written....