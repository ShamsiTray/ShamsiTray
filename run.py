import sys
from pathlib import Path
import os
os.environ['QT_SCALE_FACTOR'] = '0.9'


def main():
    """Configures the system path and launches the application."""
    project_root = Path(__file__).resolve().parent
    src_path = project_root / 'src'
    sys.path.insert(0, str(src_path))

    try:
        from app import main as run_app
        run_app()
    except ImportError as e:
        print(f"Error: Could not import the application. Make sure the 'src' directory exists and is structured correctly.\nDetails: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()