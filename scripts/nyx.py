import os
import asyncio
from playwright.async_api import async_playwright
from worker import Worker
import json
from openai import AsyncOpenAI
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path

class Nyx:
    def __init__(self):
        """Initialize Nyx with basic configuration."""
        # Create required directories
        self._create_required_directories()

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

        self.tools = None #worker can initialize directly
        # Initialize FastAPI app
        self.app = FastAPI()
        self.setup_routes()

        # Initialize Playwright resources
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.worker = None

    def _create_required_directories(self):
        """Create required directories if they don't exist."""
        required_dirs = ['static', 'templates']
        for dir_name in required_dirs:
            dir_path = Path(dir_name)
            if not dir_path.exists():
                dir_path.mkdir(parents=True)
                print(f"Created directory: {dir_path}")
        
        # Check if dashboard template exists
        template_path = Path("templates/dashboard.html")
        if not template_path.exists():
            print(f"Warning: Dashboard template not found at {template_path}")
            print("Please ensure dashboard.html exists in the templates directory")

    def setup_routes(self):
        """Set up FastAPI routes."""
        # Mount static files
        self.app.mount("/static", StaticFiles(directory="static"), name="static")

        # Setup routes
        @self.app.get("/")
        async def get():
            template_path = Path("templates/dashboard.html")
            if not template_path.exists():
                return HTMLResponse("Error: Dashboard template not found. Please ensure dashboard.html exists in the templates directory.")
            return HTMLResponse(template_path.read_text())

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.handle_websocket(websocket)

        @self.app.on_event("shutdown")
        async def shutdown_event():
            await self.cleanup()

    async def setup_browser(self):
        """Initialize browser and create a page."""
        if not self.playwright:
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

    async def create_worker(self, websocket=None) -> Worker:
        """Create and initialize a single worker."""
        if not self.worker:
            self.worker = Worker(
                page=self.page,
                worker_id=0,
                request_queue=None,
                api=self.api,
                model=self.MODEL,
                max_messages=100,
                tools=self.tools,
                websocket=websocket
            )
            await self.worker.setup_client()
        else:
            self.worker.websocket = websocket
        return self.worker

    async def handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection."""
        await websocket.accept()
        
        try:
            # Initialize browser if needed
            if not self.page:
                await self.setup_browser()

            # Initialize or update worker
            worker = await self.create_worker(websocket)
            await websocket.send_text("\n=== Nyx AI Initialized ===")
            await websocket.send_text("Worker initialized and ready!")
            await websocket.send_text("Enter your task below.\n")

            while True:
                # Get message from websocket
                data = await websocket.receive_text()
                await websocket.send_text(f"\n=== User Input ===\n{data}\n")
                
                # Add user input to message history
                worker.messages.add_user_text(data)
                
                # Process the task - continue until we need user input
                while True:
                    active = await worker.step()
                    if not active:
                        await websocket.send_text("\n=== Ready for Next Input ===\n")
                        break

        except Exception as e:
            await websocket.send_text(f"\n=== Error ===\n{str(e)}")
        finally:
            if websocket.client_state.CONNECTED:
                await websocket.close()
            if self.worker:
                self.worker.websocket = None

    async def cleanup(self):
        """Clean up resources."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    def run_dashboard(self, host="0.0.0.0", port=8000):
        """Run the web dashboard."""
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)

if __name__ == "__main__":
    nyx = Nyx()
    nyx.run_dashboard()