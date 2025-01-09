import sys
sys.path.append("scripts")
sys.path.append("web")
from scripts.nyx import *

if __name__ == '__main__':
    nyx = Nyx()
    nyx.start()