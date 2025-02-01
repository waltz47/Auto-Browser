import time
from tools import *
from openai import OpenAI
import json
import base64
import sys
import os
import worker
from worker import *
from playwright.sync_api import sync_playwright, Page, ElementHandle
from playwright.sync_api import Page

"""
Class to handle workers via swarm
"""

class Nyx:    

    def __init__(self):
        if os.environ.get("OPENAI_API_KEY") is not None:
            print("Using OpenAI API")
            self.api = "openai"
            self.MODEL = "gpt-4o"
        elif os.environ.get("XAI_API_KEY") is not None:
            print("Using XAI API")
            self.api = "xai"
            self.MODEL = "grok-2-beta"
        else:
            print("Using Ollama. ")
            self.api = "ollama"
            self.MODEL = "qwen2.5-coder:latest"

        self.MAX_MESSAGES = 100

    def start(self):
        worker = Worker()

        self.playwright = sync_playwright().start()
        if os.environ.get("USER_DATA_DIR") is None:
            print(f"Please set the USER_DATA_DIR env variable to allow persistent browser use.")

        self.browser = self.playwright.firefox.launch_persistent_context(
            user_data_dir=os.environ.get("USER_DATA_DIR"), 
            headless=False,
            args=["--ignore-certificate-errors", "--disable-extensions"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36",
            no_viewport=False,
            viewport={"width": 1920, "height": 1080},
            record_video_dir=os.path.join(os.getcwd(), "videos"),
            record_video_size={"width": 1920, "height": 1080},
            permissions=["geolocation"]
        ) 

        try:
            worker.page = self.browser.pages[0]
        except:
            worker.page = self.browser.new_page()
        
        worker.api = self.api
        worker.owner = self
        worker.MODEL = self.MODEL
        worker.MAX_MESSAGES = self.MAX_MESSAGES

        worker.run()