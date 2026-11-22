"""Publish reviewed, allow-listed sources and installers using existing Git auth."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import requests

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from version import VERSION,GITHUB_REPOSITORY


def credential():
    if os.environ.get('GH_TOKEN'):return os.environ['GH_TOKEN']
    result=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',
        capture_output=True,text=True,timeout=30,check=True,
        env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never'))
    fields=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    if not fields.get('password'):raise RuntimeError('Sign in with Git Credential Manager first')
    return fields['password']


def scan(source):
    forbidden={'config.json','api_usage.sqlite','scheduler_state.json','source.json'}
    patterns=[r'AIza[\w-]{25,}',r'gh[pousr]_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{30,}']
    icons={'assets/wechat-summary.ico':b'\x00\x00\x01\x00',
           'assets/wechat-summary.png':b'\x89PNG\r\n\x1a\n'}
    for path in source.rglob('*'):
        if not path.is_file() or '.git' in path.parts or '__pycache__' in path.parts:continue
        relative=path.relative_to(source).as_posix()
        if relative in icons:
            if path.is_symlink() or path.stat().st_size>512*1024 or not path.read_bytes().startswith(icons[relative]):
                raise ValueError('Unexpected icon file: '+relative)
            continue
        if path.name in forbidden or path.suffix.lower() in ('.dpapi','.sqlite','.exe','.ico','.png','.jpg','.onnx','.log'):
            raise ValueError('Private/build file in source: '+str(path.relative_to(source)))
        text=path.read_text(encoding='utf-8-sig')
        if any(re.search(pattern,text) for pattern in patterns):
            raise ValueError('Potential secret in source: '+str(path.relative_to(source)))
        if re.search(r'(?i)[a-z]:[\\/]{1,2}Users[\\/]{1,2}(?!Public|Default|<|your)',text):
            raise ValueError('Owner-specific data in source: '+str(path.relative_to(source)))


def publish(source,assets):
    scan(source)
    manifest=json.loads((assets/'release.json').read_text(encoding='utf-8'))
    if manifest.get('version')!=VERSION:raise ValueError('Version mismatch')
    for value in manifest['assets'].values():
        path=assets/value['name']
        if path.parent!=assets or path.stat().st_size!=value['size']:
            raise ValueError('Invalid release file')
        with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest!=value['sha256']:raise ValueError('Changed installer checksum')
    session=requests.Session()
    session.headers.update({'Authorization':'Bearer '+credential(),'Accept':'application/vnd.github+json',
                            'X-GitHub-Api-Version':'2022-11-28'})
    def api(method,path,**kwargs):
        r=session.request(method,'https://api.github.com'+path,timeout=(20,60),**kwargs)
        r.raise_for_status();return r.json()
    user=api('GET','/user')['login']
    owner,name=GITHUB_REPOSITORY.split('/')
    if user.lower()!=owner.lower():raise ValueError('Authenticated account is not the configured owner')
    repo_response=session.get(f'https://api.github.com/repos/{GITHUB_REPOSITORY}',timeout=30)
    if repo_response.status_code==404:
        repo=api('POST','/user/repos',json={'name':name,'private':False,'description':'Windows 微信聊天本地导出、Gemini 汇总与 PushPlus 推送工具','auto_init':False})
    else:
        repo_response.raise_for_status();repo=repo_response.json()
    if repo.get('private'):raise ValueError('Repository is private; refusing to change visibility')
    remote=f'https://github.com/{GITHUB_REPOSITORY}.git'
    def git(*args):
        result=subprocess.run(['git','-c','safe.directory='+source.as_posix(),*args],cwd=source,capture_output=True,text=True,encoding='utf-8',errors='replace',
            env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never'),timeout=180)
        if result.returncode:raise RuntimeError('Git operation failed: '+result.stderr[-1200:])
        return result.stdout.strip()
    if not (source/'.git').exists():
        git('init','-b','main')
    if 'origin' not in git('remote').splitlines():git('remote','add','origin',remote)
    elif git('remote','get-url','origin')!=remote:raise ValueError('Unexpected Git remote')
    git('add','--all')
    if git('status','--porcelain'):git('commit','-m',f'Release v{VERSION}: Windows installers and verified updates')
    tag='v'+VERSION
    if not git('tag','--list',tag):git('tag',tag)
    git('push','-u','origin','main');git('push','origin',tag)
    # Publish only after all requested assets have uploaded successfully.
    releases=api('GET',f'/repos/{GITHUB_REPOSITORY}/releases')
    release=next((r for r in releases if r['tag_name']==tag),None)
    if release and not release['draft']:raise ValueError('This version is already published; use a new version')
    if not release:
        notes=(source/'CHANGELOG.md').read_text(encoding='utf-8')
        notes+='\n\n首次安装下载 Setup；本地图片/语音另外安装 Media。已安装用户下载 Update。个人配置与密钥不包含在安装包中。'
        release=api('POST',f'/repos/{GITHUB_REPOSITORY}/releases',json={'tag_name':tag,'name':f'WeChatSummary {VERSION}','body':notes,'draft':True,'prerelease':False})
    existing={a['name']:a for a in release.get('assets',[])}
    names=[a['name'] for a in manifest['assets'].values()]+['release.json','SHA256SUMS.txt']
    for name in names:
        file=assets/name
        if name in existing:
            if existing[name]['size']==file.stat().st_size:continue
            raise ValueError('Draft contains a different asset: '+name)
        print('Uploading',name,flush=True)
        with file.open('rb') as data:
            response=session.post(release['upload_url'].split('{')[0],params={'name':name},data=data,
                headers={'Content-Type':'application/octet-stream'},timeout=(30,1200))
        response.raise_for_status()
    release=api('PATCH',f'/repos/{GITHUB_REPOSITORY}/releases/{release["id"]}',json={'draft':False,'make_latest':'true'})
    print(json.dumps({'repository':repo['html_url'],'release':release['html_url']},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--assets',type=Path,required=True)
    args=parser.parse_args();publish(args.source.resolve(),args.assets.resolve())
