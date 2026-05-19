import os

def load_dotenv(dotenv_path: str = ".env"):
    """
    Loads environment variables from a .env file into os.environ.
    Enables zero-dependency environment variable injection for the application.
    """
    # If .env is in parent directory when running from services/ subfolder, search parent directories
    search_paths = [
        dotenv_path,
        os.path.join(os.path.dirname(__file__), "..", dotenv_path),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), dotenv_path),
    ]
    
    resolved_path = None
    for path in search_paths:
        if os.path.exists(path):
            resolved_path = path
            break
            
    if not resolved_path:
        return
        
    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue
                # Split by the first equals sign
                key_val = line.split("=", 1)
                if len(key_val) == 2:
                    key = key_val[0].strip()
                    val = key_val[1].strip()
                    # Strip quotes if value is wrapped in them
                    if val.startswith(('"', "'")) and val.endswith(('"', "'")):
                        val = val[1:-1]
                    os.environ[key] = val
    except Exception as e:
        print(f"Warning: Failed to read .env file at {resolved_path}: {e}")
