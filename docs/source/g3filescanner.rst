g3 File Scanner
===============

Reading back housekeeping data from g3 files written to disk is a key feature
required of the housekeeping monitor. This task is performed in two parts. The
first is to scan the files. Each g3 file is read and metadata about what is
stored in the files is recorded into a MySQL database. The component that
performs this first task is called the `g3-file-scanner`. The second, is the
opening and caching of the data in specific g3 files which are requested. This
is the data server, `g3-reader`. This page describes the inner workings of
the `g3-file-scanner`.

.. contents:: Contents
    :local:

Overview
--------

The `g3-file-scanner` (referred to here as the "file scanner") will scan a
given directory for files with a `.g3` extension, open them, and record
metadata about them required for the `g3-reader` data server in a MySQL
database. The scan occurs on a regular interval, set by the user as an
environment variable.

.. note::

    The first scan of a large dataset will take some time, depending on how
    much data you have.

SQL Database Design
-------------------

The SQL database is split into two tables, the "feeds" table and the "fields"
table. "feeds" stores the filename and path to the file along with the
`prov_id` and `description` from within the g3 file. The `description` will be
used to assemble a unique sisock field name. Additionally, the "feeds" table
keeps track of whether a scan has completed on the given file (with the
`scanned` column), and assigns each file a unique `id`.

A description and example of the "feeds" table is shown here:

.. code-block:: mysql

    MariaDB [files]> describe feeds;
    +-------------+--------------+------+-----+---------+-------+
    | Field       | Type         | Null | Key | Default | Extra |
    +-------------+--------------+------+-----+---------+-------+
    | id          | int(11)      | NO   | PRI | NULL    |       |
    | filename     | varchar(255) | YES  | MUL | NULL    |       |
    | path        | varchar(255) | YES  |     | NULL    |       |
    | prov_id     | int(11)      | YES  |     | NULL    |       |
    | description | varchar(255) | YES  |     | NULL    |       |
    | scanned     | tinyint(1)   | NO   |     | 0       |       |
    +-------------+--------------+------+-----+---------+-------+
    6 rows in set (0.010 sec)
    
    MariaDB [files]> select * from feeds limit 3;
    +----+------------------------+-------------+---------+---------------------+---------+
    | id | filename                | path        | prov_id | description         | scanned |
    +----+------------------------+-------------+---------+---------------------+---------+
    |  1 | 2019-03-18-16-52-46.g3 | /data/15529 |       0 | observatory.LSA22ZC |       1 |
    |  2 | 2019-03-18-16-52-46.g3 | /data/15529 |       1 | observatory.LSA23JD |       1 |
    |  3 | 2019-03-18-16-52-46.g3 | /data/15529 |       3 | observatory.LSA22YG |       1 |
    +----+------------------------+-------------+---------+---------------------+---------+
    3 rows in set (0.001 sec)

The "fields" table has a row for each ocs field within a file (i.e. "Channel
1", "Channel 2", channels for a given Lakeshore device), the start and end
times for the field, and the correspoding 'id' in the feeds id, stored here as
"feed_id".

A description and example of the "fields" table is shown here:

.. code-block:: mysql

    MariaDB [files]> describe fields;
    +---------+--------------+------+-----+---------+-------+
    | Field   | Type         | Null | Key | Default | Extra |
    +---------+--------------+------+-----+---------+-------+
    | feed_id | int(11)      | NO   | MUL | NULL    |       |
    | field   | varchar(255) | YES  |     | NULL    |       |
    | start   | datetime(6)  | YES  |     | NULL    |       |
    | end     | datetime(6)  | YES  |     | NULL    |       |
    +---------+--------------+------+-----+---------+-------+
    4 rows in set (0.001 sec)
    
    MariaDB [files]> select * from fields limit 3;
    +---------+-----------+----------------------------+----------------------------+
    | feed_id | field     | start                      | end                        |
    +---------+-----------+----------------------------+----------------------------+
    |       1 | Channel 1 | 2019-03-18 16:51:55.762230 | 2019-03-18 17:01:56.772258 |
    |       1 | Channel 2 | 2019-03-18 16:51:55.762230 | 2019-03-18 17:01:56.772258 |
    |       1 | Channel 3 | 2019-03-18 16:51:55.762230 | 2019-03-18 17:01:56.772258 |
    +---------+-----------+----------------------------+----------------------------+
    3 rows in set (0.001 sec)

The "description" table is a simple, single column, table containing the
combined ocs field and ocs descriptions distinctly across all .g3 files. This
is used as the field list that the g3-reader will return.

A description and example of the "description" table is shown here:

.. code-block:: mysql

    MariaDB [files]> describe description;
    +-------------+--------------+------+-----+---------+-------+
    | Field       | Type         | Null | Key | Default | Extra |
    +-------------+--------------+------+-----+---------+-------+
    | description | varchar(255) | NO   | PRI | NULL    |       |
    +-------------+--------------+------+-----+---------+-------+
    1 row in set (0.001 sec)
    
    MariaDB [files]> select * from description limit 3;
    +----------------------------------+
    | description                      |
    +----------------------------------+
    | observatory.LSA22YE.channel_01_r |
    | observatory.LSA22YE.channel_01_t |
    | observatory.LSA22YE.channel_02_r |
    +----------------------------------+
    3 rows in set (0.000 sec)
