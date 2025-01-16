import base64
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union
from pathlib import Path

@dataclass
class Message:
    """
    A class to handle different types of messages including text, images, and tool calls.
    Provides operators and methods to convert messages into different formats.
    """
    role: str
    content: Union[str, List[Dict[str, Any]], Dict[str, Any]]
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    
    @staticmethod
    def create_text(role: str, text: str) -> 'Message':
        """Create a simple text message."""
        return Message(role=role, content=text)
    
    @staticmethod
    def create_with_image(role: str, text: str, image_path: Union[str, Path], detail: str = "high") -> 'Message':
        """Create a message with both text and image content."""
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
            
        with open(image_path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode('utf-8')
            
        content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{encoded}",
                    "detail": detail
                }
            },
            {
                "type": "text",
                "text": text
            }
        ]
        return Message(role=role, content=content)
    
    @staticmethod
    def create_tool_call(role: str, tool_id: str, function_name: str, arguments: str) -> 'Message':
        """Create a tool call message."""
        return Message(
            role=role,
            content=None,  # Content should be None for tool calls
            tool_calls=[{
                'id': tool_id,
                'function': {
                    'arguments': arguments,
                    'name': function_name
                },
                'type': 'function'
            }]
        )
    
    @staticmethod
    def create_tool_response(tool_id: str, result: str, name: str) -> 'Message':
        """Create a tool response message."""
        return Message(
            role="tool",
            content=result,
            tool_call_id=tool_id,
            name=name #for ollama tool calling
        )
    
    def __str__(self) -> str:
        """Convert message to string format, extracting only the text content."""
        if isinstance(self.content, str):
            return self.content
        elif isinstance(self.content, list):
            # Extract text from content list
            text_contents = [
                item["text"] 
                for item in self.content 
                if item["type"] == "text"
            ]
            return " ".join(text_contents)
        return ""
    
    def __repr__(self) -> str:
        """Detailed representation of the message including role and type."""
        msg_type = "text" if isinstance(self.content, str) else (
            "image+text" if isinstance(self.content, list) else "tool"
        )
        return f"Message(role='{self.role}', type='{msg_type}', content='{str(self)}')"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary format for API calls."""
        message_dict = {"role": self.role}
        
        if self.content is not None:
            message_dict["content"] = self.content
            
        if self.tool_call_id:
            message_dict["tool_call_id"] = self.tool_call_id
            message_dict["name"] = self.name
        if self.tool_calls:
            message_dict["tool_calls"] = self.tool_calls
            
        return message_dict
    
    def has_image(self) -> bool:
        """Check if the message contains an image."""
        if isinstance(self.content, list):
            return any(
                item.get("type") == "image_url" 
                for item in self.content
            )
        return False
    
    def has_tool_calls(self) -> bool:
        """Check if the message contains tool calls."""
        return bool(self.tool_calls)
    
    def get_tool_calls(self) -> List[Dict[str, Any]]:
        """Get tool calls if they exist, otherwise return empty list."""
        return self.tool_calls or []
    
    def get_text(self) -> str:
        """Get only the text content of the message."""
        return str(self)
    
    def get_images(self) -> List[Dict[str, Any]]:
        """Get list of images in the message."""
        if isinstance(self.content, list):
            return [
                item["image_url"] 
                for item in self.content 
                if item["type"] == "image_url"
            ]
        return []

class MessageHistory:
    """
    A class to manage a collection of messages with convenient methods
    for adding and retrieving messages in different formats.
    """
    def __init__(self, system_prompt: str):
        self.messages: List[Message] = [
            Message.create_text("system", system_prompt)
        ]
        
    def add_message(self, message: Message) -> None:
        """Add a message to the history."""
        self.messages.append(message)
        
    def add_user_text(self, text: str) -> None:
        """Add a user text message."""
        self.add_message(Message.create_text("user", text))
        
    def add_user_with_image(self, text: str, image_path: Union[str, Path]) -> None:
        """Add a user message with both text and image."""
        self.add_message(Message.create_with_image("user", text, image_path))
        
    def add_assistant_text(self, text: str) -> None:
        """Add an assistant text message."""
        self.add_message(Message.create_text("assistant", text))
        
    def add_tool_call(self, tool_id: str, function_name: str, arguments: str) -> None:
        """Add a tool call message."""
        self.add_message(Message.create_tool_call("assistant", tool_id, function_name, arguments))
        
    def add_tool_response(self, tool_id: str, result: str, name: str) -> None:
        """Add a tool response message."""
        self.add_message(Message.create_tool_response(tool_id, result, name))
        
    def get_messages_for_api(self) -> List[Dict[str, Any]]:
        """Get messages in format suitable for API calls."""
        return [msg.to_dict() for msg in self.messages]
        
    def trim_history(self, max_messages: int) -> None:
        """Trim message history to keep only recent messages if exceeding max length,
        preserving only the last occurrence of special JSON markers."""
        import re
        
        # Find all messages containing JSON markers
        json_messages = []
        for i, msg in enumerate(self.messages):
            if isinstance(msg.content, str) and "PAGE JSON" in msg.content:
                json_messages.append(i)
        
        # Replace content in all but the last 2 occurrences
        if len(json_messages) > 4:
            for i in json_messages[:-4]:
                print("Converting to Stale")
                self.messages[i].content = "Stale page summary"

        # Truncate history if it exceeds max_messages
        if len(self.messages) > max_messages + 2:
            # Keep system message (index 0) and last max_messages
            self.messages = [self.messages[0]] + self.messages[-max_messages:]

        # print(self.messages)

            
    def __len__(self) -> int:
        """Get number of messages in history."""
        return len(self.messages)
    
    def __getitem__(self, index: int) -> Message:
        """Get message at specific index."""
        return self.messages[index]
    
    def __iter__(self):
        """Iterate over messages."""
        return iter(self.messages)