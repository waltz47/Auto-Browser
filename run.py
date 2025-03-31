import os
import sys
import asyncio
import argparse
from playwright.async_api import async_playwright
import json

# Add scripts directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'scripts'))
from worker import Worker
from scripts.nyx import Nyx

async def run_terminal_mode():
    """Run Nyx in terminal mode."""
    nyx = Nyx()
    await nyx.setup_browser()
    worker = await nyx.create_worker()
    
    print("\nWorker initialized and ready!")
    print("Enter your task or type 'exit' to quit")

    try:
        while True:
            user_input = input("\nEnter task: ")
            if user_input.lower() == 'exit':
                break

            # Add user input to message history
            worker.messages.add_user_text(user_input)
            
            # Process task - only break if waiting for input
            while True:
                active = await worker.step()
                if worker.waiting_for_input:
                    break
                # Sleep briefly to avoid overwhelming the system
                await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        await nyx.cleanup()

def run_dashboard_mode():
    """Run Nyx in dashboard mode."""
    nyx = Nyx()
    nyx.run_dashboard()

def main():
    parser = argparse.ArgumentParser(description='Run Nyx AI in terminal or dashboard mode')
    parser.add_argument('--mode', choices=['terminal', 'dashboard'], default='terminal',
                      help='Run mode: terminal or dashboard (default: terminal)')
    args = parser.parse_args()

    if args.mode == 'terminal':
        asyncio.run(run_terminal_mode())
    else:
        run_dashboard_mode()

if __name__ == "__main__":
    os.makedirs("log",exist_ok=True)
    main()
