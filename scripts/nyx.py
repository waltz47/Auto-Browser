import os
import asyncio
from playwright.async_api import async_playwright
from worker import Worker
import json
from openai import AsyncOpenAI

class Nyx:
    def __init__(self):
        """Initialize Nyx with basic configuration."""
        # Load configuration
        with open("api_config.cfg", 'r') as f:
            cfg = f.read()

        self.config = {}
        for line in cfg.split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                self.config[key.strip()] = value.strip().strip('"')

        # Determine API type
        if os.environ.get("OPENAI_API_KEY") is not None:
            self.api = "openai"
            self.MODEL = self.config["openai_model"]
        elif os.environ.get("XAI_API_KEY") is not None:
            self.api = "xai"
            self.MODEL = self.config["xai_model"]
        else:
            self.api = "ollama"
            self.MODEL = self.config["ollama_local_model"]

        # Load tools
        with open("tools.json", 'r') as f:
            self.tools = json.load(f)["tools"]

    async def setup_browser(self):
        """Initialize browser and create a page."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=[
                "--new-window",
                "--ignore-certificate-errors",
                "--disable-extensions",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36",
            viewport=None,
            permissions=["geolocation"],
        )
        
        self.page = await self.context.new_page()

    async def create_worker(self, task_description: str = "Initializing") -> Worker:
        """Create and initialize a single worker."""
        worker = Worker(
            page=self.page,
            worker_id=0,
            request_queue=None,
            api=self.api,
            model=self.MODEL,
            max_messages=100,
            tools=self.tools
        )
        worker.current_task = task_description
        await worker.setup_client()
        return worker

    async def cleanup(self):
        """Clean up resources."""
        if hasattr(self, 'browser'):
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()

    async def start(self, initial_task: str = None):
        """Start Nyx with a single worker."""
        try:
            # Setup browser
            await self.setup_browser()
            
            # Create worker
            worker = await self.create_worker()
            
            print("\nWorker initialized and ready!")
            print("Enter your message or type 'exit' to quit")

            # Get initial input
            user_input = input("\nYour message: ")
            if user_input.lower() == 'exit':
                return

            # Add initial input to message history
            worker.messages.add_user_text(user_input)
            
            # Main processing loop
            while True:
                try:
                    # Process step
                    active = await worker.step()
                    if not active:
                        break

                except KeyboardInterrupt:
                    print("\nExiting...")
                    break
                except Exception as e:
                    print(f"Error: {e}")
                    continue

        finally:
            await self.cleanup()

if __name__ == "__main__":
    nyx = Nyx()
    asyncio.run(nyx.start())