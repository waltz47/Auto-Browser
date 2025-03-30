import json
from typing import List, Dict, Any
from openai import AsyncOpenAI

class Planner:
    def __init__(self, api: str, model: str):
        """Initialize the planner with API configuration."""
        self.api = api
        self.model = model
        self.client = None

    async def setup_client(self):
        """Set up the OpenAI client based on API configuration."""
        if self.client is not None:
            return
            
        if self.api == "openai":
            self.client = AsyncOpenAI()
        elif self.api == "xai":
            api_key = os.environ.get('XAI_API_KEY')
            if not api_key:
                raise ValueError("XAI_API_KEY not set")
            self.client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
        elif self.api == "ollama":
            self.client = AsyncOpenAI(api_key="____", base_url='http://localhost:11434/v1')
        else:
            raise ValueError(f"Unsupported API type: {self.api}")

    async def plan_task(self, user_input: str) -> List[str]:
        """Break down a user task into detailed steps."""
        if not self.client:
            await self.setup_client()

        system_prompt = """You are a task planner that converts user requests into clear instructions.
Present each task from the user's perspective, as if they are giving instructions to an assistant.
Focus on the 'what' rather than the 'how' - don't include specific implementation details.

Example input: "analyze tesla stock and recent news"
Example output:
Search for Tesla's current stock performance on Yahoo Finance and review their recent news coverage. Give me a comprehensive overview of their current market situation.

Example input: "find me cheap flights to new york"
Example output:
Search major travel sites for available flights to New York. Find the best deals and compare prices across different airlines and dates.

Keep responses brief and focused on the overall goal. Write in an instructional tone, as if the user is giving the command. Avoid technical details or specific steps."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.7,
                stream=False
            )

            # Return the complete instruction
            return [response.choices[0].message.content.strip()]

        except Exception as e:
            print(f"Error in planning task: {e}")
            return [user_input]  # Return original input as a single instruction if planning fails 