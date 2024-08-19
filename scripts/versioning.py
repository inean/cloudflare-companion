#!/usr/bin/env python3

import argparse
import os
import sys

import toml

TOML_FILE = "pyproject.toml"
DATA_FILE = "src/dns_synchub/__about__.py"


def update_version(toml_file=None, data_file=None):
    # Get the current working directory
    current_dir = os.getcwd()

    # Compute the paths relative to the current working directory
    toml_file = os.path.join(current_dir, toml_file or TOML_FILE)
    data_file = os.path.join(current_dir, data_file or DATA_FILE)

    # Ensure the files exist
    if not os.path.exists(toml_file):
        sys.stderr.write(f"Source file '{toml_file}' not found\n")
        sys.exit(1)
    if not os.path.exists(data_file):
        sys.stderr.write(f"Destination File {data_file} not found\n")
        sys.exit(1)

    # Read the version from pyproject.toml
    with open(toml_file, "r") as f:
        pyproject_data = toml.load(f)
    # Read the current contents of __about__.py
    with open(data_file, "r") as f:
        lines = f.readlines()

    # Update the version in __about__.py
    with open(data_file, "w") as f:
        version = pyproject_data["project"]["version"]
        for line in lines:
            line = f'__version__ = "{version}"\n' if line.startswith("__version__") else line
            f.write(line)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Update version in destination file from source file.",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=TOML_FILE,
        help=f"PyProject file to read version from ({TOML_FILE})",
    )
    parser.add_argument(
        "--target",
        type=str,
        default=DATA_FILE,
        help=f"Python Destination file to update version in ({DATA_FILE})",
    )
    args = parser.parse_args()

    update_version(toml_file=args.source, data_file=args.target)
    update_version()
