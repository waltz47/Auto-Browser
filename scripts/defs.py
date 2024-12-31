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
            "name": "set_active_element",
            "description": "Set a page element as active.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type_name": {
                        "type": "string",
                        "description": "The type of the element (e.g., 'id', 'class', 'name').",
                        "example_value": "id",
                    },
                    "class_name": {
                        "type": "string",
                        "description": "The class name of the element.",
                        "example_value": "submit-button",
                    },
                },
                "required": ["type_name", "class_name"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_keys_to_active_element",
            "description": "Send keys to the active element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "string",
                        "description": "The keys to send to the active element.",
                        "example_value": "Hello, World!",
                    },
                },
                "required": ["keys"],
                "optional": [],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_submit",
            "description": "Call submit on the active element. Ususally used on forms after entering the text.",
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
            "name": "click_active_element",
            "description": "Click the active element.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "optional": [],
            },
        }
    },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "display_message",
    #         "description": "Displays the message to the user.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "messages": {
    #                     "type": "string",
    #                     "description": "The text to display to the user.",
    #                     "example_value": "Here is the information you asked for....",
    #                 },
    #             },
    #             "required": [],
    #             "optional": [],
    #         },
    #     }
    # }
]