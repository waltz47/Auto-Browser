from typing import List, Dict, Any
import json
from openai import AsyncOpenAI

class Task:
    def __init__(self, title: str, description: str):
        self.title = title
        self.description = description
        self.completed = False
        self.failed = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "completed": self.completed,
            "failed": self.failed
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        task = cls(data["title"], data["description"])
        task.completed = data.get("completed", False)
        task.failed = data.get("failed", False)
        return task

class Workflow:
    def __init__(self, title: str, tasks: List[Task]):
        self.title = title
        self.tasks = tasks
        self.current_task_index = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "tasks": [task.to_dict() for task in self.tasks],
            "current_task_index": self.current_task_index
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Workflow':
        tasks = [Task.from_dict(t) for t in data["tasks"]]
        workflow = cls(data["title"], tasks)
        workflow.current_task_index = data.get("current_task_index", 0)
        return workflow

    def get_progress(self) -> Dict[str, Any]:
        total_tasks = len(self.tasks)
        completed_tasks = sum(1 for t in self.tasks if t.completed)
        failed_tasks = sum(1 for t in self.tasks if t.failed)
        current_task = self.tasks[self.current_task_index]

        # Calculate progress based on completed tasks only
        progress_percentage = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "current_task": self.current_task_index,  # Keep zero-based
            "current_task_title": current_task.title,
            "current_task_description": current_task.description,
            "overall_progress": progress_percentage
        }

    def update_progress(self, task_index: int, completed: bool = False, failed: bool = False):
        """Update task status and move to next task if needed."""
        if 0 <= task_index < len(self.tasks):
            task = self.tasks[task_index]
            if completed:
                task.completed = True
            if failed:
                task.failed = True
            
            # Move to next task if available
            if task_index < len(self.tasks) - 1:
                self.current_task_index = task_index + 1

class Orchestrator:
    def __init__(self, api_key: str = None, model: str = "gpt-4-turbo-preview"):
        self.client = AsyncOpenAI(api_key=api_key) if api_key else AsyncOpenAI()
        self.model = model
        self.current_workflow = None

    async def create_workflow(self, user_prompt: str) -> Workflow:
        """Create a workflow based on user prompt"""
        system_prompt = """You are an expert AI deisnged to split the user request into multiple tasks. 

        - The worker has web browsing capabilities and tools available - focus on the high-level goals.
        - Each task should be clear and goal-oriented.
        
        Format your response as a JSON object with the following structure:
        {
            "title": "Workflow title",
            "tasks": [
                {
                    "title": "Task title",
                    "description": "Detailed description of what needs to be accomplished"
                }
            ]
        }
        Focus on what needs to be accomplished rather than how to do it."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )

            workflow_data = json.loads(response.choices[0].message.content)
            print(f"Workflow data: {workflow_data}")
            tasks = [Task(**task) for task in workflow_data["tasks"]]
            self.current_workflow = Workflow(workflow_data["title"], tasks)
            return self.current_workflow

        except Exception as e:
            raise Exception(f"Failed to create workflow: {str(e)}")

    async def handle_worker_request(self, request: str, context: Dict[str, Any]) -> str:
        """Handle requests from worker when it needs help"""
        system_prompt = """You are an expert workflow orchestrator helping a worker complete tasks.
        The worker has encountered an issue and needs guidance.
        
        - The worker has web browsing capabilities and tools available - focus on alternative approaches to achieve the goals.
        
        Provide clear, actionable instructions to help the worker proceed.
        If user input is absolutely necessary, start your response with 'USER_INPUT_REQUIRED:'.
        Otherwise, suggest alternative approaches to achieve the desired outcome."""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"""
                Current task: {context.get('current_task', 'Unknown')}
                Worker request: {request}
                """}
            ]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3
            )
            print(f"Plan from orchestrator: {response.choices[0].message.content}")
            return response.choices[0].message.content

        except Exception as e:
            raise Exception(f"Failed to handle worker request: {str(e)}")

    def get_current_task(self) -> Dict[str, Any]:
        """Get current task details"""
        if not self.current_workflow:
            return None

        if self.current_workflow.current_task_index >= len(self.current_workflow.tasks):
            return None

        current_task = self.current_workflow.tasks[self.current_workflow.current_task_index]
        return {
            "task_title": current_task.title,
            "task": current_task.description,
            "progress": self.current_workflow.get_progress()
        }

    def update_progress(self, task_index: int, completed: bool = False, failed: bool = False):
        """Update workflow progress"""
        if not self.current_workflow:
            return
        
        # Use the workflow's update_progress method
        self.current_workflow.update_progress(task_index, completed, failed) 