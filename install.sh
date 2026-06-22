#!/bin/bash
#
# Script to install git-overleaf from the web. Can be run multiple times to
# update the git-overleaf script.
#
# To run this script paste
#
#  curl https://raw.githubusercontent.com/robol/python-overleaf-git-unipi/refs/heads/main/install.sh | bash
#

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-${HOME}/.local/share/python-overleaf-git-unipi}"
VENV_DIR="${INSTALL_DIR}/venv"
BIN_DIR="${INSTALL_DIR}/bin"
PACKAGE_SPEC="${PACKAGE_SPEC:-overleaf-git-unipi}"
PLATFORM="${PLATFORM:-$(uname -s)}"

die() {
    printf 'install.sh: %s\n' "$*" >&2
    exit 1
}

find_python() {
    if [ -n "${PYTHON_BIN:-}" ]; then
        [ -x "${PYTHON_BIN}" ] || die "PYTHON_BIN is not executable: ${PYTHON_BIN}"
        printf '%s\n' "${PYTHON_BIN}"
        return
    fi

    command -v python3 || true
}

PYTHON_BIN="$(find_python)"
if [ -z "${PYTHON_BIN}" ]; then
    if [ "${PLATFORM}" = "Darwin" ]; then
        die "Python 3 was not found. Install it from https://www.python.org/ or run: brew install python"
    fi
    die "Python 3 was not found. Install Python 3.9 or newer and try again."
fi

if ! "${PYTHON_BIN}" -c \
    'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'
then
    die "Python 3.9 or newer is required (found $("${PYTHON_BIN}" --version 2>&1))."
fi

mkdir -p "${INSTALL_DIR}" "${BIN_DIR}"

if [ -d "${VENV_DIR}" ] &&
    ! "${VENV_DIR}/bin/python" -c 'import sys' >/dev/null 2>&1
then
    printf 'Recreating stale virtual environment in %s\n' "${VENV_DIR}"
    rm -rf "${VENV_DIR}"
fi

if [ ! -x "${VENV_DIR}/bin/python" ]; then
    if ! "${PYTHON_BIN}" -m venv "${VENV_DIR}"; then
        if [ "${PLATFORM}" = "Darwin" ]; then
            die "Could not create a virtual environment. Reinstall Python 3 and try again."
        fi
        die "Could not create a virtual environment. Install your distribution's python3-venv package and try again."
    fi
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip

SCRIPT_PATH="${BASH_SOURCE[0]:-}"
SCRIPT_DIR=""
if [ -n "${SCRIPT_PATH}" ]; then
    SCRIPT_DIR="$(cd -- "$(dirname -- "${SCRIPT_PATH}")" && pwd)"
fi

if [ -n "${SCRIPT_DIR}" ] &&
    [ -d "${SCRIPT_DIR}/overleaf_git_unipi" ] &&
    { [ -f "${SCRIPT_DIR}/pyproject.toml" ] || [ -f "${SCRIPT_DIR}/setup.py" ]; }; then
    "${VENV_DIR}/bin/python" -m pip install --upgrade "${SCRIPT_DIR}"
else
    "${VENV_DIR}/bin/python" -m pip install --upgrade "${PACKAGE_SPEC}"
fi

COMMAND_PATH="${BIN_DIR}/git-overleaf"
if [ -d "${COMMAND_PATH}" ] && [ ! -L "${COMMAND_PATH}" ]; then
    die "Cannot install command because ${COMMAND_PATH} is a directory."
fi
rm -f "${COMMAND_PATH}"
ln -s "${VENV_DIR}/bin/git-overleaf" "${COMMAND_PATH}"

PROFILE="${PROFILE:-}"
if [ -z "${PROFILE}" ]; then
    SHELL_NAME="$(basename "${SHELL:-}")"
    case "${SHELL_NAME}" in
        zsh)
            PROFILE="${HOME}/.zshrc"
            ;;
        bash)
            if [ "${PLATFORM}" = "Darwin" ]; then
                PROFILE="${HOME}/.bash_profile"
            else
                PROFILE="${HOME}/.profile"
            fi
            ;;
        "")
            PROFILE="${HOME}/.profile"
            ;;
    esac
fi

if [ -n "${PROFILE}" ]; then
    touch "${PROFILE}"
fi

if [ -n "${PROFILE}" ] && ! grep -Fq "${BIN_DIR}" "${PROFILE}"; then
    {
        printf '\n'
        printf '# Add git-overleaf to PATH.\n'
        printf 'export PATH="%s:$PATH"\n' "${BIN_DIR}"
    } >> "${PROFILE}"
fi

printf 'git-overleaf installed in %s\n' "${INSTALL_DIR}"
if [ -n "${PROFILE}" ]; then
    printf 'Restart your shell or run: source "%s"\n' "${PROFILE}"
else
    printf 'Add this directory to your PATH: %s\n' "${BIN_DIR}"
fi
