functions = [
    {
        "type": "function",
        "function": {
            "name": "move_to_url",
            "description": "Set a specific URL as the active page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to navigate to.",
                        "example_value": "https://example.com",
                    },
                },
                "required": ["url"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_url_contents",
            "description": "Get the contents from the active page.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_keys_to_element",
            "description": "Send keys to element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xpathSelector": {
                        "type": "string",
                        "description": "The xpath selector for an element.",
                        "example_value": "//a[contains(@href, 'google.x')], //a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google.x')]"
                    },
                    "keys": {
                        "type": "string",
                        "description": "The keys to send to the element.",
                        "example_value": "Hello, World!",
                    }
                },
                "required": ["xpathSelector", "keys"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_submit",
            "description": "Call submit on an element. Usually used on forms after entering the text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xpathSelector": {
                        "type": "string",
                        "description": "The xpath selector for an element.",
                        "example_value": "//a[contains(@href, 'google.x')], //a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google.x')]"
                    }
                },
                "required": ["xpathSelector"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Click element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xpathSelector": {
                        "type": "string",
                        "description": "The xpath selector for an element.",
                        "example_value": "//a[contains(@href, 'google.x')], //a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google.x')]"
                    }
                },
                "required": ["xpathSelector"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "highlight_element",
            "description": "Highlight an element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xpathSelector": {
                        "type": "string",
                        "description": "The xpath selector for an element.",
                        "example_value": "//a[contains(@href, 'google.x')], //a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google.x')]"
                    }
                },
                "required": ["xpathSelector"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_and_click_at_page_position",
            "description": "Moves cursor to a page element and clicks",
            "parameters": {
                "type": "object",
                "properties": {
                    "location_x": {
                        "type": "number",
                        "description": "The X coordinate of the element",
                        "example_value": "56"
                    },
                    "location_y": {
                        "type": "number",
                        "description": "The y coordinate of the element",
                        "example_value": "55"
                    }
                },
                "required": ["location_x", "location_y"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mark_task_complete",
            "description": "Mark the current task as completed successfully.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The ID of the task being completed",
                    },
                    "result": {
                        "type": "string",
                        "description": "Brief description of what was accomplished",
                    }
                },
                "required": ["task_id", "result"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mark_task_failed",
            "description": "Mark the current task as failed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The ID of the task that failed",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why the task failed",
                    }
                },
                "required": ["task_id", "reason"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_task",
            "description": "Get information about the current task being executed.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "display_message",
            "description": "Display a message to the user in the chat. Use this to show results, summaries, or any other information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to display to the user",
                    }
                },
                "required": ["message"],
                "optional": [],
            },
        }
    }
]
