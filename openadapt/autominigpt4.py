"""
Automate installation of MiniGPT-4

Usage: python openadapt/autominigpt4.py
"""

import subprocess
import os
import sys


# TODO: assume have Git

def clone_repository(repo_url, target_dir):
    try:
        subprocess.check_call(['git', 'clone', repo_url, target_dir])
        print("Repository cloned successfully!")
    except subprocess.CalledProcessError as e:
        print("Failed to clone repository:", e)


def shallow_clone_repository(repo_url, target_dir):
    try:
        subprocess.check_call(['git', 'clone', '--depth', '1', repo_url, target_dir])
        print("Repository cloned successfully!")
    except subprocess.CalledProcessError as e:
        print("Failed to clone repository:", e)


def check_and_clone(repo_url, target_dir, shallow):



def is_valid_git_repository():
    try:
        subprocess.check_output(['git', 'rev-parse', '--is-inside-work-tree'])
        return True
    except subprocess.CalledProcessError:
        return False


def download_lfs_files(repo_dir):
    try:
        subprocess.check_call(['git', 'lfs', 'fetch'])
        subprocess.check_call(['git', 'lfs', 'checkout'])
        print(f"LFS files downloaded to {repo_dir} successfully!")
    except subprocess.CalledProcessError as e:
        print(f"Failed to download LFS files to {repo_dir}:", e)


def delete_files(files_to_delete):
    for file_name in files_to_delete:
        try:
            subprocess.check_call(['git', 'rm', file_name])
            print(f"{file_name} removed successfully!")
        except subprocess.CalledProcessError as e:
            print(f"Failed to remove {file_name}:", e)


if __name__ == "__main__":
    # clone MiniGPT-4
    minigpt4 = os.path.abspath('MiniGPT4')
    # Check if the repository already exists
    if os.path.exists(minigpt4):
        os.chdir(minigpt4)
        if not is_valid_git_repository():
            print(f"Directory '{minigpt4}' exists but is not a valid Git repository. Please"
                  f"check the files in this directory and choose whether to delete the directory."
                  f"Only restart the installation process if you have deleted or renamed "
                  f"this directory.")
            sys.exit()
        else:
            print(f"Repository '{minigpt4}' already exists and is valid. Skipping cloning step.")
    else:
        clone_repository('https://github.com/Vision-CAIR/MiniGPT-4', minigpt4)
        os.chdir(minigpt4)

    # install git lfs
    try:
        subprocess.check_call(['git', 'lfs', 'install'])
        print("Git LFS installed successfully!")
    except subprocess.CalledProcessError as e:
        print("Failed to install Git LFS:", e)

    # TODO: test below
    # clone vicuna 13b v1.1 weights
    vicuna = os.path.join(minigpt4, 'vicuna-13b-delta-v1.1')
    clone_repository('https://huggingface.co/lmsys/vicuna-13b-delta-v1.1', vicuna)
    # delete all the partially downloaded files
    os.chdir(vicuna)
    delete_files(['pytorch_model-00001-of-00003.bin', 'pytorch_model-00002-of-00003.bin',
                  'pytorch_model-00003-of-00003.bin'])
    # redownload the complete large size files
    download_lfs_files(vicuna)
    os.chdir(minigpt4)

    # clone llama 13b weights
    llama = os.path.join(minigpt4, 'llama-13b')
    clone_repository('https://huggingface.co/huggyllama/llama-13b', llama)
    # delete all the partially downloaded files
    os.chdir(llama)
    delete_files(['pytorch_model-00001-of-00003.bin', 'pytorch_model-00002-of-00003.bin',
                  'pytorch_model-00003-of-00003.bin', 'model-00001-of-00003.safetensors',
                  'model-00002-of-00003.safetensors', 'model-00003-of-00003.safetensors'])
    # redownload the complete large size files
    download_lfs_files(llama)

    # pip3 install fschat
    # install FastChat
    try:
        subprocess.check_call(['pip3', 'install', 'fschat'])
        print("FastChat installed successfully!")
    except subprocess.CalledProcessError as e:
        print("Failed to install FastChat:", e)

    # python -m fastchat.model.apply_delta --base-model-path D:\llama-13b
    # --target-model-path D:\vicuna_weights --delta-path D:\vicuna-13b-delta-v1.1 --low-cpu-mem
    # create working weight
    target = os.path.join(minigpt4, 'vicuna')
    # assuming most people don't have 60GB of CPU RAM, so we use --low-cpu-mem
    try:
        subprocess.check_call(['python', '-m', 'fastchat.model.apply_delta', '--base-model-path',
                               llama, '--target-model-path', target, '--delta-path', vicuna,
                               '--low-cpu-mem'])
        print("Working weight created successfully!")
    except subprocess.CalledProcessError as e:
        print("Failed to create working weight:", e)

    # Then, set the path to the vicuna weight in the model config file here at Line 16.
    file1 = os.path.join(minigpt4, 'minigpt4', 'configs', 'models', 'minigpt4.yaml')
    with open(file1, "r") as file:
        # Read the contents of the file
        file_contents = file.read()

    modified_contents = file_contents.replace("/path/to/vicuna/weights/", target)

    with open(file1, "w") as file:
        # Write the modified contents to the file
        file.write(modified_contents)

    # Then, set the path to the pretrained checkpoint in the evaluation
    #  config file in eval_configs/minigpt4_eval.yaml at Line 11.
    checkpoint_dir = os.path.abspath('minigpt4_checkpoint')
    checkpoint = os.path.join(checkpoint_dir, 'pretrained_minigpt4.pth')
    file2 = os.path.join(minigpt4, 'eval_configs', 'minigpt4_eval.yaml')
    with open(file2, "r") as file:
        # Read the contents of the file
        file_contents = file.read()

    modified_contents = file_contents.replace("/path/to/pretrained/ckpt/", checkpoint)

    with open(file2, "w") as file:
        # Write the modified contents to the file
        file.write(modified_contents)
