#!/usr/bin/env python3

import re
import sys
import os
import dns_synchub

if __name__ == "__main__":
    # Remove the .py or .pyw or .exe extension from the script name
    script_name = re.sub(r"(-script\.pyw|\.exe)?$", "", sys.argv[0])
    # If the script is run as a module, use the directory name as the script name
    if sys.argv[0] == __file__:
        script_name = os.path.basename(os.path.dirname(sys.argv[0])).replace("_", "-")
    # Set the script name to the first argument and invoke the main function
    sys.argv[0] = script_name
    sys.exit(dns_synchub.main())
