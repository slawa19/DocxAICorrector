import glob
for f in glob.glob("*.py"):
    try:
        with open(f, encoding="utf-8") as file:
            for i, line in enumerate(file, 1):
                if "gpt-" in line or "gpt-4" in line or "gpt-5" in line or "gpt-image" in line:
                    print(f"{f}:{i}:{line.strip()}")
    except Exception as e:
        print(f"Error {f}: {e}")
