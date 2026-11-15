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
PINYIN = {
    'official-themes': 'guan_1_fang_1_zhu_3_ti_2_ku_4',
    'advanced': 'gao_1_ji_2_ge_4_xing_4_hua_4',
    'admin': 'shou_3_ji_1_bian_4_jie_2_guan_3_li_3',
    'cat-art': 'fen_1_ceng_2_mao_1_niang_2_su_4_cai_2',
}
MAX_BYTES = 16 * 1024 * 1024


def module_number(module, version, build='I'):
    if (module not in PINYIN or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version)
            or not isinstance(build, str) or not build
            or not re.fullmatch(r'M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})', build)):
        raise ValueError('Invalid module number')
    return f'{PINYIN[module]}-{version}-{build}'


def filename(module):
    return 'module-' + module + ('.apk' if module in ('advanced', 'admin') else '.acmpack')


def resource_revision(source):
    digest = hashlib.sha256(b'ACM-MODULE-ASSETS/1\n')
    files = sorted((path for path in (Path(source) / 'payload').rglob('*') if path.is_file()), key=lambda path: path.relative_to(Path(source) / 'payload').as_posix())
    if not files:
        raise ValueError('Resource module is empty')
    for path in files:
        relative = path.relative_to(Path(source) / 'payload').as_posix()
        content = path.read_bytes()
        digest.update((relative + '\0' + str(len(content)) + '\0' + hashlib.sha256(content).hexdigest() + '\n').encode('utf-8'))
    return 'a1-' + digest.hexdigest()


def native_revision(source):
    digest = hashlib.sha256(b'ACM-MODULE-NATIVE/1\n')
    source = Path(source)
    for path in sorted([source / 'build.gradle', *[p for p in (source / 'src/main').rglob('*') if p.is_file()]], key=lambda path: path.relative_to(source).as_posix()):
        digest.update(path.relative_to(source).as_posix().encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
    return 'n1-' + digest.hexdigest()


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
        if 'revision' in entry and (not isinstance(entry['revision'], str) or not re.fullmatch(('n1-' if module in ('advanced', 'admin') else 'a1-') + '[0-9a-f]{64}', entry['revision'])):
            raise ValueError('Invalid independent module revision')
        if 'number' in entry:
            number = entry['number']
            if not isinstance(number, str) or number != module_number(module, version, number.rsplit('-', 1)[-1]):
                raise ValueError('Module number does not match identity or App version')


def package_resources(source, target, module, code):
    source = Path(source)
    with ZipFile(target, 'w', ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr('module.json', json.dumps(dict(id=module, api=1, versionCode=code, kind='assets', revision=resource_revision(source))))
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
                            sha256=hashlib.sha256(target.read_bytes()).hexdigest(), sizeBytes=target.stat().st_size,
                            number=module_number(module, version, args.module_build),
                            revision=native_revision(Path(args.app_root) / module) if module in ('advanced', 'admin') else resource_revision(Path(args.resources) / module)))
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
    parser.add_argument('--module-build', default='I', help='Canonical Roman build number within this App version, e.g. I or II')
    build(parser.parse_args())
