#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "Installing requirements..."
python -m pip install -r requirements.txt
echo "Starting SNP-Disease Platform..."
python -m streamlit run app/main.py --server.headless false
