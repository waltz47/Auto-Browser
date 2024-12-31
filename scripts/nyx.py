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
    api="openai"
    # MODEL='grok-2-latest'
    # MODEL = "grok-2-vision-1212"
    MODEL="gpt-4o"
    VISION=False #for grok-2-vision
    MAX_MESSAGES=20

    def __init__(self):
        self.messages = [
            {'role':'system','content':'''You are a helpful assistant managing AI agents.

When assigned a task, you'll control an AI agent that scrapes the web for information using HTML elements (via Selenium). Your role involves:

- Breaking down the user's task into smaller, manageable steps for the agent.
- Guiding the agent and correcting any mistakes it makes.
- Ensuring logical reasoning throughout the process.

**User Interaction:**
- Communicate with the user only through the User Input tool. Do not interact directly.
- After completing the task, use the User Input tool to:
  - Ask for user feedback.
  - Provide a summary of the task performed.

**Agent Interaction:**
- When interacting with the agent, assume the role of the user and use first-person perspective.

Start by asking the user for input.'''}
]

    def start(self):
        worker = Worker()
        
        worker.api = self.api
        worker.owner = self
        worker.MODEL = self.MODEL
        worker.MAX_MESSAGES = self.MAX_MESSAGES

        worker.run()