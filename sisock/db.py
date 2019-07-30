"""sisock database operations."""
import os
import mysql.connector
from mysql.connector import errorcode

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
                                  port=config.get('port', 3306),
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
                                  port=config.get('port', 3306),
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
                          file_id INT, \
                          prov_id INT, \
                          description varchar(255))")
        cur.execute("CREATE UNIQUE INDEX feed_index ON feeds (`file_id`, `prov_id`)")
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
