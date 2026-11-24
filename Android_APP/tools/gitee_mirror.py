"""Recover a published formal Tag using reviewed tooling, without rebuilding its artifacts."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from create_module_assets import verify_jar
from create_update_manifest import bundled_history
from gitee_release import GITHUB_REPOSITORY, Gitee, restore_github, publish
from gitee_transport import event, probe
from release_credits import bundled_credits, requires_review_record, validate_release_credits
from tag_release import GitHub, validate_source

CERTIFICATE='88c9f163cbf379aeca7bc110f66c542a838d0d8e3970f24fd96582bec8e93fe4'
GRADLE='Android_APP/app/app/build.gradle'
HISTORY='Android_APP/app/app/src/main/assets/releases/history.json'
CREDITS='Android_APP/app/app/src/main/assets/releases/credits.json'


def validate_context(tag,environment):
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+',tag):raise ValueError('Only an immutable formal Tag may be mirrored')
    if environment.get('GITHUB_ACTIONS')!='true' or environment.get('GITHUB_REPOSITORY')!=GITHUB_REPOSITORY:
        raise ValueError('Mirror recovery requires the selected GitHub Actions repository')
    event_name,ref=environment.get('GITHUB_EVENT_NAME'),environment.get('GITHUB_REF')
    if not ((event_name=='workflow_dispatch' and ref=='refs/heads/main') or (event_name=='push' and ref=='refs/tags/'+tag)):
        raise ValueError('Mirror recovery only accepts reviewed main dispatch or its matching Tag push')


def read_source(commit,path):
    if not re.fullmatch(r'[0-9a-f]{40}',commit):raise ValueError('Invalid source commit')
    result=subprocess.run(['git','show',commit+':'+path],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    if result.returncode:raise ValueError('Target Tag source snapshot is missing')
    return result.stdout.decode('utf-8')


def prepare(github,tag,directory,source_reader=read_source,run=subprocess.run):
    commit=github.tag_commit(tag)
    if not re.fullmatch(r'[0-9a-f]{40}',commit):raise ValueError('Invalid target Tag commit')
    ancestry=run(['git','merge-base','--is-ancestor',commit,'origin/main'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    if ancestry.returncode:raise ValueError('Target Tag must be an ancestor of reviewed main')
    history=json.loads(source_reader(commit,HISTORY))
    version,code=validate_source(tag,source_reader(commit,GRADLE),history)
    channel='release' if tuple(map(int,version.split('.')))>=(1,0,0) else 'debug'
    if not restore_github(github,directory,tag,commit,version,code,channel,CERTIFICATE):
        raise ValueError('Recovery requires an already published GitHub formal Release')
    apk=Path(directory)/('acmforever-'+version+('-debug' if channel=='debug' else '')+'.apk')
    bundled_history(apk,history)
    if requires_review_record(version):
        credits=json.loads(source_reader(commit,CREDITS))
        validate_release_credits(credits,version)
        bundled_credits(apk,version,credits)
    return commit


def verify_signatures(directory):
    for path in Path(directory).iterdir():
        if path.suffix in ('.apk','.acmpack'):
            verify_jar(path,shutil.which('jarsigner') or 'jarsigner',shutil.which('keytool') or 'keytool',CERTIFICATE)
            event('original_signature_verified',filename=path.name,scheme='JAR/v1')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',required=True)
    args=parser.parse_args()
    validate_context(args.tag,os.environ)
    local=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,timeout=30)
    if local.returncode or local.stdout.strip()!=os.environ.get('GITHUB_SHA'):
        raise ValueError('Checked-out tooling differs from the selected Actions commit')
    if not os.environ.get('GITEE_RELEASE_TOKEN'):raise ValueError('Configure GITEE_RELEASE_TOKEN before mirror recovery')
    try:
        with tempfile.TemporaryDirectory(prefix='acm-original-release-') as directory:
            commit=prepare(GitHub(GITHUB_REPOSITORY),args.tag,Path(directory)/'originals')
            if os.environ.get('GITHUB_EVENT_NAME')=='push' and commit!=os.environ.get('GITHUB_SHA'):
                raise ValueError('Tag moved after the selected push; refuse mirror writes')
            verify_signatures(Path(directory)/'originals')
            probe()
            result=publish(Gitee(os.environ['GITEE_RELEASE_TOKEN']),Path(directory)/'originals',args.tag,commit)
            event('mirror_complete',tag=args.tag,source_commit=commit)
            print(result)
    except Exception:
        summary=os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary,'a',encoding='utf-8') as stream:
                stream.write('## Gitee mirror incomplete\n\nGitHub originals were not rebuilt or replaced. '
                             'Inspect the structured file/transport events above. Reconcile an uncertain upload before another run.\n')
        raise


if __name__=='__main__':main()
