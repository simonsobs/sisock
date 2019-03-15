import time
import os
from os import environ
from datetime import datetime

import mysql.connector

import so3g
from spt3g import core
from spt3g.core import G3FrameType

def _extract_feeds_from_status_frame(frame):
    """Get the prov_id and description from each provider in an HKStatus frame.

    Returns
    -------
    list
        list of tuples containing (prov_id, description) for each provider.
        None if not an HKStatus frame

    """
    feeds = []
    for provider in frame['providers']:
        description = str(provider['description']).strip('"')
        prov_id = int(str(provider['prov_id']))
        feeds.append((prov_id, description))

    return feeds

# G3 Modules
def add_files_to_feeds_table(frame, cur, r, f):
    """Parse the frames, gathering feed information.

    Parameters
    ----------
    frame : G3Frame
        The G3Frame which the G3Pipeline will pass to us.
    cur : mysql.connector.cursor.MySQLCursor object
        SQL cursor provided by mysql.connector connection.
    r : string
        The pathname of the file, gathered from an os.walk call.
    f : string
        The basename of the g3 file to parse.
    """
    feeds = []
    # Build feeds list for g3 file
    if frame.type == G3FrameType.Housekeeping:
        if frame['hkagg_type'] == 1:
            feeds = _extract_feeds_from_status_frame(frame)
    else:
        return

    # Each file can (and probably will) contain more than one feed
    for (prov_id, description) in feeds:
        # Get ID from the file/feed if it exists.
        cur.execute("SELECT id FROM feeds WHERE filename=%s AND prov_id=%s", (f, prov_id))
        _r = cur.fetchall()

        if not _r:
            result = None
        else:
            result = _r[0]

        if result is not None:
            feed_id = result[0]
        else:
            feed_id = None

        # If the ID doesn't exist, the file/feed isn't in the table yet.
        if feed_id is None:
            # Calculate new unique id for file/feed
            print("calculating ID %s %s"%(f, description))
            cur.execute("SELECT MAX(id) from feeds")
            max_id = cur.fetchall()[0][0]
            if max_id is None:
                _id = 1 # Index on 1 so we can check with not feed_id later
                        # and not get false result
            else:
                _id = max_id+1

            # Add file/feed to table.
            cur.execute("INSERT IGNORE \
                         INTO feeds \
                             (id, filename, path, prov_id, description) \
                         VALUES \
                             (%s, %s, %s, %s, %s)", (_id, f, r, prov_id, description))

def add_fields_and_times_to_db(frame, cur, r, f):
    """Parse the frames, gathering field information such as start/end times.

    Parameters
    ----------
    frame : G3Frame
        The G3Frame which the G3Pipeline will pass to us.
    cur : mysql.connector.cursor.MySQLCursor object
        SQL cursor provided by mysql.connector connection.
    r : string
        The pathname of the file, gathered from an os.walk call.
    f : string
        The basename of the g3 file to parse.
    """
    if frame.type == G3FrameType.Housekeeping:
        if frame['hkagg_type'] == 2:
            prov_id = frame['prov_id']
        else:
            return
    else:
        return

    # Get ID from the filed/prov_id if it exists.
    cur.execute("SELECT id, scanned FROM feeds WHERE filename=%s AND prov_id=%s", (f, prov_id))
    _r = cur.fetchall()
    result = _r[0]
    if result is not None:
        feed_id = result[0]
        scanned = bool(result[1]) # True if already scanned by this script.
    else:
        raise Exception("%s is not in feed database, something went wrong."%(f))

    if not scanned:
        # Get start and end times for each field within this frame.
        print("Adding %s/%s to G3Reader"%(r, f))
        start_times = {}
        end_times = {}
        for block in frame['blocks']:
            for field in dict(block.data).keys():
                times = list(block.t)
                if field not in start_times:
                    start_times[field] = datetime.fromtimestamp(times[0])
                    end_times[field] = datetime.fromtimestamp(times[len(times)-1])
                else:
                    if datetime.fromtimestamp(times[0]) < start_times[field]:
                        start_times[field] = datetime.fromtimestamp(times[0])
                    if datetime.fromtimestamp(times[len(times)-1]) > end_times[field]:
                        end_times[field] = datetime.fromtimestamp(times[len(times)-1])

        # Check for feed/field combo in DB, also compare start/end times before updating.
        for field in dict(block.data).keys():
            # Format for DB entry.
            _start = start_times[field].strftime("%Y-%m-%d %H-%M-%S.%f")
            _end = end_times[field].strftime("%Y-%m-%d %H-%M-%S.%f")

            # Query for existing start/end times.
            cur.execute("SELECT feed_id, field, start, end \
                         FROM fields \
                         WHERE feed_id=%s \
                         AND field=%s", (feed_id, field))
            _r = cur.fetchall()
            if not _r:
                result = None
            else:
                result = _r[0]

            if result is None:
                # INSERT
                print("Inserting start={} and end={} to feed_id {} for field {}".format(_start,
                                                                                        _end,
                                                                                        feed_id,
                                                                                        field))
                cur.execute("INSERT \
                             INTO fields \
                                 (feed_id, field, start, end) \
                             VALUES (%s, %s, %s, %s)", (feed_id, field, _start, _end))
            else:
                # UPDATE (only if start < db_start or end > db_end)
                _id, _field, db_start, db_end = result
                print("Updating start={} and end={} for feed_id {}, field {}".format(_start,
                                                                                     _end,
                                                                                     feed_id,
                                                                                     field))
                if start_times[field] < db_start:
                    cur.execute("UPDATE fields \
                                 SET start=%s \
                                 WHERE feed_id=%s \
                                 AND field=%s", (_start, feed_id, field))
                if end_times[field] > db_end:
                    cur.execute("UPDATE fields \
                                 SET end=%s \
                                 WHERE feed_id=%s \
                                 AND field=%s", (_end, feed_id, field))
    else:
        # debug print
        #print("%s/%s containing feed %s has already been scanned, skipping."%(r, f, feed))
        pass

