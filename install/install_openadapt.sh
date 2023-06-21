#!/bin/bash
set -e

# Change these if a different version  is required
pythonCmd="python3.10"
pythonVerStr="Python 3.10*"
pythonInstaller="python-3.10.11-macos11 21.11.47.pkg"
pythonInstallerLoc="https://www.python.org/ftp/python/3.10.11/python-3.10.11-macos11.pkg"
pythonInstallerPath ="$HOME/downloads/$pythonInstaller"

# Remove OpenAdapt if it exists
Cleanup() {
    if [ -d "../OpenAdapt" ]; then
        cd ..
        rm -rf OpenAdapt
        echo "Deleted OpenAdapt directory"
    fi
}

# Refresh Path Environment variable
Refresh() {
    export PATH="$PATH:$(echo $PATH | tr ':' '\n' | grep -v -e '^$' -e '^/usr/local/share/dotnet' -e '^/usr/local/bin' | uniq | tr '\n' ':')$(echo $PATH | tr ':' '\n' | grep -e '^/usr/local/share/dotnet' -e '^/usr/local/bin' | uniq | tr '\n' ':')"
}

# Run a command and ensure it did not fail
RunAndCheck() {
    res=$($1)

    if [[ -z $res ]] || [[ $res == 0 ]]; then
        echo "Success: $2 : $res"
    else
        echo "Failed: $2 : $res"
        Cleanup
        exit 1
    fi
}

# Return true if a command/exe is available
CheckCMDExists() {
    command=$($1)

    if type -P $command >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

GetPythonCMD() {
    # Use Python alias of required version if it exists
    if CheckCMDExists $pythonCmd; then
        return
    fi

    # Use Python exe if it exists and is the required version
    pythonCmd="python"
    if CheckCMDExists $pythonCmd; then
        $res=$(python --version)
        if echo "$res" | grep -q "$pythonVerStr"; then
            return
        fi
    fi

    # Install required Python version
    RunAndCheck "curl --output "$pythonInstallerLoc"" "Download Python"
    exists=(test -e "$pythonInstallerPath")
    if [ ! $exists ]; then
        echo "Failed to download python installer"
        Cleanup
        exit 1
    fi

    echo "Installing python, click 'Yes' if prompted for permission"
    open -W "$pythonInstallerPath"

    # Refresh Path Environment Variable
    export PATH="$PATH:$(echo $PATH | tr ':' '\n' | grep -v -e '^$' -e '^/usr/local/share/dotnet' -e '^/usr/local/bin' | uniq | tr '\n' ':')$(echo $PATH | tr ':' '\n' | grep -e '^/usr/local/share/dotnet' -e '^/usr/local/bin' | uniq | tr '\n' ':')"

    # Make sure python is now available and the right version
    if CheckCMDExists $pythonCmd; then
        res=(python --version)
        if [[ "$res" =~ "$pythonVerStr" ]]; then
            return
        fi
    fi

    # Otherwise, Python is not available
    echo "Error after installing python. Uninstalling, click 'Yes' if prompted for permission"
    rm -r "$pythonInstallerPath"

    Cleanup
    exit
}

############################################################################################
# Installation starts here
############################################################################################

# Download brew
brewExists=$(CheckCMDExists "brew")
if [ ! $brewExists ]; then
    RunAndCheck "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" "download brew"
    Refresh # necessary ?
    brewExists=$(CheckCMDExists "brew")
    if [ ! $brewExists ]; then
        echo "Failed to download brew"
        Cleanup
        exit 1
    fi
fi

gitExists=$(CheckCMDExists "git")
if [ ! $gitExists ]; then
    # Install git
    RunAndCheck "brew install git" "Download git"
    gitExists=$(CheckCMDExists "git")
    if [ ! $gitExists ]; then
        echo "Failed to download git"
        Cleanup
        exit 1
    fi
fi

GetPythonCMD

[ -d "OpenAdapt" ] && mv OpenAdapt OpenAdapt-$(date +%Y-%m-%d_%H-%M-%S)
RunAndCheck "git clone https://github.com/MLDSAI/OpenAdapt.git" "Clone git repo"

cd OpenAdapt

RunAndCheck "python3.10 -m venv .venv" "Create python virtual environment"
source .venv/bin/activate
pip install wheel

# the following line generates a warning:
#   Ignoring pywin32: markers 'sys_platform == "win32"' don't match your environment
pip install -r requirements.txt

# the following line generates a warning:
#   [notice] To update, run: pip install --upgrade pip
pip install -e .

RunAndCheck "alembic upgrade head" "Update database"
RunAndCheck "python3.10 -m spacy download en_core_web_trf" "Download spacy model"
RunAndCheck "pytest" "Run tests"
