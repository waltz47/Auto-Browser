import os
from flask import Flask, render_template, current_app
from flask_socketio import SocketIO, emit
import asyncio
import base64
from io import BytesIO
import time
from threading import Thread, Lock

# Import your Nyx class
from nyx import Nyx

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# Global lock for thread safety with Flask
emit_lock = Lock()

class DashboardNyx(Nyx):
    async def run_worker(self, worker):
        print(f"Starting worker {worker.worker_id}")
        while True:
            try:
                active = await worker.step()
                screenshot = await worker.page.screenshot()
                screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
               
                status = {
                    'worker_id': worker.worker_id,
                    'active': active,
                    'task': worker.current_task if hasattr(worker, 'current_task') else 'Idle',
                    'screenshot': screenshot_b64,
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                }
                print(f"Emitting update for worker {worker.worker_id}: {status['task']}, active={active}")
                
                # Use a thread-safe way to emit
                with emit_lock:
                    socketio.emit('worker_update', status)
               
                if not active:
                    print(f"Worker {worker.worker_id} has quit.")
                    break
                await asyncio.sleep(2) # Reduced to 2 seconds
            except Exception as e:
                print(f"Worker {worker.worker_id} error: {e}")
                break
        return worker.worker_id

@app.route('/')
def index():
    print("Rendering index")
    return render_template('index.html')
