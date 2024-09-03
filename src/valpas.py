#!/usr/bin/env python
"""
Wrapper that executes the main function in valpas.py. Once the 
package is properly installed this script can be moved at the users 
convenience and executed from their directory of choice.
"""

__author__ = 'Yannick Mahlich'
__email__ = 'ymahlich@bromberglab.org'

from valpas.valpas import main

if __name__ == '__main__':
    try: main()
    except KeyboardInterrupt: pass