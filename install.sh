#!/bin/bash
#
# Script to install git-overleaf from the web. Can be run multiple times to
# update the git-overleaf script.
#
# To run this script paste
#  
#  curl https://github.com/robol/git-overleaf-unipi/raw/master/install.sh | bash"
#

set -euo pipefail

INSTALL_DIR="${HOME}/.local/share/python-overleaf-git-unipi"
VENV_DIR="${INSTALL_DIR}/venv"
BIN_DIR="${INSTALL_DIR}/bin"
PROFILE="${HOME}/.profile"
PACKAGE_SPEC="${PACKAGE_SPEC:-overleaf-git-unipi}"

mkdir -p "${INSTALL_DIR}" "${BIN_DIR}"

if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "${SCRIPT_DIR}/overleaf_git_unipi" ] &&
    { [ -f "${SCRIPT_DIR}/pyproject.toml" ] || [ -f "${SCRIPT_DIR}/setup.py" ]; }; then
    "${VENV_DIR}/bin/python" -m pip install --upgrade "${SCRIPT_DIR}"
else
    "${VENV_DIR}/bin/python" -m pip install --upgrade "${PACKAGE_SPEC}"
fi

ln -sfn "${VENV_DIR}/bin/git-overleaf" "${BIN_DIR}/git-overleaf"

touch "${PROFILE}"
if ! grep -Fq "${BIN_DIR}" "${PROFILE}"; then
    {
        printf '\n'
        printf '# Add git-overleaf to PATH.\n'
        printf 'export PATH="%s:$PATH"\n' "${BIN_DIR}"
    } >> "${PROFILE}"
fi

printf 'git-overleaf installed in %s\n' "${INSTALL_DIR}"
printf 'Restart your shell or run: export PATH="%s:$PATH"\n' "${BIN_DIR}"
