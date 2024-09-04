#!/usr/bin/env python
"""
Wrapper that executes the main function in valpas.py. Once the 
package is properly installed this script can be moved at the users 
convenience and executed from their directory of choice.
"""
import sys
from valpas.valpas import main

if __name__ == '__main__':
    try: main(sys.argv[1:])
    except KeyboardInterrupt: pass