# Non-G3 Modules
def init_tables(config):
    """Initialize the tables if they don't exist.

    Parameters
    ----------
    config : dict
        SQL config for the DB connection

    """
    # Establish DB connection.
    cnx = mysql.connector.connect(host=config['host'],
                                  user=config['user'],
                                  passwd=config['passwd'],
                                  db=config['db'])
    cur = cnx.cursor()
    print("SQL server connection established")

    # Check what tables exist, create the tables we need if they don't exist.
    table_query = cur.execute("SHOW tables;")

    tables = []
    for row in cur.fetchall():
        tables.append(row[0])

    print(tables)

    if "feeds" not in tables and "fields" not in tables:
        print("Initializing feeds and fields tables.")
        cur.execute("CREATE TABLE feeds \
                         (id INT NOT NULL PRIMARY KEY, \
                          filename varchar(255), \
                          path varchar(255), \
                          prov_id INT, \
                          description varchar(255), \
                          scanned BOOL NOT NULL DEFAULT 0)")
        cur.execute("CREATE UNIQUE INDEX feed_index ON feeds (`filename`, `prov_id`)")
        cur.execute("CREATE TABLE fields \
                         (feed_id INT NOT NULL, \
                          field varchar(255), \
                          start DATETIME(6), \
                          end DATETIME(6))")
        cur.execute("CREATE UNIQUE INDEX index_field ON fields (`feed_id`, `field`)")

    cnx.commit()
    cur.close()
    cnx.close()

def scan_directory(directory, config):
    """Scan a given directory for .g3 files, adding them to the Database.

    Parameters
    ----------
    directory : str
        the top level directory to scan
    config : dict
        SQL config for the DB connection

    """
    # Establish DB connection.
    cnx = mysql.connector.connect(host=config['host'],
                                  user=config['user'],
                                  passwd=config['passwd'],
                                  db=config['db'])
    cur = cnx.cursor()
    print("SQL server connection established")


    # Gather all files we want to scan.
    a = os.walk(directory)

    # Iterate over file list and run pipeline on each file.
    for root, directory, _file in a:
        for g3 in _file:
            if g3[-2:] == "g3":
                try:
                    p = core.G3Pipeline()
                    #print("Adding %s/%s to G3Reader"%(root, g3))
                    p.Add(core.G3Reader, filename=os.path.join(root, g3))
                    p.Add(add_files_to_feeds_table, cur=cur, r=root, f=g3)
                    p.Add(add_fields_and_times_to_db, cur=cur, r=root, f=g3)
                    p.Run()
                    # Mark feed_id as 'scanned' in feeds table.
                    cur.execute("UPDATE feeds \
                                 SET scanned=1 \
                                 WHERE filename=%s \
                                 AND path=%s", (g3, root))
                    cnx.commit()
                except RuntimeError:
                    print("Could not read {}, ".format(os.path.join(root, g3)) +
                          "file likely still being written.")

    cur.close()
    cnx.close()

if __name__ == "__main__":
    # Check variables setup when creating the Docker container.
    required_env = ['SQL_HOST', 'SQL_USER', 'SQL_PASSWD', 'SQL_DB']

    for var in required_env:
        try:
            environ[var]
        except KeyError:
            print("Required environment variable {} is missing. \
                  Check your environment setup and try again.".format(var))

    # SQL Config
    # User/password just for development purposes, obviously change in production.
    SQL_CONFIG = {'host': environ['SQL_HOST'],
                  'user': environ['SQL_USER'],
                  'passwd': environ['SQL_PASSWD'],
                  'db': environ['SQL_DB']}

    init_tables(SQL_CONFIG)

    while True:
        scan_directory(environ['DATA_DIRECTORY'], SQL_CONFIG)
        print('sleeping for:', environ['SCAN_INTERVAL'])
        time.sleep(int(environ['SCAN_INTERVAL']))
