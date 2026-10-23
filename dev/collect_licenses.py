"""Collect installed application dependency versions, notices, and license texts."""
import importlib.metadata as metadata
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent


def application_distributions():
    pending = []
    for line in (ROOT/'dev/requirements.txt').read_text(encoding='utf-8').splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            requirement = Requirement(line)
            # Only what this system installs: the window library differs per system.
            if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
                pending.append(requirement)
    found = {}
    extras_seen = {}
    while pending:
        requirement = pending.pop()
        name = canonicalize_name(requirement.name)
        extras = set(requirement.extras) | {''}
        if name in found and extras <= extras_seen[name]:
            continue
        extras_seen.setdefault(name, set()).update(extras)
        distribution = metadata.distribution(name)
        found[name] = distribution
        for value in distribution.requires or []:
            dependency = Requirement(value)
            if dependency.marker is None or any(dependency.marker.evaluate({'extra': e}) for e in extras):
                pending.append(dependency)
    return found


def license_name(distribution):
    result = distribution.metadata.get('License-Expression')
    if result:
        return result
    classifiers = [s.split(' :: ')[-1] for s in distribution.metadata.get_all('Classifier', [])
                   if s.startswith('License ::') and not s.endswith('OSI Approved')]
    if classifiers:
        return ', '.join(classifiers)
    value = distribution.metadata.get('License', '').strip().split('\n')[0]
    return value[:100] or 'See upstream license'


def main():
    output = ROOT/'src/licenses/python'
    output.mkdir(parents=True, exist_ok=True)
    inventory = []
    for name, distribution in sorted(application_distributions().items()):
        copied = []
        for file in distribution.files or []:
            parts = str(file).replace('\\','/').split('/')
            if not any(t in str(file).lower() for t in ('license','copying','notice')):
                continue
            source = Path(distribution.locate_file(file))
            if not source.is_file() or source.suffix in ('.pyc','.py'):
                continue
            relative = '/'.join(parts[1:])
            target = output/name/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source,target)
            copied.append(target.relative_to(ROOT).as_posix())
        sources = json.loads((ROOT/'src/licenses/sources.json').read_text(encoding='utf-8'))
        for notice in sources:
            if notice['package'] != name:
                continue
            if notice['version'] != distribution.version:
                raise ValueError('Review upstream license for updated package: ' + name)
            target = ROOT / notice['file']
            if hashlib.sha256(target.read_bytes()).hexdigest() != notice['sha256']:
                raise ValueError('Upstream license text changed: ' + name)
            copied.append(notice['file'])
        links = distribution.metadata.get_all('Project-URL', [])
        home = distribution.metadata.get('Home-page') or next((s.split(', ',1)[1] for s in links if ', ' in s), '')
        inventory.append({'name': name, 'version': distribution.version,
                          'license': license_name(distribution), 'upstream': home,
                          'license_files': copied})
    (ROOT/'docs/dependencies.json').write_bytes((json.dumps(inventory,indent=2)+'\n').encode())
    # Pins of packages only another system installs (the Windows or Linux
    # window library) stay as they are; this system's packages are updated.
    pins = {}
    for line in (ROOT/'dev/constraints.txt').read_text(encoding='utf-8').splitlines():
        if '==' in line:
            name, pinned = line.split('==', 1)
            pins[canonicalize_name(name)] = pinned.strip()
    pins.update({d['name']: d['version'].split('+')[0] for d in inventory})
    (ROOT/'dev/constraints.txt').write_bytes(('\n'.join(f'{n}=={v}' for n, v in sorted(pins.items()))+'\n').encode())
    python_license = Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():
        shutil.copy2(python_license,ROOT/'src/licenses/Python-LICENSE.txt')
    system = {'win32': 'Windows x64', 'darwin': 'macOS'}.get(sys.platform, 'Linux')
    rows = ['# Python dependencies', '', f'Installed application dependency closure on {system}. Native bundled libraries',
            'and downloaded model terms are described in the third-party notices.', '',
            '| Package | Tested version | License |', '|---|---|---|']
    for item in inventory:
        license = item['license'].replace('|',' / ')
        name = f'[{item["name"]}]({item["upstream"]})' if item['upstream'].startswith('https://') else item['name']
        rows.append(f'| {name} | {item["version"]} | {license} |')
    (ROOT/'docs/DEPENDENCIES.md').write_bytes(('\n'.join(rows)+'\n').encode())
    print('Collected',len(inventory),'application distributions and their supplied license texts.')


if __name__=='__main__':
    main()
