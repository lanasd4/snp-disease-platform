"""
Sample/Demo Data Loader
"""

import sqlite3
import pandas as pd
from core.paths import DATABASE_PATH, DATA_DIR


SAMPLE_DATA_DIR = DATA_DIR / "sample"

GENES_FILE = SAMPLE_DATA_DIR / "genes.csv"
SNPS_FILE = SAMPLE_DATA_DIR / "snps.csv"
STUDIES_FILE = SAMPLE_DATA_DIR / "studies.csv"
POPULATION_REGIONS_FILE = SAMPLE_DATA_DIR / "population_regions.csv"
ASSOCIATIONS_FILE = SAMPLE_DATA_DIR / "associations.csv"


def create_connection():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(f"Database file was not found: {DATABASE_PATH}")

    connection = sqlite3.connect(DATABASE_PATH)
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def create_sample_tables(connection):
    cursor = connection.cursor()

    cursor.execute("DROP TABLE IF EXISTS Association;")
    cursor.execute("DROP TABLE IF EXISTS Study;")
    cursor.execute("DROP TABLE IF EXISTS SNP;")
    cursor.execute("DROP TABLE IF EXISTS Gene;")
    cursor.execute("DROP TABLE IF EXISTS PopulationRegion;")

    cursor.execute("""
        CREATE TABLE Gene (
            gene_id INTEGER PRIMARY KEY,
            gene_symbol TEXT NOT NULL UNIQUE,
            gene_name TEXT NOT NULL,
            chromosome TEXT,
            active TEXT NOT NULL CHECK(active IN ('Y', 'N'))
        );
    """)

    cursor.execute("""
        CREATE TABLE SNP (
            snp_id INTEGER PRIMARY KEY,
            rsid TEXT NOT NULL UNIQUE,
            gene_id INTEGER NOT NULL,
            chromosome TEXT,
            position TEXT,
            variant_type TEXT NOT NULL,
            functional_annotation TEXT,
            active TEXT NOT NULL CHECK(active IN ('Y', 'N')),
            FOREIGN KEY (gene_id) REFERENCES Gene(gene_id)
        );
    """)

    cursor.execute("""
        CREATE TABLE PopulationRegion (
            population_region_id INTEGER PRIMARY KEY,
            country TEXT NOT NULL,
            region TEXT NOT NULL,
            population_label TEXT NOT NULL,
            is_arab_related TEXT NOT NULL CHECK(is_arab_related IN ('Y', 'N')),
            notes TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE Study (
            study_id INTEGER PRIMARY KEY,
            study_title TEXT NOT NULL,
            source_name TEXT NOT NULL,
            publication_year INTEGER,
            pmid TEXT,
            country TEXT,
            population_region_id INTEGER NOT NULL,
            active TEXT NOT NULL CHECK(active IN ('Y', 'N')),
            FOREIGN KEY (population_region_id) REFERENCES PopulationRegion(population_region_id)
        );
    """)

    cursor.execute("""
        CREATE TABLE Association (
            association_id INTEGER PRIMARY KEY,
            disease_id INTEGER NOT NULL,
            snp_id INTEGER NOT NULL,
            study_id INTEGER NOT NULL,
            population_region_id INTEGER NOT NULL,
            p_value REAL,
            odds_ratio REAL,
            risk_allele TEXT,
            effect_allele TEXT,
            source_database TEXT,
            evidence_level TEXT,
            notes TEXT,
            FOREIGN KEY (disease_id) REFERENCES Disease(disease_id),
            FOREIGN KEY (snp_id) REFERENCES SNP(snp_id),
            FOREIGN KEY (study_id) REFERENCES Study(study_id),
            FOREIGN KEY (population_region_id) REFERENCES PopulationRegion(population_region_id)
        );
    """)

    connection.commit()


def read_csv_file(file_path):
    if not file_path.exists():
        raise FileNotFoundError(f"Required sample file was not found: {file_path}")

    dataframe = pd.read_csv(file_path)
    dataframe = dataframe.where(pd.notnull(dataframe), None)

    return dataframe


def load_sample_csv_data():
    genes_df = read_csv_file(GENES_FILE)
    snps_df = read_csv_file(SNPS_FILE)
    population_regions_df = read_csv_file(POPULATION_REGIONS_FILE)
    studies_df = read_csv_file(STUDIES_FILE)
    associations_df = read_csv_file(ASSOCIATIONS_FILE)

    return genes_df, snps_df, population_regions_df, studies_df, associations_df


def insert_sample_data(connection, genes_df, snps_df, population_regions_df, studies_df, associations_df):
    genes_df.to_sql("Gene", connection, if_exists="append", index=False)
    snps_df.to_sql("SNP", connection, if_exists="append", index=False)
    population_regions_df.to_sql("PopulationRegion", connection, if_exists="append", index=False)
    studies_df.to_sql("Study", connection, if_exists="append", index=False)
    associations_df.to_sql("Association", connection, if_exists="append", index=False)


def check_sample_tables(connection):
    cursor = connection.cursor()

    table_names = [
        "Gene",
        "SNP",
        "PopulationRegion",
        "Study",
        "Association"
    ]

    counts = {}

    for table_name in table_names:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        counts[table_name] = cursor.fetchone()[0]

    return counts


def load_sample_data():
    connection = create_connection()

    try:
        create_sample_tables(connection)

        genes_df, snps_df, population_regions_df, studies_df, associations_df = load_sample_csv_data()

        insert_sample_data(
            connection,
            genes_df,
            snps_df,
            population_regions_df,
            studies_df,
            associations_df
        )

        counts = check_sample_tables(connection)

        print("Sample data loaded successfully into SQLite.")
        print("Database path:", DATABASE_PATH)

        for table_name, row_count in counts.items():
            print(f"{table_name} rows:", row_count)

    finally:
        connection.close()


if __name__ == "__main__":
    load_sample_data()
