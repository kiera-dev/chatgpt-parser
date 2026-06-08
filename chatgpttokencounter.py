import json
import glob
import tiktoken

encoding = tiktoken.encoding_for_model("gpt-4o")

total_tokens = 0

json_files = glob.glob("*.json")

for filename in json_files:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        text_blob = json.dumps(data)

        tokens = len(encoding.encode(text_blob))

        print(f"{filename}: {tokens:,} tokens")

        total_tokens += tokens

    except Exception as e:
        print(f"Error with {filename}: {e}")

print("\n======================")
print(f"TOTAL TOKENS: {total_tokens:,}")