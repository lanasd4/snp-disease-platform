"""
Database Setup - Disease and DiseaseSynonym Tables
"""

import sqlite3
import pandas as pd
from core.paths import DATABASE_PATH, MASTER_DISEASES_FILE, DISEASE_SYNONYMS_FILE


def create_connection():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def create_tables(connection):
    cursor = connection.cursor()

    cursor.execute("DROP TABLE IF EXISTS DiseaseSynonym;")
    cursor.execute("DROP TABLE IF EXISTS Disease;")

    cursor.execute("""
        CREATE TABLE Disease (
            disease_id INTEGER PRIMARY KEY,
            canonical_name TEXT NOT NULL UNIQUE,
            arabic_name TEXT NOT NULL,
            category TEXT NOT NULL,
            active TEXT NOT NULL CHECK(active IN ('Y', 'N'))
        );
    """)

    cursor.execute("""
        CREATE TABLE DiseaseSynonym (
            synonym_id INTEGER PRIMARY KEY,
            disease_id INTEGER NOT NULL,
            synonym TEXT NOT NULL,
            language TEXT NOT NULL,
            synonym_type TEXT NOT NULL,
            FOREIGN KEY (disease_id) REFERENCES Disease(disease_id)
        );
    """)

    connection.commit()


def load_csv_data():
    diseases_df = pd.read_csv(MASTER_DISEASES_FILE)
    synonyms_df = pd.read_csv(DISEASE_SYNONYMS_FILE)
    return diseases_df, synonyms_df


def insert_diseases(connection, diseases_df):
    diseases_df.to_sql(
        "Disease",
        connection,
        if_exists="append",
        index=False
    )


def insert_disease_synonyms(connection, synonyms_df):
    synonyms_df.to_sql(
        "DiseaseSynonym",
        connection,
        if_exists="append",
        index=False
    )


def check_database(connection):
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM Disease;")
    disease_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM DiseaseSynonym;")
    synonym_count = cursor.fetchone()[0]

    return disease_count, synonym_count


def build_database():
    connection = create_connection()

    try:
        create_tables(connection)

        diseases_df, synonyms_df = load_csv_data()

        insert_diseases(connection, diseases_df)
        insert_disease_synonyms(connection, synonyms_df)

        disease_count, synonym_count = check_database(connection)

        print("Database created successfully.")
        print("Database path:", DATABASE_PATH)
        print("Disease rows:", disease_count)
        print("DiseaseSynonym rows:", synonym_count)

    finally:
        connection.close()


if __name__ == "__main__":
    build_database()
