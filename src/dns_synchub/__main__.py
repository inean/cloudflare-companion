#!/usr/bin/env python3

import pathlib
import sys

import dns_synchub

if __name__ == "__main__":
    # If the script is run as a module, use the directory name as the script name
    script_name = pathlib.Path(sys.argv[0]).stem
    if sys.argv[0] == __file__:
        script_path = pathlib.Path(sys.argv[0])
        script_name = script_path.parent.name.replace("_", "-")
    # Set the script name to the first argument and invoke the main function
    sys.argv[0] = script_name
    sys.exit(dns_synchub.main())
