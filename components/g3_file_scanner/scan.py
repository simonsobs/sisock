import time
import hashlib
import os
from os import environ
from datetime import datetime

import mysql.connector
from mysql.connector import errorcode

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
def add_files_to_feeds_table(frame, cur, cnx, r, f):
    """Add filename and path to file_info table and parse the frames within
    each file, gathering feed information.

    Parameters
    ----------
    frame : G3Frame
        The G3Frame which the G3Pipeline will pass to us.
    cur : mysql.connector.cursor.MySQLCursor object
        SQL cursor provided by mysql.connector connection.
    cnx : mysql.connector.connection.MySQLConnection object
        SQL connection, allowing us to commit
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
        cur.execute("SELECT E.id \
                     FROM feeds E, file_info I \
                     WHERE I.filename=%s AND E.prov_id=%s", (f, prov_id))
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
            # Add file+path to file_info table
            cur.execute("INSERT IGNORE \
                         INTO file_info \
                             (filename, path) \
                         VALUES \
                             (%s, %s)", (f, r))
            cnx.commit()

            cur.execute("SELECT id \
                        FROM file_info \
                        WHERE filename=%s AND path=%s", (f, r))
            file_id = cur.fetchone()[0]

            # Add file_id, feed description to feeds table.
            cur.execute("INSERT IGNORE \
                         INTO feeds \
                             (file_id, prov_id, description) \
                         VALUES \
                             (%s, %s, %s)", (file_id, prov_id, description))

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

    # Get feed ID from the field/prov_id if it exists.
    cur.execute("SELECT E.id, I.scanned \
                 FROM feeds E, file_info I \
                 WHERE I.filename=%s AND E.prov_id=%s", (f, prov_id))
    _r = cur.fetchall()

    # _r will be [] if empty.
    if not _r:
        result = None
    else:
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
                _start = start_times[field].strftime("%Y-%m-%d %H:%M:%S.%f")
                _end = end_times[field].strftime("%Y-%m-%d %H:%M:%S.%f")

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
def _create_database(cursor, db_name):
    """Create database in SQL database conncted to cursor.

    Parameters
    ----------
    cursor : mysql.connector.cursor()
        Cursor for MySQL connection
    db_name : str
        Name for the DB

    """
    try:
        cursor.execute(
            "CREATE DATABASE {} DEFAULT CHARACTER SET 'utf8'".format(db_name))
    except mysql.connector.Error as err:
        print("Failed creating database: {}".format(err))
        exit(1)

def init_tables(config, version):
    """Initialize the tables if they don't exist.

    Parameters
    ----------
    config : dict
        SQL config for the DB connection
    version : int
        Internal db structure version number

    """
    # Establish DB connection.
    cnx = mysql.connector.connect(host=config['host'],
                                  user=config['user'],
                                  passwd=config['passwd'])
    cur = cnx.cursor()
    print("SQL server connection established")

    # Create DB if it doesn't already exist.
    # https://dev.mysql.com/doc/connector-python/en/connector-python-example-ddl.html
    try:
        cur.execute("USE {}".format(config['db']))
    except mysql.connector.Error as err:
        print("Database {} does not exists.".format(config['db']))
        if err.errno == errorcode.ER_BAD_DB_ERROR:
            _create_database(cur, config['db'])
            print("Database {} created successfully.".format(config['db']))
            cnx.database = config['db']
        else:
            print(err)
            exit(1)

    # Check what tables exist, create the tables we need if they don't exist.
    cur.execute("SHOW tables;")

    tables = []
    for row in cur.fetchall():
        tables.append(row[0])

    print(tables)

    db_version = version

    if "feeds" not in tables and "fields" not in tables:
        print("Initializing feeds and fields tables.")
        cur.execute("CREATE TABLE feeds \
                         (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, \
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
    else:
        if "db_structure" not in tables:
            # 1st implementation of DB stucture. If "feeds" and "fields" are in
            # the DB, but "db_structure" isn't, then that means we're using the
            # original structure, which we call version 0. Every version check
            # after this one will just rely on checking the version already set
            # in the database.
            db_version = 0

    if "description" not in tables:
        cur.execute("CREATE TABLE description \
                         (description varchar(255) NOT NULL PRIMARY KEY)")

    if "db_structure" not in tables:
        cur.execute("CREATE TABLE db_structure \
                         (version INT NOT NULL)")
        cur.execute("INSERT IGNORE \
                     INTO db_structure \
                         (version) \
                     VALUES \
                         (%s)", (db_version,))
        print('Set the db_structure version to {}'.format(db_version))

    if "file_info" not in tables:
        cur.execute("CREATE TABLE file_info \
                         (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, \
                          filename varchar(255), \
                          path varchar(255), \
                          scanned BOOL NOT NULL DEFAULT 0, \
                          available BOOL NOT NULL DEFAULT 0, \
                          last_modified DATETIME, \
                          last_seen DATETIME, \
                          size BIGINT, \
                          md5sum varchar(32))")
        cur.execute("CREATE UNIQUE INDEX file_index ON file_info (`filename`, `path`)")

    cnx.commit()
    cur.close()
    cnx.close()

def _update_v0_to_v1(connection, cursor):
    """Update DB structure v0 to structure v1.

    Changes here focus on the creation of the file_info table, which describes
    the file, where it is located, its size, and more.

    Operations:
        * Copy filename, path, scanned columns from feeds table to file_info
        * Add file_id column to feeds table
        * Populate the file_id column based on new id's generated in file_info
        * Remove old INDEX feed_index
        * Remove old filename, path, scanned columns from feeds table
        * Create new INDEX feed_index on file_id, prov_id
        * (Let scanning operation populate remainder of file_info table)

    Parameters
    ----------
    connection : mysql.connector.connect Connection
        Connection to the sql database, so we can commit
    cursor : mysql.connector.cursor Object
        Cursor for the SQL database connection so we can query the DB

    """
    # Copy filename, path, scanned to file_info
    cursor.execute("INSERT IGNORE INTO file_info \
                        (filename, path, scanned) \
                    SELECT DISTINCT \
                        filename, \
                        path, \
                        scanned \
                    FROM feeds")
    connection.commit()

    # Add file_id colume to feeds table
    cursor.execute("ALTER TABLE feeds ADD COLUMN file_id INT AFTER id")

    # Copy the file_id into the feeds based on file_info table
    cursor.execute("SELECT id, filename, path \
                    FROM feeds")
    feeds = cursor.fetchall()

    for (_id, _filename, _path) in feeds:
        cursor.execute("SELECT id FROM file_info \
                     WHERE filename=%s \
                     AND path=%s", (_filename, _path))
        print("Determining file_id for {}".format(os.path.join(_path, _filename)))
        file_id = cursor.fetchone()[0]
        cursor.execute("UPDATE feeds \
                     SET file_id=%s \
                     WHERE filename=%s \
                     AND path=%s", (file_id, _filename, _path))
        print("file_id for {} recorded as {}".format(os.path.join(_path, _filename), file_id))

    connection.commit()

    # Drop old feed_index from feeds table
    cursor.execute("DROP INDEX `feed_index` ON feeds")
    connection.commit()

    # Remove old filename, path, scanned columns from feeds table
    cursor.execute("ALTER TABLE feeds DROP COLUMN filename")
    cursor.execute("ALTER TABLE feeds DROP COLUMN path")
    cursor.execute("ALTER TABLE feeds DROP COLUMN scanned")
    connection.commit()

    # Create new feed_index on file_id, prov_id
    cursor.execute("CREATE UNIQUE INDEX feed_index ON feeds (`file_id`, `prov_id`)")
    connection.commit()

    # Update the version number
    cursor.execute("UPDATE db_structure SET version=1")
    connection.commit()

def update_db_structure(config, version):
    """Update the DB structure of an already initialized database.

    Since we're running the system on several computers we want to make updates
    to the database structure seemless for users who depend on the database.
    This method handles updating the database structure. Clients that use the
    info in the database should be stopped during a restart of the g3-file-scanner
    for updating.

    Parameters
    ----------
    config : dict
        SQL config for the DB connection
    version : int
        Internal db structure version number

    """
    # Establish DB connection.
    cnx = mysql.connector.connect(host=config['host'],
                                  user=config['user'],
                                  passwd=config['passwd'],
                                  db=config['db'])
    cur = cnx.cursor()
    print("SQL server connection established")

    cur.execute("SELECT version FROM db_structure;")
    db_version = cur.fetchone()[0]

    while db_version != version:
        cur.execute("SELECT version FROM db_structure;")
        db_version = cur.fetchone()[0]

        if db_version < version:
            print("DB structure requires update.")
            if db_version == 0 and version == 1:
                _update_v0_to_v1(cnx, cur)
        else:
            print("DB structure is update to date.")

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
                    p.Add(add_files_to_feeds_table, cur=cur, cnx=cnx, r=root, f=g3)
                    p.Add(add_fields_and_times_to_db, cur=cur, r=root, f=g3)
                    p.Run()
                    # Mark file as 'scanned' in file_info table.
                    cur.execute("UPDATE file_info \
                                 SET scanned=1 \
                                 WHERE filename=%s \
                                 AND path=%s", (g3, root))
                    cnx.commit()
                except RuntimeError:
                    print("Could not read {}, ".format(os.path.join(root, g3)) +
                          "file likely still being written.")

    cur.close()
    cnx.close()


def build_description_table(config):
    """Build the list of field names that the sisock g3-reader data server will
    return. This is stored in the description table.

    Parameters
    ----------
    config : dict
        SQL config for the DB connection

    """
    print("Buliding description table")
    # Profiling building the field list
    t = time.time()

    # Establish DB connection.
    cnx = mysql.connector.connect(host=config['host'],
                                  user=config['user'],
                                  passwd=config['passwd'],
                                  db=config['db'])
    cur = cnx.cursor()
    print("SQL server connection established")

    # Get feed_ids and field names from database.
    print("Querying database for all fields")
    cur.execute("SELECT DISTINCT F.field, E.description \
                 FROM fields F, feeds E \
                 WHERE F.feed_id=E.id")
    fields = cur.fetchall()

    # print("Queried for fields:", fields) # debug

    for field_name, description in fields:
        # Create our timeline names based on the feed
        _field_name = (field_name).lower().replace(' ', '_')

        # Actually using for both timeline and field names, as each field
        # is timestamped independently anyway, and _field_name is not
        # guarenteed to be unique between feeds (i.e. there is a "Channel
        # 01" feed on every Lakeshore).
        _timeline_name = description + '.' + _field_name

        cur.execute("INSERT IGNORE \
                     INTO description \
                         (description) \
                     VALUES \
                         (%s)", (_timeline_name,))

    # TODO: Drop descriptions that are no longer available

    # Close DB connection
    cnx.commit()
    cur.close()
    cnx.close()

    total_time = time.time() - t
    print("Total Time:", total_time)

def _get_availability(filename, path):
    """Confirm the file is available by confirming the file is there.

    Parameters
    ----------
    filename : str
        basename of the file
    path : str
        directory path to the file

    Returns
    -------
    int
        1 if True, 0 if False. This maps into the DB structure.

    """
    full_path = os.path.join(path, filename)
    result = os.path.isfile(full_path)
    return int(result)

def _unixtime2sql(time_):
    # datetime object format
    time_dt = datetime.fromtimestamp(time_)

    # String formatting for SQL query
    sql_str = time_dt.strftime("%Y-%m-%d %H:%M:%S.%f")

    return sql_str

def _sql2unix(time_, fraction=False):
    """Convert SQL formatted time string to unix timestamp.

    Parameters
    ----------
    time_ : str
        SQL formatted timestamp, i.e. %Y-%m-%d %H:%M:%S
    fraction : bool
        Support fractional seconds on input

    Returns
    -------
    int
        unix timestamp

    """
    # datetime object format
    if fraction:
        time_dt = datetime.strptime(time_, "%Y-%m-%d %H:%M:%S.%f")
    else:
        time_dt = datetime.strptime(time_, "%Y-%m-%d %H:%M:%S")

    unix = int(time_dt.strftime("%s"))

    return unix

def _get_last_modified_date(filename, path):

    full_path = os.path.join(path, filename)
    unix = os.stat(full_path).st_ctime
    sql_str = _unixtime2sql(unix)

    return sql_str

def _get_size(filename, path):
    """Get the filesize in bytes.

    Parameters
    ----------
    filename : str
        basename of the file
    path : str
        directory path to the file

    Returns
    -------
    int
        Size of the file in bytes.

    """
    full_path = os.path.join(path, filename)
    result = os.path.getsize(full_path)
    return result

def _md5sum(filename, blocksize=65536):
    # https://stackoverflow.com/questions/3431825/generating-an-md5-checksum-of-a-file
    hash_ = hashlib.md5()
    with open(filename, "rb") as f:
        for block in iter(lambda: f.read(blocksize), b""):
            hash_.update(block)
    return hash_.hexdigest()

def _get_md5sum(filename, path):
    full_path = os.path.join(path, filename)
    return _md5sum(full_path)

def gather_new_file_info(config):
    """Gather information about new files that have yet to be scanned.

    Parameters
    ----------
    config : dict
        SQL config for the DB connection

    """
    print("Gathering file information")
    # Profiling file scanning
    t = time.time()

    # Establish DB connection.
    cnx = mysql.connector.connect(host=config['host'],
                                  user=config['user'],
                                  passwd=config['passwd'],
                                  db=config['db'])
    cur = cnx.cursor()
    print("SQL server connection established")

    # Get filenames and paths if md5sum hasn't been computed
    print("Querying database for all files")
    cur.execute("SELECT DISTINCT filename, path \
                 FROM file_info \
                 WHERE md5sum IS NULL")
    files = cur.fetchall()

    for filename, path in files:
        print("Updating info for:", filename)
        available = _get_availability(filename, path)
        if available:
            seen = _unixtime2sql(time.time())
            print("Last seen:", seen)
        modified_date = _get_last_modified_date(filename, path)
        size = _get_size(filename, path)
        md5 = _get_md5sum(filename, path)

        cur.execute("UPDATE file_info \
                     SET \
                         available=%s, \
                         last_modified=%s, \
                         last_seen=%s, \
                         size=%s, \
                         md5sum=%s \
                     WHERE \
                         filename=%s \
                         AND \
                         path=%s", (available, modified_date, seen, size, md5, filename, path))

    # Close DB connection
    cnx.commit()
    cur.close()
    cnx.close()

    total_time = time.time() - t
    print("Total Time to gather file info:", total_time)

def check_old_file_info(config):
    """Check on old files, updating information in file_info table

    Parameters
    ----------
    config : dict
        SQL config for the DB connection

    """
    print("Checking file info")
    # Profiling file scanning
    t = time.time()

    # Establish DB connection.
    cnx = mysql.connector.connect(host=config['host'],
                                  user=config['user'],
                                  passwd=config['passwd'],
                                  db=config['db'])
    cur = cnx.cursor()
    print("SQL server connection established")

    # Get filenames and paths if md5sum hasn't been computed
    print("Querying database for all files")
    cur.execute("SELECT filename, path, last_modified, last_seen, size, md5sum \
                 FROM file_info \
                 WHERE md5sum IS NOT NULL")
    files = cur.fetchall()

    for filename, path, last_modified, seen, known_size, known_md5 in files:
        print("Updating info for:", filename)
        available = _get_availability(filename, path)
        if available:
            seen = _unixtime2sql(time.time())
            print("Last seen:", seen)

            modified_date = _get_last_modified_date(filename, path)
            if _sql2unix(modified_date, fraction=True) > int(last_modified.strftime("%s")):
                print("{} has been modified, updating size, md5sum, and modified date".format(os.path.join(path, filename)))
                md5 = _get_md5sum(filename, path)
                if known_md5 != md5:
                    print("md5sum has changed for {}".format(os.path.join(path, filename)))
                    # TODO: Need to now rescan the file, set scanned to 0? (is
                    # that sufficient? might need to first remove fields for
                    # the file)
                size = _get_size(filename, path)
            else:
                size = known_size
                md5 = known_md5
        else:
            modified_date = last_modified
            size = known_size
            md5 = known_md5

        cur.execute("UPDATE file_info \
                     SET \
                         available=%s, \
                         last_modified=%s, \
                         last_seen=%s, \
                         size=%s, \
                         md5sum=%s \
                     WHERE \
                         filename=%s \
                         AND \
                         path=%s", (available, modified_date, seen, size, md5, filename, path))

    # Close DB connection
    cnx.commit()
    cur.close()
    cnx.close()

    total_time = time.time() - t
    print("Total Time to gather file info:", total_time)


if __name__ == "__main__":
    # Check variables setup when creating the Docker container.
    REQUIRED_ENV = ['SQL_HOST', 'SQL_USER', 'SQL_PASSWD', 'SQL_DB']

    for var in REQUIRED_ENV:
        try:
            environ[var]
        except KeyError:
            print("Required environment variable {} is missing. \
                  Check your environment setup and try again.".format(var))

    # SQL Config
    SQL_CONFIG = {'host': environ['SQL_HOST'],
                  'user': environ['SQL_USER'],
                  'passwd': environ['SQL_PASSWD'],
                  'db': environ['SQL_DB']}

    DB_VERSION = 1

    init_tables(SQL_CONFIG, DB_VERSION)
    update_db_structure(SQL_CONFIG, DB_VERSION)

    while True:
        scan_directory(environ['DATA_DIRECTORY'], SQL_CONFIG)
        build_description_table(SQL_CONFIG)
        check_old_file_info(SQL_CONFIG)
        gather_new_file_info(SQL_CONFIG)
        print('sleeping for:', environ['SCAN_INTERVAL'])
        time.sleep(int(environ['SCAN_INTERVAL']))
