#!/usr/bin/env python3
"""
Token counter for instruction-analyzer skill.
Usage: python3 token_counter.py file1.md file2.md ...
Output: JSON object mapping file paths to token counts.
"""
import json
import sys


def count_tokens(file_paths: list[str]) -> dict:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
    except ImportError:
        return {"error": "tiktoken not installed. Run: pip install tiktoken"}

    results = {}
    for path in file_paths:
        try:
            text = open(path, encoding="utf-8").read()
            results[path] = len(enc.encode(text))
        except FileNotFoundError:
            results[path] = {"error": f"file not found: {path}"}
        except Exception as e:
            results[path] = {"error": str(e)}

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "no files provided"}))
        sys.exit(1)

    result = count_tokens(sys.argv[1:])
    print(json.dumps(result, ensure_ascii=False, indent=2))
