import json
import asyncio
import subprocess
from pathlib import Path
import sys

PROMPT_TEMPLATE = """You are an expert French proofreader. Modernize the spelling and grammar of the following 18th-century French text blocks.
Make contextual corrections for archaic words or OCR outliers (e.g., "assez constans" -> "assez constants", "défert" -> "désert", "cy-devant" -> "ci-devant", "arrosez et cultivez" -> "arrosés et cultivés", "enfans" -> "enfants").
DO NOT change the meaning. 

You MUST output ONLY a valid JSON array of strings containing the exact modernized strings in the exact same order as the input array. DO NOT wrap it in markdown block quotes. Just the raw JSON array.

INPUT:
{input_json}"""

async def run_agy_batch(text_batch, semaphore):
    if not text_batch:
        return text_batch
    
    input_json = json.dumps(text_batch, ensure_ascii=False, indent=2)
    prompt = PROMPT_TEMPLATE.format(input_json=input_json)
    
    async with semaphore:
        if BACKEND == "claude":
            # Prompt via stdin; no tools, no MCP.
            process = await asyncio.create_subprocess_exec(
                'claude', '-p', '--model', CLAUDE_MODEL, '--tools', '',
                '--strict-mcp-config', '--disable-slash-commands',
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate(prompt.encode('utf-8'))
        else:
            process = await asyncio.create_subprocess_exec(
                'agy', '-p', prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            result = stdout.decode('utf-8').strip()
            # Failsafe if the LLM adds markdown or quotes
            if result.startswith("```"):
                lines = result.split("\n")
                if len(lines) > 2:
                    result = "\n".join(lines[1:-1]).strip()
            if result.startswith("json"):
                result = result[4:].strip()
                
            try:
                output_batch = json.loads(result)
                if isinstance(output_batch, list) and len(output_batch) == len(text_batch):
                    return output_batch
                else:
                    raise Exception(f"Output array length ({len(output_batch if isinstance(output_batch, list) else 0)}) does not match input ({len(text_batch)})")
            except json.JSONDecodeError as e:
                raise Exception(f"Error parsing JSON from agy: {e}\nRaw Output: {result[:200]}...")
        else:
            raise Exception(f"Error calling {BACKEND}: {(stderr or stdout).decode('utf-8')[:200]}")

import hashlib
import os

# LLM_BACKEND=claude uses Claude Code instead of agy (e.g. when agy quota is exhausted).
BACKEND = os.environ.get("LLM_BACKEND", "agy")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "sonnet")
MAX_BATCHES = int(os.environ.get("MAX_BATCHES", "0"))  # 0 = all; small value for a trial run

from paths import DATA, LLM_CACHE as CACHE_FILE
def load_cache():
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def get_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

async def main():
    if len(sys.argv) < 2:
        print("Usage: python llm_modernize.py <book_folder>")
        sys.exit(1)
        
    folder_name = sys.argv[1]
    folder = DATA / folder_name / "normalized"
    files = list(folder.glob("page_[0-9][0-9][0-9][0-9].json"))
    
    semaphore = asyncio.Semaphore(10)
    cache = load_cache()
    
    print(f"Loading {len(files)} files into memory...")
    
    file_data_map = {}
    pointers = [] # stores (data_dict, key, original_text, hash)
    
    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            file_data_map[file_path] = data
            
        # Helper to check cache
        def add_pointer(item, key):
            text = item.get(key)
            if not text or not text.strip():
                return
            h = get_hash(text)
            if h in cache:
                item[key] = cache[h] # Apply cached version immediately
            elif text in cache.values():
                pass # Already perfectly modernized, nothing to do
            else:
                pointers.append((item, key, text, h))
                
        # Summary
        if data.get("chapter_summary"):
            add_pointer(data, "chapter_summary")
            
        # Verses
        if "verses" in data:
            for verse in data["verses"]:
                add_pointer(verse, "french")
                
        # Commentary
        if "commentary" in data:
            for comm in data["commentary"]:
                add_pointer(comm, "french_translation")
                add_pointer(comm, "french_commentary")

    print(f"Found {len(pointers)} distinct text blocks needing LLM. Grouping into batches of 30...")
    
    BATCH_SIZE = 30
    batches = []
    for i in range(0, len(pointers), BATCH_SIZE):
        batch_pointers = pointers[i:i+BATCH_SIZE]
        batch_texts = [p[2] for p in batch_pointers]
        batches.append((batch_pointers, batch_texts))
    if MAX_BATCHES:
        batches = batches[:MAX_BATCHES]

    print(f"Total batches to process: {len(batches)}")
    
    async def process_batch(batch_pointers, batch_texts, idx):
        print(f"Sending batch {idx}/{len(batches)}...")
        try:
            modernized_texts = await run_agy_batch(batch_texts, semaphore)
            # apply and cache
            for j, (parent, key, orig, h) in enumerate(batch_pointers):
                parent[key] = modernized_texts[j]
                # only cache if it changed or actually processed properly
                if modernized_texts[j] != orig and not modernized_texts[j].startswith("Error"):
                    cache[h] = modernized_texts[j]
                elif modernized_texts[j] == orig:
                    # also cache if LLM decided no changes were needed, to prevent re-running forever
                    cache[h] = modernized_texts[j]
            print(f"Batch {idx}/{len(batches)} completed.")
        except Exception as e:
            print(f"Batch {idx}/{len(batches)} failed: {e}", file=sys.stderr)
            # Do NOT cache, leave original text in memory so it doesn't crash
            for j, (parent, key, orig, h) in enumerate(batch_pointers):
                parent[key] = orig

    tasks = []
    for idx, (batch_pointers, batch_texts) in enumerate(batches):
        tasks.append(process_batch(batch_pointers, batch_texts, idx+1))
        
    await asyncio.gather(*tasks)
    
    print("All texts modernized! Saving cache and files to disk...")
    # Merge with the cache on disk: other scripts may have added entries during the run.
    on_disk = load_cache()
    on_disk.update(cache)
    cache = on_disk
    save_cache(cache)

    # Re-read each page and replace only text that is still exactly what was sent,
    # so edits saved meanwhile (page/review editor, other scripts) are kept.
    def apply(item, key):
        text = item.get(key)
        if text and text.strip() and get_hash(text) in cache and cache[get_hash(text)] != text:
            item[key] = cache[get_hash(text)]
            return True
        return False

    written = 0
    for file_path in file_data_map:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Skipped {file_path.name}: {e}", file=sys.stderr)
            continue
        changed = apply(data, "chapter_summary") if data.get("chapter_summary") else False
        for verse in data.get("verses") or []:
            changed |= apply(verse, "french")
        for comm in data.get("commentary") or []:
            changed |= apply(comm, "french_translation")
            changed |= apply(comm, "french_commentary")
        if changed:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            written += 1

    print(f"Done! {written} pages updated.")

if __name__ == "__main__":
    asyncio.run(main())
