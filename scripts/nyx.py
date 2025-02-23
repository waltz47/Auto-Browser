import os
import sys
import time
import queue
from queue import Queue
from playwright.async_api import async_playwright
from worker import Worker
import asyncio

class Nyx:
    def __init__(self, num_workers=2):
        with open("api_config.cfg", 'r') as f:
            cfg = f.read()

        config = {}
        for line in cfg.split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip().strip('"')
                print(f"{key.strip()}: {value.strip()}")

        if os.environ.get("OPENAI_API_KEY") is not None:
            print(f"Using OpenAI API. Model: {config['openai_model']}")
            self.api = "openai"
            self.MODEL = config["openai_model"]
        elif os.environ.get("XAI_API_KEY") is not None:
            print("Using XAI API")
            self.api = "xai"
            self.MODEL = config["xai_model"]
        else:
            print("Using Ollama.")
            self.api = "ollama"
            self.MODEL = config["ollama_local_model"]

        self.MAX_MESSAGES = 100
        self.num_workers = num_workers
        self.request_queue = Queue()  # Shared queue for input requests
        self.workers = []

    def on_browser_disconnected(self):
        print("Browser disconnected. Exiting program.")
        sys.exit(0)

    async def start(self):
        async with async_playwright() as playwright:
            if os.environ.get("USER_DATA_DIR") is None:
                print("Please set the USER_DATA_DIR env variable to allow persistent browser use.")

            self.browser = await playwright.firefox.launch_persistent_context(
                user_data_dir=os.environ.get("USER_DATA_DIR"),
                headless=False,
                args=["--ignore-certificate-errors", "--disable-extensions"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36",
                no_viewport=True,
                record_video_dir=os.path.join(os.getcwd(), "videos"),
                permissions=["geolocation"]
            )
            self.browser.on('disconnected', self.on_browser_disconnected)

            if not self.browser.pages:
                await self.browser.new_page()

            for i in range(self.num_workers):
                if i > 0:
                    page = await self.browser.new_page()
                else:
                    page = self.browser.pages[0]

                worker = Worker(
                    page=page,
                    worker_id=i,
                    request_queue=self.request_queue,
                    api=self.api,
                    model=self.MODEL,
                    max_messages=self.MAX_MESSAGES
                )
                self.workers.append(worker)

            running = True
            while running:
                try:
                    active_workers = []
                    for worker in self.workers:
                        if await worker.step():
                            active_workers.append(worker)
                        else:
                            print(f"Worker {worker.worker_id} has quit.")

                    self.workers = active_workers

                    # Process all input requests after workers have stepped
                    while not self.request_queue.empty():
                        try:
                            worker_id = self.request_queue.get_nowait()
                            print(f"\nInput requested by Worker {worker_id}. Enter command (or 'quit' to stop worker):")
                            user_input = input(f"Worker {worker_id}> ")
                            for worker in self.workers:
                                if worker.worker_id == worker_id:
                                    worker.input_queue.put(user_input)
                                    break
                        except queue.Empty:
                            break

                    if not self.workers:
                        print("All workers have quit.")
                        running = False

                    await asyncio.sleep(0.1)  # Small delay to avoid busy-waiting
                except KeyboardInterrupt:
                    print("Shutting down Nyx...")
                    running = False

            await self.browser.close()
