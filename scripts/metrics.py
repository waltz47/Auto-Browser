import tiktoken

def avg_tokens(text, model="o200k_base"):
    # Choose the appropriate encoding for your model. Here, we use the default for gpt-3.5-turbo.
    encoding = tiktoken.get_encoding(model)
    return len(encoding.encode(text))
