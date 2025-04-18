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
        
        # Track active WebSocket connection
        self._active_websocket = None

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
            # Check if we already have an active connection
            if self._active_websocket is not None:
                try:
                    await websocket.accept()
                    # Send a special message to trigger page refresh on the client side
                    await websocket.send_text("__REFRESH_PAGE__")
                    await websocket.close(code=1000, reason="Another connection is already active")
                except:
                    pass
                return

            await websocket.accept()
            self._active_websocket = websocket
            
            try:
                # Initialize browser if needed
                if not self.page:
                    await self.setup_browser()

                # Initialize or update worker (this will now also send the ready message)
                worker = await self.create_worker(websocket)
                
                while True:
                    try:
                        # Get message from websocket
                        data = await websocket.receive_text()
                        
                        try:
                            await websocket.send_text(f"\nUser: {data}\n")
                            print(f"\n=== User Input ===\n{data}")
                            
                            # Process the task with planning
                            active = await worker.process_user_input(data)
                            if active:
                                # Process the planned steps
                                while True:
                                    active = await worker.step()
                                    if not active:
                                        print("\n=== Ready for Next Input ===")
                                        break

                        except RuntimeError as e:
                            if "Connection closed" in str(e):
                                break
                            raise

                    except RuntimeError as e:
                        if "Connection closed" in str(e):
                            break
                        raise
                    except Exception as e:
                        error_msg = f"Error processing message: {str(e)}"
                        print(f"\n=== Error ===\n{error_msg}")
                        try:
                            await websocket.send_text(f"\nAn error occurred: {error_msg}")
                        except:
                            pass
                        break

            except Exception as e:
                error_msg = f"WebSocket error: {str(e)}"
                print(f"\n=== Error ===\n{error_msg}")
            finally:
                # Clean up worker reference and active websocket
                if self.worker:
                    self.worker.websocket = None
                if self._active_websocket == websocket:
                    self._active_websocket = None
                print("WebSocket connection closed")

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
                    "--window-size=1920,1080"  # Set window size
                ]
            )
            
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},  # Increased viewport size to 1080p
                screen={"width": 1920, "height": 1080},  # Match screen size with viewport
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
        """Create or update worker instance and ensure ready message is sent."""
        if not self.worker:
            self.worker = Worker(
                page=self.page,
                worker_id=1,
                request_queue=None,
                api=self.api,
                model=self.MODEL,
                max_messages=10,
                websocket=websocket, # Assign websocket during creation
                enable_vision=True
            )
            # Initialize the worker (sets up API client, etc.)
            await self.worker.initialize()
        else:
            # Update websocket for existing worker
            self.worker.websocket = websocket
            
        # Send ready message using the worker's assigned websocket
        print(f"[Nyx] Attempting to send ready message via websocket {id(self.worker.websocket)}")
        await asyncio.sleep(0.1) # Add a small delay (100ms)
        try:
            await self.worker.send_to_websocket("\nAuto Browser is ready. Enter your task below.")
            print("[Nyx] Sent ready message successfully.")
        except Exception as e:
            print(f"[Nyx] Error sending ready message: {e}")
            
        return self.worker

    async def handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection."""
        # Check if we already have an active connection
        if self._active_websocket is not None:
            try:
                await websocket.close(code=1000, reason="Another connection is already active")
            except:
                pass
            return

        await websocket.accept()
        self._active_websocket = websocket
        
        try:
            # Initialize browser if needed
            if not self.page:
                await self.setup_browser()

            # Initialize or update worker
            worker = await self.create_worker(websocket)
            
            try:
                print("\n=== Nyx AI Initialized ===")
                print("Worker initialized and ready!")
            except RuntimeError:
                return

            while True:
                try:
                    # Get message from websocket
                    data = await websocket.receive_text()
                    
                    try:
                        await websocket.send_text(f"\nUser: {data}\n")
                        print(f"\n=== User Input ===\n{data}")
                        
                        # Process the task with planning
                        active = await worker.process_user_input(data)
                        if active:
                            # Process the planned steps
                            while True:
                                active = await worker.step()
                                if not active:
                                    print("\n=== Ready for Next Input ===")
                                    break

                    except RuntimeError as e:
                        if "Connection closed" in str(e):
                            break
                        raise

                except RuntimeError as e:
                    if "Connection closed" in str(e):
                        break
                    raise
                except Exception as e:
                    error_msg = f"Error processing message: {str(e)}"
                    print(f"\n=== Error ===\n{error_msg}")
                    try:
                        await websocket.send_text(f"\nAn error occurred: {error_msg}")
                    except:
                        pass
                    break

        except Exception as e:
            error_msg = f"WebSocket error: {str(e)}"
            print(f"\n=== Error ===\n{error_msg}")
        finally:
            # Clean up worker reference and active websocket
            if self.worker:
                self.worker.websocket = None
            if self._active_websocket == websocket:
                self._active_websocket = None
            print("WebSocket connection closed")

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
