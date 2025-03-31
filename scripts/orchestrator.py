from typing import List, Dict, Any
import json
from openai import AsyncOpenAI

class WorkflowPoint:
    def __init__(self, title: str, tasks: List[str], description: str = ""):
        self.title = title
        self.tasks = tasks
        self.description = description
        self.completed = False
        self.current_task_index = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "tasks": self.tasks,
            "description": self.description,
            "completed": self.completed,
            "current_task_index": self.current_task_index
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowPoint':
        point = cls(data["title"], data["tasks"], data["description"])
        point.completed = data.get("completed", False)
        point.current_task_index = data.get("current_task_index", 0)
        return point

class Workflow:
    def __init__(self, title: str, points: List[WorkflowPoint]):
        self.title = title
        self.points = points
        self.current_point_index = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "points": [point.to_dict() for point in self.points],
            "current_point_index": self.current_point_index
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Workflow':
        points = [WorkflowPoint.from_dict(p) for p in data["points"]]
        workflow = cls(data["title"], points)
        workflow.current_point_index = data.get("current_point_index", 0)
        return workflow

    def get_progress(self) -> Dict[str, Any]:
        total_points = len(self.points)
        completed_points = sum(1 for p in self.points if p.completed)
        current_point = self.points[self.current_point_index]
        total_tasks = len(current_point.tasks)
        current_task = current_point.current_task_index + 1

        return {
            "total_points": total_points,
            "completed_points": completed_points,
            "current_point": self.current_point_index + 1,
            "current_point_title": current_point.title,
            "total_tasks": total_tasks,
            "current_task": current_task,
            "current_task_description": current_point.tasks[current_task - 1],
            "overall_progress": (completed_points / total_points) * 100
        }

class Orchestrator:
    def __init__(self, api_key: str = None, model: str = "gpt-4-turbo-preview"):
        self.client = AsyncOpenAI(api_key=api_key) if api_key else AsyncOpenAI()
        self.model = model
        self.current_workflow = None

    async def create_workflow(self, user_prompt: str) -> Workflow:
        """Create a workflow based on user prompt"""
        system_prompt = """You are an expert workflow orchestrator. Your task is to break down complex tasks into detailed workflows.
        Each workflow should consist of clear, actionable points. Each point should have 4-6 specific tasks.
        
        Format your response as a JSON object with the following structure:
        {
            "title": "Workflow title",
            "points": [
                {
                    "title": "Point title",
                    "description": "Brief description of this workflow point",
                    "tasks": ["Task 1", "Task 2", "Task 3", ...]
                }
            ]
        }
        
        Make each task specific and actionable. Do not include technical implementation details.
        Focus on high-level actions that need to be taken."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )

            workflow_data = json.loads(response.choices[0].message.content)
            points = [WorkflowPoint(**point) for point in workflow_data["points"]]
            self.current_workflow = Workflow(workflow_data["title"], points)
            return self.current_workflow

        except Exception as e:
            raise Exception(f"Failed to create workflow: {str(e)}")

    async def handle_worker_request(self, request: str, context: Dict[str, Any]) -> str:
        """Handle requests from worker when it needs help"""
        system_prompt = """You are an expert workflow orchestrator helping a worker complete tasks.
        The worker has encountered an issue and needs guidance.
        Provide clear, actionable instructions to help the worker proceed.
        If user input is absolutely necessary, start your response with 'USER_INPUT_REQUIRED:'.
        Otherwise, provide alternative approaches or solutions."""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"""
                Current workflow point: {context.get('current_point', 'Unknown')}
                Current task: {context.get('current_task', 'Unknown')}
                Worker request: {request}
                """}
            ]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )

            return response.choices[0].message.content

        except Exception as e:
            raise Exception(f"Failed to handle worker request: {str(e)}")

    def update_progress(self, point_index: int, task_index: int, completed: bool = False):
        """Update workflow progress"""
        if not self.current_workflow:
            return

        point = self.current_workflow.points[point_index]
        point.current_task_index = task_index
        
        if completed:
            point.completed = True
            if point_index < len(self.current_workflow.points) - 1:
                self.current_workflow.current_point_index = point_index + 1

    def get_current_task(self) -> Dict[str, Any]:
        """Get current task details"""
        if not self.current_workflow:
            return None

        point = self.current_workflow.points[self.current_workflow.current_point_index]
        return {
            "point_title": point.title,
            "task": point.tasks[point.current_task_index],
            "progress": self.current_workflow.get_progress()
        } 