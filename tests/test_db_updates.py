# Test database scheme updates
# For these tests to work you need to setup a development sql environment that
# will allow you to test the scheme updates on a clean DB.

# This can be done using Docker:
#  database:
#    image: mariadb:10.3
#    ports:
#      - "127.0.0.1:3306:3306"
#    environment:
#      # @see https://phabricator.wikimedia.org/source/mediawiki/browse/master/includes/DefaultSettings.php
#      MYSQL_DATABASE: files
#      MYSQL_USER: development
#      MYSQL_PASSWORD: development
#      MYSQL_RANDOM_ROOT_PASSWORD: 'yes'

import time
import subprocess
import mysql.connector
import pytest

from components.g3_file_scanner.scan import _unixtime2sql
from mysql.connector.errors import InterfaceError

# User pytest-docker-compose plugin to startup SQL container.
pytest_plugins = ["docker_compose"]

HOST='127.0.0.1'
PORT=3307
USER='development'
PASSWD='development'
DB='files'

SQL_CONFIG = {'host': HOST,
              'port': PORT,
              'user': USER,
              'passwd': PASSWD,
              'db': DB}


def _connect_to_sql(config):
    """Connect to an SQL DB using mysql-connector

    Parameters
    ----------
    config : dict
        Configuration dictionary for connecting. Must contain host, user,
        passwd, db keys.

    Returns
    -------
    mysql.connector Connection and Cursor Objects
        The cnx and cur objects from the DB connection.

    """
    cnx = mysql.connector.connect(host=config['host'],
                                  port=config['port'],
                                  user=config['user'],
                                  passwd=config['passwd'],
                                  db=config['db'])
    cur = cnx.cursor()
    print("SQL server connection established")

    return cnx, cur


def _drop_files_db():
    """Drop the DB we built."""
    bashCommand = ["mysql", "-h", HOST, "--user=%s" % USER, "--port=%s" % PORT, "--password=%s" % PASSWD, "-e", "drop database %s" % DB]
    process = subprocess.Popen(bashCommand, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    output, error = process.communicate()
    print(output, error)


# Fixture to wait for SQL connection to be available. Uses same SQL DB
# container for all tests in this module, so cleanup should occur within each
# test.
@pytest.fixture(scope="module")
def wait_for_sql(module_scoped_containers):
    """Wait for the SQL from docker-compose to become responsive"""
    attempts = 0

    while attempts < 6:
        try:
            cnx, cur = _connect_to_sql(SQL_CONFIG)
        except InterfaceError:
            print("Could not connect to SQL DB, waiting 5 seconds.")
            time.sleep(5)

        attempts += 1

    cur.execute("SELECT VERSION()")
    result = cur.fetchall()
    assert result
    return cnx, cur


def _restore_v0_db_structure():
    """Restore DB in v0 state from disk."""
    bashCommand = "mysql -h 127.0.0.1 --port {} --user=development --password=development".format(PORT)
    process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    output, error = process.communicate(open("./tests/db_schemas/files_v0.sql", 'rb').read())


def test_schema_v0_restore_and_clear(wait_for_sql):
    """Tests our ability to restore a database from file and then clear it when
    we're done.

    Note: This leaves you with out a "files" DB, in case you were expecting one.

    """
    _restore_v0_db_structure()

    cnx, cur = _connect_to_sql(SQL_CONFIG)

    table_query = cur.execute("SHOW tables;")

    tables = []
    for row in cur.fetchall():
        tables.append(row[0])

    print(tables)

    # These 3 tables should exist.
    assert 'feeds' in tables
    assert 'fields' in tables
    assert 'description' in tables

    cur.close()
    cnx.close()

    _drop_files_db()

    # The files DB shouldn't exist anymore, so this should fail
    with pytest.raises(Exception):
        cnx = mysql.connector.connect(host=HOST,
                                      port=PORT,
                                      user=USER,
                                      passwd=PASSWD,
                                      db=DB)


def test_blank_db_and_table_initialization_v1(wait_for_sql):
    """Test init_tables from empty database."""
    from sisock.db import init_tables
    init_tables(SQL_CONFIG, 1)

    cnx, cur = _connect_to_sql(SQL_CONFIG)

    table_query = cur.execute("SHOW tables;")

    tables = []
    for row in cur.fetchall():
        tables.append(row[0])

    print(tables)

    # These 5 tables should exist.
    assert 'feeds' in tables
    assert 'fields' in tables
    assert 'description' in tables
    assert 'db_structure' in tables
    assert 'file_info' in tables

    cur.execute("DESCRIBE feeds;")

    fields = []
    for (field, type_, null, key, default, extra) in cur.fetchall():
        fields.append(field)

    print(fields)

    # This shouldn't exist anymore, was in v0.
    assert 'filename' not in fields

    cur.close()
    cnx.close()

    _drop_files_db()


def test_schema_v0_to_v1_update(wait_for_sql):
    """Test updating to file database table structure layout v1 from v0.

    Start by loading v0 from an sql dump, then perform update to v1 and check
    it worked.

    """
    _restore_v0_db_structure()
    cnx, cur = _connect_to_sql(SQL_CONFIG)
    from sisock.db import _update_v0_to_v1, init_tables
    init_tables(SQL_CONFIG, 1)
    _update_v0_to_v1(cnx, cur)
    
    cur.execute("DESCRIBE feeds;")
    feed_cols = []
    for (field, type_, null, key, default, extra) in cur.fetchall():
        feed_cols.append(field)

    assert 'filename' not in feed_cols
    assert 'path' not in feed_cols
    assert 'scanned' not in feed_cols
    assert 'file_id' in feed_cols

    cur.execute("SELECT version FROM db_structure;")
    version = cur.fetchone()[0]

    assert version==1

    _drop_files_db


# Methods within components/g3_file_scanner/scan.py
def test_unix2sql():
    assert _unixtime2sql(1564434601.916555) == '2019-07-29 21:10:01.916555'
