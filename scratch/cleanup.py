import os
files = [
    "fix_paths.py",
    "fix_paths2.py",
    "fix_test_base_url.py",
    "fix_test_regex.py",
    "fix_test_regex2.py"
]
for f in files:
    try:
        os.remove(f"C:\\Users\\Ilya\\Documents\\new_prj\\" + f)
        print(f"Deleted {f}")
    except FileNotFoundError:
        pass
