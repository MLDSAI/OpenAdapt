import subprocess

from openadapt.app.main import run_app

def changes_needed(result: str) -> bool:
    """ Checks if git stash needs to be run.
    
    Assumes result is the result of git status.
    """
    if "Changes to be committed:" in result:
        return True
    if "Changes not staged for commit:" in result:
        return True
    if "Your branch is ahead of" in result:
        return True
    return False

result = subprocess.run(["git", "status"], capture_output=True, text=True)

if "branch is up to date" not in result.stdout:
    
    if changes_needed(result.stdout):
        subprocess.run(["git", "stash"])
        print("Changes stashed")
    
    subprocess.run(["git", "pull"])
    print("Updated the OpenAdapt App")

run_app() # start gui