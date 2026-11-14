"""Resume the three official AirSim map files, with one connection per file."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
from extract_maps import DOWNLOADS, EXPECTED

BASE = 'https://github.com/microsoft/AirSim/releases/download/v1.8.1-windows/'


def fetch(name):
    path = DOWNLOADS / name
    if path.exists() and path.stat().st_size == EXPECTED[name]:
        return
    print(f'Downloading {name}...', flush=True)
    subprocess.run([
        'curl.exe', '-L', '--fail', '--silent', '--show-error', '--retry', '5',
        '--connect-timeout', '30', '--continue-at', '-', '-o', str(path), BASE + name,
    ], check=True)
    if path.stat().st_size != EXPECTED[name]:
        raise RuntimeError(f'Download size mismatch: {name}')
    print(f'Download ready: {name}', flush=True)


def main():
    DOWNLOADS.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(fetch, name) for name in EXPECTED]):
            future.result()


if __name__ == '__main__':
    main()
