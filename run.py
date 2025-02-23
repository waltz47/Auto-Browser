import sys
import asyncio
import argparse

sys.path.append("scripts")
sys.path.append("web")
from nyx import Nyx

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument( "-n","--num_workers", help="Number of workers to spawn")
    args = parser.parse_args()
    nyx = Nyx(num_workers=int(args.num_workers))
    asyncio.run(nyx.start())