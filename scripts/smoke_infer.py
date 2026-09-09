"""Run the real CLI and validate per-chunk output independently of UI language."""
import math
from pathlib import Path
import re
import subprocess
import sys


def check_probabilities(output, expected_chunks):
    values = re.findall(r"^\s*([0-9.]+)s\s+p=(\S+)", output, re.MULTILINE)
    if len(values) != expected_chunks or not values:
        raise ValueError(f"Expected {expected_chunks} chunk probabilities, got {len(values)}")
    for i, (timestamp, value) in enumerate(values, 1):
        probability = float(value)
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError(f"Invalid target-speaker probability: {value}")
        if not math.isclose(float(timestamp), i * 0.16, abs_tol=0.005):
            raise ValueError(f"Unexpected chunk timestamp: {timestamp}")


def main():
    import soundfile as sf

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "infer.py", "--enroll", "examples/enroll.wav",
         "--test", "examples/test.wav", "--fast", "--verbose"],
        cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, end="", flush=True)
    result.check_returncode()
    info = sf.info(root / "examples/test.wav")
    expected = math.ceil(info.frames * 16000 / info.samplerate / 2560)
    check_probabilities(result.stdout, expected)
    print(f"Smoke inference passed: {expected} finite chunk probabilities in [0, 1]")


if __name__ == "__main__":
    main()
