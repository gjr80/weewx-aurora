# aurora_schema.py
#
# A weeWX schema for use the weewx-aurora driver and an Aurora inverter.
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
# Version: 0.2.0                                      Date: 31 January 2017
#
# Revision History
#  31 January 2017      v0.2.0      - minor reformatting only
#  11 December 2016     v0.1.0      - initial release
#
"""The weewx-aurora schema"""
# ============================================================================
# This file contains the default schema of the weewx-aurora archive table. It
# is only used for initialization, or in conjunction with the aurora_config
# utility --create-database and --reconfigure options. Otherwise, once the
# tables are created the schema is obtained dynamically from the database.
# Although a type may be listed here, it may not necessarily be supported by
# the inverter in use.
#
# The schema may be trimmed of any unused types if required, but it will not
# result in much space being saved as most of the space is taken up by the
# primary key indexes (type "dateTime").
# ============================================================================
#
AURORA_SCHEMA_VERSION = '0.2.0'

# Define schema for archive table
aurora_schema = [
    ('dateTime',       'INTEGER NOT NULL UNIQUE PRIMARY KEY'),
    ('usUnits',        'INTEGER NOT NULL'),
    ('interval',       'INTEGER NOT NULL'),
    ('string1Voltage', 'REAL'),    ('string1Current', 'REAL'),
    ('string1Power',   'REAL'),
    ('string2Voltage', 'REAL'),
    ('string2Current', 'REAL'),
    ('string2Power',   'REAL'),    ('gridVoltage',    'REAL'),
    ('gridCurrent',    'REAL'),
    ('gridPower',      'REAL'),
    ('gridFrequency',  'REAL'),
    ('efficiency',     'REAL'),
    ('inverterTemp',   'REAL'),
    ('boosterTemp',    'REAL'),
    ('bulkVoltage',    'REAL'),
    ('isoResistance',  'REAL'),
    ('in1Power',       'REAL'),
    ('in2Power',       'REAL'),
    ('bulkmidVoltage', 'REAL'),
    ('bulkdcVoltage',  'REAL'),
    ('leakdcCurrent',  'REAL'),
    ('leakCurrent',    'REAL'),
    ('griddcVoltage',  'REAL'),
    ('gridavgVoltage', 'REAL'),
    ('gridnVoltage',   'REAL'),
    ('griddcFrequency','REAL'),
    ('energy',         'REAL')
    ]
