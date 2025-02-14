import os
import re
import subprocess
from pathlib import Path


def load_from_large_pdf(file_path: Path) -> str | None:
    tmp_file_name = f"{file_path.name}_temp"
    tmp_path = file_path.parent.joinpath(tmp_file_name)
    cmd = ["pdf2txt.py", "-o", tmp_path.absolute(), file_path.absolute()]
    cnv_proc = subprocess.Popen(cmd)  # pylint: disable=consider-using-with
    cnv_proc.wait()

    try:
        with open(tmp_path, "r", encoding="utf-8") as f:
            content = f.read()
        os.remove(tmp_path)
        cleaned_content = clean_content(content)
        return cleaned_content
    except Exception:
        return None


def clean_content(content: str) -> str:
    content = re.sub("\xad", "", content)  # Soft hyphen
    content = re.sub("\xa0", " ", content)  # No-break space
    content = re.sub("\x0c", " ", content)
    content = re.sub("[−\\-–—]\n", "", content)
    return content
