-- SQLite schema for database/snp_platform.db (used by pipeline.rebuild_dataset).

CREATE TABLE Disease (
            disease_id INTEGER PRIMARY KEY,
            canonical_name TEXT NOT NULL UNIQUE,
            arabic_name TEXT NOT NULL,
            category TEXT NOT NULL,
            active TEXT NOT NULL CHECK(active IN ('Y', 'N'))
        );

CREATE TABLE DiseaseSynonym (
            synonym_id INTEGER PRIMARY KEY,
            disease_id INTEGER NOT NULL,
            synonym TEXT NOT NULL,
            language TEXT NOT NULL,
            synonym_type TEXT NOT NULL,
            FOREIGN KEY (disease_id) REFERENCES Disease(disease_id)
        );

CREATE TABLE Gene (
            gene_id INTEGER PRIMARY KEY,
            gene_symbol TEXT NOT NULL UNIQUE,
            gene_name TEXT NOT NULL,
            chromosome TEXT,
            active TEXT NOT NULL CHECK(active IN ('Y', 'N'))
        );

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

CREATE TABLE PopulationRegion (
            population_region_id INTEGER PRIMARY KEY,
            country TEXT NOT NULL,
            region TEXT NOT NULL,
            population_label TEXT NOT NULL,
            ancestry TEXT,
            is_arab_related TEXT NOT NULL CHECK(is_arab_related IN ('Y', 'N')),
            notes TEXT
        );

CREATE TABLE Study (
            study_id INTEGER PRIMARY KEY,
            study_title TEXT NOT NULL,
            source_name TEXT NOT NULL,
            publication_year INTEGER,
            pubmed_id TEXT,
            journal TEXT,
            study_accession TEXT,
            country TEXT,
            population_region_id INTEGER NOT NULL,
            active TEXT NOT NULL CHECK(active IN ('Y', 'N')),
            FOREIGN KEY (population_region_id) REFERENCES PopulationRegion(population_region_id)
        );

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

CREATE TABLE UserAccount (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user', 'guest')),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
                created_at TEXT NOT NULL,
                last_login TEXT
            , must_change_password INTEGER NOT NULL DEFAULT 0);

CREATE TABLE AdminActionLog (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            );

CREATE TABLE UserSearchHistory (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                search_mode TEXT NOT NULL,
                query TEXT NOT NULL,
                result_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES UserAccount(user_id)
            );

CREATE TABLE LoginThrottle (
                username TEXT PRIMARY KEY,
                fail_count INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT
            );
