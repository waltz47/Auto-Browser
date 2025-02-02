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
            print("Using Ollama. ")
            self.api = "ollama"
            self.MODEL = config["ollama_local_model"]

        self.MAX_MESSAGES = 100
        
    def on_browser_disconnected(self):
        print("Browser disconnected. Exiting program.")
        sys.exit(0)

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
            no_viewport=True,
            # viewport={"width": 1320, "height": 768},
            record_video_dir=os.path.join(os.getcwd(), "videos"),
            # record_video_size={"width": 1320, "height": 768}, #fix this
            permissions=["geolocation"]
        ) 
        self.browser.on('disconnected', self.on_browser_disconnected)

        try:
            worker.page = self.browser.pages[0]
        except:
            worker.page = self.browser.new_page()

        worker.browser = self.browser
        worker.playwright = self.playwright
        
        worker.api = self.api
        worker.owner = self
        worker.MODEL = self.MODEL
        worker.MAX_MESSAGES = self.MAX_MESSAGES

        worker.run()