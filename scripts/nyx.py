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
    VISION=False #for grok-2-vision

    def __init__(self):
        self.api = "openai"
        # self.MODEL="llama3.1:latest"
        self.MODEL="gpt-4o"
        self.MAX_MESSAGES = 25

    def start(self):
        worker = Worker()
        
        worker.api = self.api
        worker.owner = self
        worker.MODEL = self.MODEL
        worker.MAX_MESSAGES = self.MAX_MESSAGES

        worker.run()