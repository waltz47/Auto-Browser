import os
import sys
import asyncio
from playwright.async_api import async_playwright
import json

# Add scripts directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'scripts'))
from worker import Worker

async def main():
    # Load configuration
    with open("api_config.cfg", 'r') as f:
        cfg = f.read()

    config = {}
    for line in cfg.split('\n'):
        if '=' in line:
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip().strip('"')

    # Determine API type
    if os.environ.get("OPENAI_API_KEY") is not None:
        api = "openai"
        model = config["openai_model"]
    elif os.environ.get("XAI_API_KEY") is not None:
        api = "xai"
        model = config["xai_model"]
    else:
        api = "ollama"
        model = config["ollama_local_model"]

    # Load tools
    with open("tools.json", 'r') as f:
        tools = json.load(f)["tools"]

    # Initialize playwright
    async with async_playwright() as playwright:
        # Launch browser in a new window
        browser = await playwright.chromium.launch(
            headless=False,
            args=[
                "--new-window",
                "--ignore-certificate-errors",
                "--disable-extensions",
                "--disable-blink-features=AutomationControlled",
            ]
        )

        # Create context and page
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36",
            viewport=None,
            permissions=["geolocation"],
        )
        page = await context.new_page()

        # Create worker
        worker = Worker(
            page=page,
            worker_id=0,
            request_queue=None,  # No queue needed
            api=api,
            model=model,
            max_messages=100,
            tools=tools
        )

        # Initialize API client
        await worker.setup_client()

        print("\nWorker initialized and ready!")
        print("Enter your task or type 'exit' to quit")

        # Main input loop
        while True:
            try:
                user_input = input("\nEnter task: ")
                if user_input.lower() == 'exit':
                    break

                # Set task and process
                worker.current_task = user_input
                worker.waiting_for_input = False
                worker.messages.add_user_text(user_input)  # Add user input to message history
                
                # Process task
                while True:
                    active = await worker.step()
                    if not active or worker.waiting_for_input:
                        break

            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                print(f"Error: {e}")
                continue

        # Cleanup
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
