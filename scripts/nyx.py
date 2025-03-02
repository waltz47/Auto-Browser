import os
import sys
import asyncio
from queue import Queue
from playwright.async_api import async_playwright
from worker import Worker
import pygetwindow as gw
import time
import csv
import openai  # Assuming OpenAI API is used for initial input processing
import json
from messages import *
from openai import AsyncOpenAI
import pandas as pd

async def async_input(prompt: str, queue: asyncio.Queue):
    """Asynchronously wait for user input and put it in a queue."""
    loop = asyncio.get_event_loop()
    print(f"Prompting for input: {prompt}")
    user_input = await loop.run_in_executor(None, lambda: input(prompt))
    print(f"Adding to queue for {prompt}: {user_input}")
    await queue.put(user_input)

class Nyx:
    input_list = []

    NYX_PROMPT = """You are an AI designed to create and handle multiple autonomous AI agents. You have the following tools available to you:
    1. create_csv: Create a CSV file that stores the tasks to be done. Usage: create_csv <filename> <task1> <task2> ...
    2. use_csv: Start autonomous agents on the given csv. Usage: use_csv <path to csv>
    
    The tasks should mention that they are to be done via web.
    Perform tasks using the tools based on the input from the user."""

    def __init__(self):
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

        with open("tools.json", 'r') as f:
            self.tools = json.load(f)["tools"]
        self.config = config

    async def handle_initial_input(self, initial_input):
        api_key = os.environ.get('XAI_API_KEY')
        if self.api == "xai" and not api_key:
            print(f"Worker {self.worker_id}: XAI_API_KEY not set.")
            sys.exit(1)
        if self.api == "openai":
            self.client = AsyncOpenAI()
        elif self.api == "xai":
            self.client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
        elif self.api == "ollama":
            self.client = AsyncOpenAI(api_key="____", base_url='http://localhost:11434/v1')

        tools_description = [{"type": "function", "function": tool['function']} for tool in self.tools]
        system_msgs = MessageHistory(self.NYX_PROMPT)
        system_msgs.add_user_text(initial_input)
        response = await self.client.chat.completions.create(
            model=self.MODEL,
            messages=system_msgs.get_messages_for_api(),
            tools=tools_description,
            tool_choice="auto",
            temperature=0.0,
            parallel_tool_calls=False
        )
        content = response.choices[0].message.content
        print(f"System Response: {content}")

        if response.choices[0].message.tool_calls:
            tool_call = response.choices[0].message.tool_calls[0]
            function_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            await self.execute_command(function_name, args)

    async def execute_command(self, function_name, args):
        if function_name == "create_csv":
            self.create_csv(args['filename'], args['tasks'])
        elif function_name == "use_csv":
            self.use_csv(args['filename'])
        else:
            print(f"Unknown command: {function_name}")

    def create_csv(self, filename, tasks):
        filename = os.path.join("input", filename)
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['tasks'])
            for task in tasks:
                writer.writerow([task])
        print(f"CSV file '{filename}' created with tasks: {tasks}")
        self.use_csv(filename)

    def use_csv(self, filename):
        df = pd.read_csv(filename)
        self.input_list = list(df['tasks'])
        print(f"Tasks loaded from CSV file '{filename}': {self.input_list}")

        self.MAX_MESSAGES = 100
        self.num_workers = len(self.input_list)
        self.request_queue = Queue()
        self.workers = []
        self.worker_tasks = {}
        self.input_queues = {}
        print(f"Nyx initialized with {self.num_workers} workers")

    def on_browser_disconnected(self):
        print("Browser disconnected. Exiting program.")
        sys.exit(0)

    async def run_worker(self, worker):
        """Run a worker's step method in a loop until it quits."""
        print(f"Starting worker {worker.worker_id}")
        while True:
            try:
                active = await worker.step()
                print(f"Worker {worker.worker_id} step completed, active: {active}")
                if not active:
                    print(f"Worker {worker.worker_id} has quit.")
                    break
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Worker {worker.worker_id} encountered an error: {e}")
                break
        return worker.worker_id

    async def handle_input_requests(self):
        """Handle input requests from workers asynchronously."""
        print("Starting input request handler")
        while True:
            await asyncio.sleep(0.1)
            while not self.request_queue.empty():
                try:
                    worker_id = self.request_queue.get_nowait()
                    if worker_id in self.input_queues:
                        queue = self.input_queues[worker_id]
                        print(f"Input requested by Worker {worker_id}, queue size before prompt: {queue.qsize()}")
                        user_input = self.input_list.pop(0)
                        print(f"Providing input for Worker {worker_id}: {user_input}")
                        await queue.put(user_input)
                    else:
                        print(f"Warning: Worker {worker_id} not found in input_queues")
                    self.request_queue.task_done()
                except queue.Empty:
                    break

    async def start(self):
        print("Starting Nyx")
        async with async_playwright() as playwright:
            if os.environ.get("USER_DATA_DIR") is None:
                print("Please set the USER_DATA_DIR env variable to allow persistent browser use.")

            self.browser = await playwright.chromium.launch_persistent_context(
                user_data_dir=os.environ.get("USER_DATA_DIR"),
                headless=False,
                args=["--ignore-certificate-errors", "--disable-extensions"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36",
                no_viewport=True,
                # record_video_dir=os.path.join(os.getcwd(), "videos"),
                permissions=["geolocation"]
            )
            self.browser.on('disconnected', self.on_browser_disconnected)
            print("Browser launched")

            if not self.browser.pages:
                await self.browser.new_page()

            # screen_width = 1920  # Todo: This needs to be fixed
            # screen_height = 1080  
            # rows, cols = 3,3
            # window_width = screen_width // cols
            # window_height = screen_height // rows

            # Launch pages and set viewports
            for i in range(self.num_workers):
                if i > 0:
                    page = await self.browser.new_page()
                else:
                    page = self.browser.pages[0]

                # Set viewport size
                # await page.set_viewport_size({"width": window_width, "height": window_height})
                # print(f"Worker {i} viewport set to {window_width}x{window_height}")

                worker = Worker(
                    page=page,
                    worker_id=i,
                    request_queue=self.request_queue,
                    api=self.api,
                    model=self.MODEL,
                    max_messages=self.MAX_MESSAGES
                )
                worker.enable_vision = self.config["enable_vision"]
                self.workers.append(worker)
                self.input_queues[i] = asyncio.Queue()
                worker.input_queue = self.input_queues[i]
                print(f"Worker {i} initialized")

            # Wait briefly for all pages to open before positioning
            # await asyncio.sleep(2)

            # Position windows in a grid using pygetwindow
            # firefox_windows = gw.getWindowsWithTitle("Chromium")  # Todo: This needs to be changed
            # if len(firefox_windows) >= self.num_workers:
            #     for i, win in enumerate(firefox_windows[:self.num_workers]):
            #         row = i // cols
            #         col = i % cols
            #         x = col * window_width
            #         y = row * window_height
            #         win.moveTo(x, y)
            #         win.resizeTo(window_width + 10, window_height + 50)  # Extra height for browser UI
            #         print(f"Positioned window {i} at ({x}, {y})")
            # else:
            #     print(f"Warning: Found {len(firefox_windows)} Firefox windows, expected {self.num_workers}")

            # Start worker tasks
            for worker in self.workers:
                task = asyncio.create_task(self.run_worker(worker))
                self.worker_tasks[worker.worker_id] = task
                print(f"Task created for Worker {worker.worker_id}")
                await asyncio.sleep(0)

            # Start input handler
            input_task = asyncio.create_task(self.handle_input_requests())
            print("Input handler task created")

            # Wait for all worker tasks to complete
            try:
                done, pending = await asyncio.wait(
                    [task for task in self.worker_tasks.values()],
                    return_when=asyncio.ALL_COMPLETED
                )
                for worker_id, task in self.worker_tasks.items():
                    if task in done:
                        print(f"Worker {worker_id} task completed.")
                input_task.cancel()
            except asyncio.CancelledError:
                print("Nyx shutting down...")
                for task in self.worker_tasks.values():
                    task.cancel()
                input_task.cancel()

            await self.browser.close()
            print("Browser closed")