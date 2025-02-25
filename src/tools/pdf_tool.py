import asyncio
import os
import re
import traceback

import pdf2txt
import sys
from pathlib import Path

import aiofiles

from src.tools.log import get_logger

logger = get_logger(__name__)


async def load_from_large_pdf(file_path: Path) -> str | None:
    assert pdf2txt.__name__

    tmp_file_name = f"{file_path.name}_temp"
    tmp_path = file_path.parent.joinpath(tmp_file_name)

    # subprocess
    # cmd = ["pdf2txt.py", "-o", tmp_path.absolute(), file_path.absolute()]
    # cnv_proc = subprocess.Popen(cmd)  # pylint: disable=consider-using-with
    # cnv_proc.wait()

    # asyncio
    python_path = Path(sys.executable)
    pdf2txt_path = python_path.parent.joinpath("pdf2txt.py")
    cmd = [pdf2txt_path, "-o", tmp_path.absolute(), file_path.absolute()]

    p = await asyncio.create_subprocess_exec(python_path, *cmd)
    await p.wait()

    try:
        async with aiofiles.open(tmp_path, "r", encoding="utf-8") as f:
            content = await f.read()
        os.remove(tmp_path)
        cleaned_content = clean_content(content)
        return cleaned_content
    except Exception:
        logger.error(traceback.format_exc())
        return None


def clean_content(content: str) -> str:
    content = re.sub("\xad", "", content)  # Soft hyphen
    content = re.sub("\xa0", " ", content)  # No-break space
    content = re.sub("\x0c", " ", content)
    content = re.sub("[−\\-–—]\n", "", content)
    return content
