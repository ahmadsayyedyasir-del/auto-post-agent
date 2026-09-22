from pathlib import Path

# Project root = folder where this script is located
ROOT = Path(__file__).parent

# Folders
folders = [
    "backend",
    "backend/app",
    "backend/app/agents",
    "backend/app/api",
    "backend/app/models",
    "backend/app/services",
    "backend/app/tools",
    "backend/app/workflows",
    "backend/tests",
    "frontend",
    "data",
    "docs",
]

# Files
files = [
    "backend/app/__init__.py",
    "backend/app/main.py",
    "backend/app/config.py",

    "backend/app/agents/__init__.py",
    "backend/app/api/__init__.py",
    "backend/app/models/__init__.py",
    "backend/app/services/__init__.py",
    "backend/app/tools/__init__.py",
    "backend/app/workflows/__init__.py",

    "backend/tests/__init__.py",

    ".env.example",
    ".gitignore",
    "README.md",
    "backend/requirements.txt",
]

# Create folders
for folder in folders:
    path = ROOT / folder
    path.mkdir(parents=True, exist_ok=True)

# Create files
for file in files:
    path = ROOT / file
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        path.touch()

print("\n" + "=" * 60)
print("AI SOCIAL MEDIA AUTOMATION PLATFORM")
print("Project structure created successfully!")
print("=" * 60)

print(f"\nProject location:\n{ROOT}")

print(f"\nFolders created: {len(folders)}")
print(f"Files created: {len(files)}")

print("\nNext step:")
print("Open the project folder in Antigravity.")
print("=" * 60)