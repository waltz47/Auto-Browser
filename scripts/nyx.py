import time
from defs import *
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
        worker.VISION = self.VISION
        worker.MAX_MESSAGES = self.MAX_MESSAGES

        worker.run()

    def user_input(self):
        user_input = input("User input:")
        return "USER: " + user_input

    def get_system_dir(self, messages):

        tool_dict = {
            "user_input": self.user_input,
        }

        api_key = os.environ.get('XAI_API_KEY')
        if api_key is None:
            print("XAI_API_KEY environment variable not set.")
            sys.exit(1)
        if self.api == "openai":
            client = OpenAI()
        else:
            client = OpenAI(
                api_key=api_key,
                base_url="https://api.x.ai/v1"
            )

        inv_messages = self.messages.copy()
        # for message in messages:
        #     if message["role"] != "system":
        #         inv_messages.append(message)

        #inverted
        for message in messages:
            try:
                if message["role"] == "assistant":
                    inv_messages.append({"role": "user", "content": message["content"]})
                elif message["role"] == "user":
                    if len(message["content"]) > 0:
                        continue #do not append vision elements
                    inv_messages.append({"role": "assistant", "content": message["content"]})
            except:
                pass
            # elif message["role"] == "tool":
            #     inv_messages.append(message)

        user_input_def = [
            {
                "type": "function",
                "function": {
                    "name": "user_input",
                    "description": "Ask the user for input",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "optional": [],
                    },
                }
            }
        ]

        # print(self.messages)
        response = client.chat.completions.create(
            model=self.MODEL,
            messages=inv_messages,
            tools=user_input_def,
            tool_choice="auto"
            
        )
    
        if response.choices[0].message.tool_calls:
            for tool_call in response.choices[0].message.tool_calls:
                # Get the tool function name and arguments Grok wants to call
                function_name = tool_call.function.name
                print(f"Function call: {function_name}")
                function_args = json.loads(tool_call.function.arguments)
                print(f"Function args: {function_args}")
                # Call one of the tool function defined earlier with arguments
                result = tool_dict[function_name](**function_args)
                print(f"Result: {result}")
                
                if function_name == "user_input":
                    # messages.append({'role':'user', 'content': result})
                    return result
                else:
                    messages.append(
                        {
                            "role": "tool",
                            "content": json.dumps(result),
                            "tool_call_id": tool_call.id  # tool_call.id supplied in Grok's response
                        }
                    )
        else:
            if len(response.choices[0].message.content.strip()) > 0:
                # messages.append({'role':'user', 'content': response.choices[0].message.content})
                print(response.choices[0].message.content)
                return response.choices[0].message.content
