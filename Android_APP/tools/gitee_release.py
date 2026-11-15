"""Mirror the exact Actions-built release to Gitee; never rebuild or upload to source Git."""
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from tag_release import digest, module_assets, validate_manifest

GITHUB_REPOSITORY = 'GiraffesLoveBeauty/ACM-Forever'
GITEE_REPOSITORY = 'MJJ13445/ACM-Forever'
API = 'https://gitee.com/api/v5/repos/' + GITEE_REPOSITORY
ORIGIN = 'https://gitee.com/' + GITEE_REPOSITORY
MAX_APK = 150 * 1024 * 1024


def asset_url(tag, name):
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag) or not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
        raise ValueError('Invalid immutable release path')
    return ORIGIN + '/releases/download/' + tag + '/' + name


def mirror_files(directory, target):
    """Change only JSON URLs. APK, module signatures and original hashes stay identical."""
    directory, target = Path(directory), Path(target)
    manifest = json.loads((directory / 'update.json').read_text(encoding='utf-8'))
    validate_manifest(manifest)
    if manifest.get('channel') not in ('debug', 'release') or not re.fullmatch(r'[0-9a-f]{64}', manifest.get('signingCertificateSha256', '')):
        raise ValueError('Missing channel/signing identity')
    tag = 'v' + manifest['versionName']
    name = 'acmforever-' + manifest['versionName'] + ('-debug' if manifest['channel'] == 'debug' else '') + '.apk'
    github = 'https://github.com/' + GITHUB_REPOSITORY + '/releases/download/' + tag + '/'
    apk, checksum = directory / name, directory / (name + '.sha256')
    if (manifest.get('apkUrl') != github + name or apk.stat().st_size != manifest['sizeBytes']
            or digest(apk) != manifest['sha256'] or checksum.read_text(encoding='ascii').strip() != manifest['sha256'] + '  ' + name):
        raise ValueError('Source APK does not match the verified GitHub manifest')
    optional = module_assets(directory, manifest, GITHUB_REPOSITORY)
    if len(optional) != 5:
        raise ValueError('All four modules and their catalog are required')
    target.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((directory / 'modules.json').read_text(encoding='utf-8'))
    for row in catalog['modules']:
        row['url'] = asset_url(tag, row['url'].rsplit('/', 1)[1])
    mirrored = copy.deepcopy(manifest)
    mirrored['apkUrl'] = asset_url(tag, name)
    mirrored['modulesUrl'] = asset_url(tag, 'modules.json')
    for filename, value in [('modules.json', catalog), ('update.json', mirrored)]:
        data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        if len(data) > (32768 if filename == 'update.json' else 65536):
            raise ValueError('Mirror JSON exceeds client limit')
        (target / filename).write_bytes(data)
    paths = [apk, checksum] + [p for p in optional if p.name != 'modules.json'] + [target / 'modules.json', target / 'update.json']
    return tag, mirrored, paths


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_public_url(url):
    p = urllib.parse.urlsplit(url)
    if (p.scheme != 'https' or p.hostname not in ('gitee.com', 'foruda.gitee.com', 'files.gitee.com')
            or p.username or p.password or p.fragment or p.port not in (None, 443)):
        raise ValueError('Untrusted Gitee attachment redirect')


