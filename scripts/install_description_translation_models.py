"""Install Argos source-to-English models for the description worker."""
import argparse
import shutil
from pathlib import Path
from argostranslate import package, settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--languages', nargs='+', default=['de', 'fr', 'es', 'it', 'nl', 'pl', 'pt', 'ru', 'uk', 'tr'])
    args = parser.parse_args()
    package.update_package_index()
    available = package.get_available_packages()
    installed = {(p.from_code, p.to_code) for p in package.get_installed_packages()}
    for language in args.languages:
        if (language, 'en') in installed:
            continue
        choices = [p for p in available if p.from_code == language and p.to_code == 'en']
        if not choices:
            raise RuntimeError('translation_model_unavailable_' + language)
        if shutil.disk_usage(settings.package_data_dir).free < 1_000_000_000:
            raise RuntimeError('translation_model_disk_space_low')
        archive = choices[-1].download()
        package.install_from_path(archive)
        Path(archive).unlink(missing_ok=True)
        print('Installed ' + language + ' -> en', flush=True)


if __name__ == '__main__':
    main()
