"""Package optional resources and verified native splits beside the base APK.

No upload. Signing passwords are read by the JDK from environment variables.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

from create_update_manifest import signer_digest, PACKAGE

IDS = ('official-themes', 'advanced', 'admin', 'cat-art')
MAX_BYTES = 16 * 1024 * 1024


def filename(module):
    return 'module-' + module + ('.apk' if module in ('advanced', 'admin') else '.acmpack')


def validate_catalog(index, version, code, repository):
    if (index.get('schemaVersion') != 1 or index.get('versionCode') != code
            or index.get('versionName') != version or len(index.get('modules', [])) != 4):
        raise ValueError('Incomplete or incompatible module catalog')
    seen = set()
    for entry in index['modules']:
        module = entry.get('id')
        if module not in IDS or module in seen:
            raise ValueError('Duplicate or unknown module')
        seen.add(module)
        expected = f'https://github.com/{repository}/releases/download/v{version}/{filename(module)}'
        if (entry.get('url') != expected or not re.fullmatch('[0-9a-f]{64}', entry.get('sha256', ''))
                or type(entry.get('sizeBytes')) is not int or not 0 < entry['sizeBytes'] <= MAX_BYTES
                or entry.get('kind') != ('native' if module in ('advanced', 'admin') else 'assets')):
            raise ValueError('Invalid module artifact identity, URL, hash or size')


def package_resources(source, target, module, code):
    source = Path(source)
    with ZipFile(target, 'w', ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr('module.json', json.dumps(dict(id=module, api=1, versionCode=code, kind='assets')))
        for path in sorted((source / 'payload').rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())


def run(*args):
    # Do not echo signing invocations or environment contents on error.
    result = subprocess.run(list(map(str, args)), capture_output=True)
    if result.returncode:
        raise RuntimeError('Module build/verification tool failed: ' + Path(args[0]).name)
    return result.stdout.decode('utf-8', errors='replace')


def verify_jar(archive, jarsigner, keytool, certificate):
    output = run(jarsigner, '-J-Duser.language=en', '-J-Duser.country=US', '-verify', archive)
    if 'jar verified.' not in output:
        raise ValueError('Module must have a valid JAR/v1 signature')
    details = run(keytool, '-J-Duser.language=en', '-J-Duser.country=US', '-printcert', '-jarfile', archive)
    hashes = re.findall(r'SHA256:\s*([A-Fa-f0-9:]+)', details)
    if not hashes or any(item.replace(':', '').lower() != certificate for item in hashes):
        raise ValueError('Module signature differs from the pinned app certificate')


def build(args):
    destination = Path(args.output_dir)
    manifest = json.loads((destination / 'update.json').read_text(encoding='utf-8'))
    version, code = manifest['versionName'], manifest['versionCode']
    if args.repository != 'GiraffesLoveBeauty/ACM-Forever':
        raise ValueError('Module client pins the distribution repository')
    certificate = manifest['signingCertificateSha256']
    entries = []
    for module in IDS:
        target = destination / filename(module)
        if module in ('advanced', 'admin'):
            source = Path(args.app_root) / module / 'build/outputs/apk' / args.channel / f'{module}-{args.channel}.apk'
            verify = run(args.apksigner, 'verify', '--verbose', '--print-certs', source)
            signer_digest(verify, certificate)
            badging = run(args.aapt, 'dump', 'badging', source)
            package = next((line for line in badging.splitlines() if line.startswith('package: ')), '')
            fields = dict(re.findall(r"(\w+)='([^']*)'", package))
            if fields.get('name') != PACKAGE or fields.get('versionCode') != str(code) or fields.get('split') != module:
                raise ValueError('Native split belongs to another app, version or feature')
            with ZipFile(source) as archive:
                metadata = json.loads(archive.read(f'assets/modules/{module}.json'))
                if metadata != dict(id=module, api=1, versionCode=code, kind='native', splitName=module):
                    raise ValueError('Signed native metadata mismatch')
            shutil.copyfile(source, target)
        else:
            package_resources(Path(args.resources) / module, target, module, code)
            run(args.jarsigner, '-keystore', args.keystore, '-storepass:env', 'ANDROID_KEYSTORE_PASSWORD',
                '-keypass:env', 'ANDROID_KEY_PASSWORD', '-digestalg', 'SHA-256', '-sigalg', 'SHA256withRSA',
                target, os.environ['ANDROID_KEY_ALIAS'])
        verify_jar(target, args.jarsigner, args.keytool, certificate)
        entries.append(dict(id=module, kind='native' if module in ('advanced', 'admin') else 'assets',
                            url=f'https://github.com/{args.repository}/releases/download/v{version}/{target.name}',
                            sha256=hashlib.sha256(target.read_bytes()).hexdigest(), sizeBytes=target.stat().st_size))
    index = dict(schemaVersion=1, versionCode=code, versionName=version, modules=entries)
    validate_catalog(index, version, code, args.repository)
    (destination / 'modules.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    manifest['modulesUrl'] = f'https://github.com/{args.repository}/releases/download/v{version}/modules.json'
    (destination / 'update.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({entry['id']: entry['sizeBytes'] for entry in entries}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output-dir', 'app-root', 'resources', 'repository', 'keystore', 'jarsigner', 'keytool', 'aapt', 'apksigner'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--channel', choices=('debug', 'release'), required=True)
    build(parser.parse_args())
