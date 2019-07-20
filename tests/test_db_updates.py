# Test database scheme updates
# For these tests to work you need to setup a development sql environment that
# will allow you to test the scheme updates on a clean DB.

# This can e done using Docker:
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

import subprocess
import mysql.connector
import pytest

HOST='127.0.0.1'
USER='development'
PASSWD='development'
DB='files'

def test_schema_v0_restore_and_clear():
    # Restore DB from disk
    bashCommand = "mysql -h 127.0.0.1 --user=development --password=development"
    process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    output, error = process.communicate(open("./db_schemas/files_v0.sql", 'rb').read())

    # Check we've loaded the v0 DB from disk successfully
    cnx = mysql.connector.connect(host=HOST,
                                  user=USER,
                                  passwd=PASSWD,
                                  db=DB)
    cur = cnx.cursor()
    print("SQL server connection established")

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

    # Drop the DB we restored
    bashCommand = ["mysql", "-h", "127.0.0.1", "--user=development", "--password=development", "-e", "drop database files"]
    process = subprocess.Popen(bashCommand, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    output, error = process.communicate()
    print(output, error)

    # The files DB shouldn't exist anymore, so this should fail
    with pytest.raises(Exception):
        cnx = mysql.connector.connect(host=HOST,
                                      user=USER,
                                      passwd=PASSWD,
                                      db=DB)