class Gitee:
    def __init__(self, token):
        if not token:
            raise ValueError('Configure GITEE_RELEASE_TOKEN in GitHub Actions Secrets before publishing')
        self.token = token
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PublicRedirect())

    def api(self, method, suffix, data=None, missing=False, multipart=None):
        headers = {'User-Agent': 'ACMforever-Gitee-mirror/1', 'Accept': 'application/json'}
        payload = None
        if multipart is not None:
            # The documented Gitee endpoint accepts multipart access_token and file fields.
            boundary = 'acmforever-' + uuid.uuid4().hex
            payload = (('--' + boundary + '\r\nContent-Disposition: form-data; name="access_token"\r\n\r\n' + self.token
                + '\r\n--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="' + multipart.name
                + '"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + multipart.read_bytes() + ('\r\n--' + boundary + '--\r\n').encode())
            headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
        elif method != 'GET':
            payload = json.dumps(dict(data or {}, access_token=self.token)).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(API + suffix, data=payload, headers=headers, method=method)
        try:
            # Credentialed API requests never follow a redirect, including to a CDN.
            opener = self.opener if method == 'GET' else urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=60) as response:
                return json.loads(response.read(1024 * 1024))
        except urllib.error.HTTPError as error:
            if missing and error.code == 404:
                return None
            raise RuntimeError('Gitee API operation failed (HTTP ' + str(error.code) + '); no credentials logged') from None
        except (OSError, urllib.error.URLError):
            raise RuntimeError('Gitee API connection failed; inspect connectivity and rerun the unchanged Tag workflow') from None

    def release(self, tag):
        return self.api('GET', '/releases/tags/' + tag, missing=True)

    def files(self, release_id):
        rows = self.api('GET', '/releases/' + str(release_id) + '/attach_files?per_page=100')
        if len(rows) >= 100:
            raise ValueError('Unexpected attachment count')
        return rows

    def readback(self, tag, name, size, expected_hash):
        url = asset_url(tag, name)
        check_public_url(url)
        try:
            with self.opener.open(urllib.request.Request(url, headers={'User-Agent': 'ACMforever-anonymous-readback'}), timeout=60) as response:
                count, result = 0, hashlib.sha256()
                for block in iter(lambda: response.read(65536), b''):
                    count += len(block)
                    if count > size:
                        raise ValueError('Gitee attachment exceeds expected size')
                    result.update(block)
            if count != size or result.hexdigest() != expected_hash:
                raise ValueError('Gitee anonymous read-back differs from verified release artifact')
        except (OSError, urllib.error.URLError):
            raise RuntimeError('Gitee attachment is not anonymously downloadable; release remains a prerelease') from None

    def ensure_tag(self, tag, source_commit):
        local = subprocess.run(['git', 'rev-parse', 'refs/tags/' + tag + '^{}'], capture_output=True, text=True)
        if local.returncode or local.stdout.strip() != source_commit:
            raise ValueError('Local Tag must identify the exact reviewed source commit')
        url = ORIGIN + '.git'
        refs = subprocess.run(['git', 'ls-remote', url, 'refs/tags/' + tag, 'refs/tags/' + tag + '^{}'], capture_output=True, text=True)
        if refs.returncode:
            raise RuntimeError('Cannot read the Gitee Tag; no upload attempted')
        lines = [line.split() for line in refs.stdout.splitlines() if line.strip()]
        if lines:
            sha = next((sha for sha, ref in lines if ref.endswith('^{}')), lines[0][0])
            if sha != source_commit:
                raise ValueError('Existing Gitee Tag differs from reviewed source; never move it')
            return
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_CONFIG_COUNT='1',
            GIT_CONFIG_KEY_0='http.https://gitee.com/.extraheader',
            GIT_CONFIG_VALUE_0='Authorization: Basic ' + base64.b64encode(('MJJ13445:' + self.token).encode()).decode())
        result = subprocess.run(['git', 'push', url, 'refs/tags/' + tag + ':refs/tags/' + tag], env=env, capture_output=True)
        if result.returncode:
            raise RuntimeError('Gitee Tag synchronization failed; check token repository write permission')
        confirmed = subprocess.run(['git', 'ls-remote', url, 'refs/tags/' + tag, 'refs/tags/' + tag + '^{}'], capture_output=True, text=True)
        values = [line.split() for line in confirmed.stdout.splitlines() if line.strip()]
        actual = next((sha for sha, ref in values if ref.endswith('^{}')), values[0][0] if values else '')
        if confirmed.returncode or actual != source_commit:
            raise ValueError('Gitee Tag synchronization was not confirmed')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def publish(client, directory, tag, source_commit):
    with tempfile.TemporaryDirectory() as temp:
        expected_tag, manifest, paths = mirror_files(directory, Path(temp))
        if tag != expected_tag or not re.fullmatch(r'[0-9a-f]{40}', source_commit):
            raise ValueError('Mirror Tag/commit mismatch')
        repo = client.api('GET', '')
        if repo.get('private') is not False or repo.get('full_name') != GITEE_REPOSITORY:
            raise ValueError('Gitee mirror must be the selected public repository')
        latest = client.api('GET', '/releases/latest', missing=True)
        if latest is not None and latest['tag_name'] != tag:
            version = latest['tag_name']
            if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', version) or tuple(map(int, version[1:].split('.'))) > tuple(map(int, tag[1:].split('.'))):
                raise ValueError('A newer or unknown Gitee version is already published')
        client.ensure_tag(tag, source_commit)
        current = client.release(tag)
        if current is None:
            current = client.api('POST', '/releases', dict(tag_name=tag, name='ACMforever ' + manifest['versionName'],
                body=manifest['notes'] + '\n\nSource commit: `' + source_commit + '`\nBuilt by GitHub Actions; identical signed APK/modules.',
                prerelease=True, target_commitish=source_commit))
        if current.get('tag_name') != tag or current.get('prerelease') not in (True, False):
            raise ValueError('Unexpected Gitee release identity')
        if source_commit not in current.get('body', ''):
            raise ValueError('Gitee release source identity differs')
        published = current['prerelease'] is False
        rid = current['id']
        rows = client.files(rid)
        names = [r['name'] for r in rows]
        if len(names) != len(set(names)) or set(names) - {p.name for p in paths}:
            raise ValueError('Unexpected or duplicate Gitee attachments')
        for path in paths:
            if path.name not in names:
                if published:
                    raise ValueError('Published Gitee release is incomplete; never modify published attachments')
                client.api('POST', '/releases/' + str(rid) + '/attach_files', multipart=path)
            client.readback(tag, path.name, path.stat().st_size, digest(path))
        if {r['name'] for r in client.files(rid)} != {p.name for p in paths}:
            raise ValueError('Gitee release incomplete; keep prerelease')
        if not published:
            result = client.api('PATCH', '/releases/' + str(rid), dict(prerelease=False))
            if result.get('prerelease') is not False or result.get('tag_name') != tag:
                raise ValueError('Gitee publication was not confirmed')
        confirmed = client.release(tag)
        if confirmed.get('prerelease') is not False:
            raise ValueError('Gitee final publication state was not confirmed')
        return 'Verified all eight Gitee assets: ' + ORIGIN + '/releases/tag/' + tag


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('tag', 'directory', 'source-commit'):
        p.add_argument('--' + name, required=True)
    args = p.parse_args()
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_EVENT_NAME') != 'push'
            or os.environ.get('GITHUB_REF') != 'refs/tags/' + args.tag
            or os.environ.get('GITHUB_REPOSITORY') != GITHUB_REPOSITORY or os.environ.get('GITHUB_SHA') != args.source_commit):
        p.error('Gitee publication is allowed only from the matching reviewed GitHub Tag Action')
    print(publish(Gitee(os.environ.get('GITEE_RELEASE_TOKEN', '')), args.directory, args.tag, args.source_commit))


if __name__ == '__main__':
    main()
