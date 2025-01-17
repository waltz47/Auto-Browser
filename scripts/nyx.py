import time
from tools import *
from openai import OpenAI
import json
import base64
import sys
import os
import worker
from worker import *

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
            self.MODEL = "llama3.2:latest"

        self.MAX_MESSAGES = 100

    def start(self):
        worker = Worker()
        
        worker.api = self.api
        worker.owner = self
        worker.MODEL = self.MODEL
        worker.MAX_MESSAGES = self.MAX_MESSAGES

        worker.run()