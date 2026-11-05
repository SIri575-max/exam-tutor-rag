"""Refresh local exports as this one full-book OCR run completes; no scheduled job."""
import json
import subprocess
import sys
import time
from process_full_book import BASE
from sync_sources import ROOT


def main():
    previous = -1
    while True:
        progress = json.loads((BASE / 'progress.json').read_text(encoding='utf-8'))
        complete = progress['completed_pages']
        if complete != previous or progress['status'] != 'running':
            with (BASE / 'organization-latest.log').open('wb') as stream:
                result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'organize_full_book.py')],
                                        stdout=stream, stderr=subprocess.STDOUT, cwd=ROOT)
            if result.returncode:
                raise RuntimeError('Archive refresh failed; see organization-latest.log')
            previous = complete
            print(f'Archive refreshed: {complete}/490 source pages', flush=True)
        if progress['status'] != 'running':
            return
        time.sleep(20)


if __name__ == '__main__':
    main()
