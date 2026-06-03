import subprocess
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 5:
        print("Usage: python_script.py image_path min_radius max_radius scale", file=sys.stderr)
        raise SystemExit(1)

    script = Path(__file__).with_name("measurement_modes.py")
    command = [
        sys.executable,
        str(script),
        "--image",
        sys.argv[1],
        "--mode",
        "au",
        "--scale",
        sys.argv[4],
        "--au-min-radius",
        sys.argv[2],
        "--au-max-radius",
        sys.argv[3],
        "--sio2-min-radius",
        sys.argv[2],
        "--sio2-max-radius",
        sys.argv[3],
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    if result.returncode != 0:
        print(result.stdout, end="")
        raise SystemExit(result.returncode)

    print("processed_image.jpg")


if __name__ == "__main__":
    main()
