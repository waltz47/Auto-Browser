import sys
import asyncio
import argparse
import pandas as pd

sys.path.append("scripts")
sys.path.append("web")
from nyx import Nyx

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument( "--csv_input",default="input/research.csv", help="CSV file containing inputs")
    args = parser.parse_args()
    
    df = pd.read_csv(str(args.csv_input))
    n = len(df)
    input_list = list(df['tasks'])
    print(f"Tasks: {input_list}")
    nyx = Nyx(num_workers=int(n))
    nyx.input_list = input_list
    asyncio.run(nyx.start())