#!/usr/bin/env bash
set -euo pipefail

export PATH="${HOME}/.local/bin:${PATH}"

pip3 install --user -r requirements.txt streamlit pandas
