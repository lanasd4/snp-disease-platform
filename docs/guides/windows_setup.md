# Windows Local Run Guide

## Project Overview

Smart Arabic-Supported SNP-Disease Bioinformatics Platform is a local Streamlit research and education app for exploring disease, SNP, gene, study, ranking, Arabic/English search, glossary, PRS prototype, Circos-style visualization, and admin data workflows.

The local app entry point is:

```bat
app\main.py
```

Runtime data stays inside the project folder. The app does not need Google Colab or Google Drive.

## Required Software

- Windows 11
- Python 3.12 or 3.13
- pip
- A terminal such as Command Prompt, PowerShell, or Windows Terminal

The current tested local interpreter was Python 3.13.6.

## Create a Virtual Environment

From the project root:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run the Setup Check

```bat
python setup_windows.py
```

The setup script creates missing folders only. It never overwrites database files, CSV files, backups, staging files, or assets.

It verifies:

- `database/snp_platform.db`
- required CSV files under `data/`
- required app and script files
- upload, staging, backup, merge-log, output, and asset folders
- expected SQLite tables, including authentication and audit tables

## Run the App

Recommended:

```bat
run.bat
```

Manual Streamlit command:

```bat
python -m streamlit run app\main.py
```

Streamlit opens the app in the browser. If it does not open automatically, use the local URL printed in the terminal, usually `http://localhost:8501`.

## Database Location

Main database:

```text
database/snp_platform.db
```

Authentication is stored in the same SQLite database:

- `UserAccount`
- `AdminActionLog`

No account ships with the project. To create the first admin, set two environment
variables before starting the app (only used when the database has no active admin):

```bat
set SNP_ADMIN_USERNAME=your_admin_name
set SNP_ADMIN_PASSWORD=a-long-unique-password
python -m streamlit run app\main.py
```

Set `SNP_ALLOW_REGISTRATION=false` to hide public self-registration.

Passwords are stored as salted PBKDF2-SHA256 hashes. Do not bypass login if authentication fails; check the database path, active user status, and password.

## Project Structure

```text
app/                         Streamlit UI: main.py, views/ (pages), ui/ (widgets + CSS), assets/
core/                        Business logic: search, auth, i18n, PRS, summaries, AI, admin workflows
pipeline/                    Offline data-preparation stages (python -m pipeline.<stage>)
tests/                       Automated tests (python -m pytest)
database/                    SQLite database
data/master_diseases.csv     Disease dictionary
data/disease_synonyms.csv    Arabic/English synonyms
data/metadata/               Source registry, glossary, labels
data/raw/                    Raw downloaded or uploaded data
data/raw/admin_uploaded/     Admin upload storage
data/processed/              Cleaned, normalized, ranked, graph, staging data
data/processed/staging/      Approved staged data before final merge
data/processed/backups/      Final-merge and rollback backups
data/processed/merge_logs/   Merge and rollback logs
outputs/tables/              Validation, test, audit, summary output tables
outputs/models/              ML classifier model
outputs/figures/             Generated figures
backups/                     Historical code/data backups
docs/                        Project notes and design history
```

## Admin Workflow

Admin tools are available only after logging in as an admin user.

Supported local workflow:

1. Upload source file into `data/raw/admin_uploaded/`.
2. Validate and clean into `data/processed/admin_sources/`.
3. Register source in `data/metadata/data_sources_registry.csv`.
4. Approve source and create staging file under `data/processed/staging/`.
5. Final merge into `data/processed/ranked_associations_initial.csv`.
6. Backup and rollback through `data/processed/backups/` and `data/processed/merge_logs/`.
7. Audit actions through SQLite `AdminActionLog`.

## Troubleshooting

### `ModuleNotFoundError`

Install dependencies:

```bat
python -m pip install -r requirements.txt
```

### Streamlit does not open

Run manually:

```bat
python -m streamlit run app\main.py
```

Then open the printed localhost URL.

### Login fails

Check:

- `database/snp_platform.db` exists
- `UserAccount` table exists
- user is active
- password is correct
- default admin was created by `setup_windows.py` or app startup

### Database missing

Restore `database/snp_platform.db` from a backup or recreate the sample database with the project scripts. Do not overwrite an existing working database.

### Plotly or visual pages fail

Install requirements again:

```bat
python -m pip install -r requirements.txt
```

## Update Dependencies

After activating the virtual environment:

```bat
python -m pip install --upgrade -r requirements.txt
python setup_windows.py
```

## Move to Another PC

Copy the whole `SNP_Disease_Platform` folder, including:

- `database/`
- `data/`
- `outputs/`
- `app/assets/`
- `backups/`
- `requirements.txt`
- `setup_windows.py`
- `run.bat`

Then create a new virtual environment and install requirements on the new PC.
