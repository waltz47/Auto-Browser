import sys
import asyncio
import argparse
import pandas as pd

sys.path.append("scripts")
sys.path.append("web")
from nyx import Nyx

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    # parser.add_argument("--command", required=True, help="Command to execute")
    args = parser.parse_args()
    
    nyx = Nyx()
    initial_input = input("Enter input: ")
    asyncio.run(nyx.handle_initial_input(initial_input))
    asyncio.run(nyx.start())