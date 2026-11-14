"""Extract the official city and park downloads. Run after downloads finish."""
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
DOWNLOADS = ROOT / 'downloads'
EXPECTED = {
    'CityEnviron.zip.001': 2000000000,
    'CityEnviron.zip.002': 966789399,
    'AbandonedPark.zip': 1269678666,
}


def extract(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        # Check paths before extracting a downloaded archive.
        for entry in zipped.infolist():
            path = (destination / entry.filename).resolve()
            if not path.is_relative_to(destination.resolve()):
                raise ValueError(f'Unsafe archive path: {entry.filename}')
        print(f'Extracting {archive.name} into {destination}', flush=True)
        zipped.extractall(destination)
    print(f'Ready: {destination}', flush=True)


def main():
    for name, expected in EXPECTED.items():
        path = DOWNLOADS / name
        if not path.exists() or path.stat().st_size != expected:
            raise SystemExit(f'{name} is not fully downloaded yet; expected {expected} bytes.')
    combined = DOWNLOADS / 'CityEnviron.zip'
    city_size = EXPECTED['CityEnviron.zip.001'] + EXPECTED['CityEnviron.zip.002']
    if not combined.exists() or combined.stat().st_size != city_size:
        print('Joining the two city archive parts...', flush=True)
        with combined.open('wb') as output:
            for suffix in ('001', '002'):
                with (DOWNLOADS / f'CityEnviron.zip.{suffix}').open('rb') as source:
                    shutil.copyfileobj(source, output, length=8 * 1024 * 1024)
    extract(combined, ROOT / 'simulator' / 'City')
    extract(DOWNLOADS / 'AbandonedPark.zip', ROOT / 'simulator' / 'Park')


if __name__ == '__main__':
    main()
