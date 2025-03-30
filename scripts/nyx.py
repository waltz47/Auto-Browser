import os
import asyncio
from playwright.async_api import async_playwright
from worker import Worker
import json
from openai import AsyncOpenAI
from fastapi import FastAPI, WebSocket, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path
import numpy as np
from PIL import Image
import io
from pydantic import BaseModel
import weakref

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
        
        # Initialize video streaming attributes
        self.video_track = None
        self.pc = None
        self.stream_task = None
        
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
        from fastapi import Body
        from pydantic import BaseModel
        
        class RTCOffer(BaseModel):
            sdp: str
            type: str

        # Mount static files
        self.app.mount("/static", StaticFiles(directory="static"), name="static")

        # Setup routes
        @self.app.get("/")
        async def get():
            template_path = Path("templates/dashboard.html")
            if not template_path.exists():
                return HTMLResponse("Error: Dashboard template not found. Please ensure dashboard.html exists in the templates directory.")
            return HTMLResponse(template_path.read_text())

        @self.app.post("/offer")
        async def offer(params: RTCOffer):
            from aiortc import RTCPeerConnection, RTCSessionDescription
            import json

            offer = RTCSessionDescription(
                sdp=params.sdp,
                type=params.type
            )

            pc = RTCPeerConnection()
            self.pc = pc  # Store reference to peer connection

            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                if pc.connectionState == "failed":
                    await pc.close()
                    self.pc = None

            # Create and add video track
            if not self.video_track:
                self.video_track = await self.create_video_track()
            pc.addTrack(self.video_track)

            # Handle the offer
            await pc.setRemoteDescription(offer)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

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
                headless=True,  # Run in headless mode
                args=[
                    "--ignore-certificate-errors",
                    "--disable-extensions",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36",
                viewport={"width": 1280, "height": 720},  # Fixed viewport for consistent streaming
                permissions=["geolocation"],
            )
            
            self.page = await self.context.new_page()
            await self.page.goto("about:blank")  # Navigate to a blank page to ensure page is ready

    async def get_video_frame(self):
        """Capture current page as video frame."""
        if self.page:
            screenshot = await self.page.screenshot(type='jpeg', quality=80)
            return screenshot
        return None

    async def create_video_track(self):
        """Create a VideoStreamTrack from browser page."""
        from aiortc.mediastreams import MediaStreamTrack
        import av
        import fractions
        import asyncio
        import numpy as np
        from PIL import Image
        import io
        import weakref
        
        class BrowserVideoStreamTrack(MediaStreamTrack):
            kind = "video"

            def __init__(self, nyx_instance):
                super().__init__()
                self.nyx = weakref.ref(nyx_instance)  # Weak reference to avoid circular reference
                self._frame_count = 0
                self._stopped = False

            async def recv(self):
                if self._stopped:
                    return None

                try:
                    nyx = self.nyx()
                    if nyx is None or nyx.page is None:
                        raise ValueError("Page is not available")

                    screenshot = await nyx.page.screenshot(type='jpeg', quality=80)
                    if screenshot is None:
                        raise ValueError("Failed to capture screenshot")

                    # Convert screenshot to numpy array
                    image = Image.open(io.BytesIO(screenshot))
                    frame_data = np.array(image)
                    
                    # Create video frame
                    frame = av.VideoFrame.from_ndarray(frame_data, format='rgb24')
                    frame.pts = self._frame_count
                    frame.time_base = fractions.Fraction(1, 30)  # 30 fps
                    self._frame_count += 1
                    return frame

                except Exception as e:
                    print(f"Error capturing frame: {e}")
                    # Return a blank frame on error
                    blank_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                    frame = av.VideoFrame.from_ndarray(blank_frame, format='rgb24')
                    frame.pts = self._frame_count
                    frame.time_base = fractions.Fraction(1, 30)
                    self._frame_count += 1
                    return frame

            async def stop(self):
                self._stopped = True
                await super().stop()

        # Create and return the video track
        return BrowserVideoStreamTrack(self)

    async def create_worker(self, websocket=None) -> Worker:
        """Create and initialize a single worker."""
        if not self.worker:
            # Convert string 'true'/'false' to boolean
            enable_vision = self.config.get("enable_vision", "false").lower() == "true"
            
            self.worker = Worker(
                page=self.page,
                worker_id=0,
                request_queue=None,
                api=self.api,
                model=self.MODEL,
                max_messages=100,
                tools=self.tools,
                websocket=websocket,
                enable_vision=enable_vision  # Pass the vision flag
            )
            await self.worker.setup_client()
        else:
            self.worker.websocket = websocket
        return self.worker

    async def handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection."""
        await websocket.accept()
        connection_open = True
        
        try:
            # Initialize browser if needed
            if not self.page:
                await self.setup_browser()

            # Initialize or update worker
            worker = await self.create_worker(websocket)
            print("\n=== Nyx AI Initialized ===")
            print("Worker initialized and ready!")
            await websocket.send_text("Nyx AI is ready. Enter your task below.\n")

            while connection_open:
                try:
                    # Get message from websocket
                    data = await websocket.receive_text()
                    await websocket.send_text(f"\nUser: {data}\n")
                    print(f"\n=== User Input ===\n{data}")
                    
                    # Add user input to message history
                    worker.messages.add_user_text(data)
                    
                    # Process the task - continue until we need user input
                    while True:
                        active = await worker.step()
                        if not active:
                            print("\n=== Ready for Next Input ===")
                            break

                except RuntimeError as e:
                    if "Connection closed" in str(e):
                        connection_open = False
                        break
                    raise

        except Exception as e:
            error_msg = f"\n=== Error ===\n{str(e)}"
            print(error_msg)
            if connection_open:
                try:
                    await websocket.send_text("An error occurred. Please try again.")
                except:
                    pass
        finally:
            if self.worker:
                self.worker.websocket = None

    async def cleanup(self):
        """Clean up resources."""
        if self.pc:
            await self.pc.close()
            self.pc = None
        if self.video_track:
            await self.video_track.stop()
            self.video_track = None
        if self.page:
            await self.page.close()
            self.page = None
        if self.context:
            await self.context.close()
            self.context = None
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

    def run_dashboard(self, host="0.0.0.0", port=8000):
        """Run the web dashboard."""
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)

if __name__ == "__main__":
    nyx = Nyx()
    nyx.run_dashboard()