import json


def save_docs_to_jsonl(docs, file_path):
    """Save list of {text, metadata} dicts to JSONL."""
    with open(file_path, "w") as f:
        for doc in docs:
            f.write(json.dumps(doc) + "\n")


def load_docs_from_jsonl(file_path):
    """Load list of {text, metadata} dicts from JSONL."""
    docs = []
    with open(file_path, "r") as f:
        for line in f:
            docs.append(json.loads(line))
    return docs
