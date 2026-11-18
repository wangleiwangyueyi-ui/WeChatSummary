"""GitHub Releases updates. No credentials, chat records or model API calls."""
import hashlib
import json
import re
from pathlib import Path
import requests
from version import VERSION, RUNTIME_VERSION, GITHUB_REPOSITORY

RELEASES_URL = f'https://github.com/{GITHUB_REPOSITORY}/releases'
API_URL = f'https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest'


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise ValueError('版本格式无效；仅接受正式版本 x.y.z')
    return tuple(int(part) for part in value.lstrip('v').split('.'))


def asset_url(version, filename):
    version_tuple(version)
    if not re.fullmatch(r'[A-Za-z0-9._-]+', filename):
        raise ValueError('发布文件名无效')
    return f'{RELEASES_URL}/download/v{version}/{filename}'


def read_release(session=None):
    session = session or requests.Session()
    response = session.get(API_URL, timeout=(10, 25), headers={'Accept':'application/vnd.github+json'})
    if response.status_code == 404:
        raise ValueError('尚未发布正式安装包；请稍后再检查。')
    response.raise_for_status()
    release = response.json()
    tag = release.get('tag_name', '')
    version_tuple(tag)
    if release.get('draft') or release.get('prerelease') or not tag.startswith('v'):
        raise ValueError('发布信息不是正式版本')
    version = tag[1:]
    remote_assets = {a['name']:a for a in release.get('assets', [])}
    manifest_asset = remote_assets.get('release.json', {})
    expected_url = asset_url(version, 'release.json')
    if manifest_asset.get('browser_download_url') != expected_url or manifest_asset.get('size', 0) > 65536:
        raise ValueError('发布缺少正确的更新清单，请从官网发布页查看。')
    response = session.get(expected_url, timeout=(10, 25))
    response.raise_for_status()
    if len(response.content) > 65536:
        raise ValueError('更新清单过大')
    manifest = response.json()
    if manifest.get('version') != version or manifest.get('schema') != 1:
        raise ValueError('版本和清单不匹配')
    valid = {}
    for kind in ('setup', 'update', 'media'):
        entry = manifest.get('assets', {}).get(kind)
        if not entry:
            continue
        name, size, digest = entry.get('name'), entry.get('size'), entry.get('sha256')
        url = asset_url(version, name or '')
        remote = remote_assets.get(name, {})
        if (not name.endswith('.exe') or type(size) is not int or not 0 < size < 2*1024**3
                or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
                or remote.get('browser_download_url') != url or remote.get('size') != size):
            raise ValueError('更新文件信息不完整或不匹配')
        valid[kind] = dict(name=name, size=size, sha256=digest, url=url)
    if 'setup' not in valid:
        raise ValueError('发布缺少主程序安装包')
    return dict(version=version, runtime_version=str(manifest.get('runtime_version', '')),
                notes=str(release.get('body') or '此版本未提供更新说明。'), assets=valid,
                newer=version_tuple(version) > version_tuple(VERSION))


def choose_asset(release, installed=True, components=False):
    if components:
        if 'media' not in release['assets']:
            raise ValueError('此版本暂未发布图片/语音组件包')
        return release['assets']['media']
    kind = 'update' if installed and release['runtime_version'] == RUNTIME_VERSION else 'setup'
    return release['assets'].get(kind, release['assets']['setup'])


def download_verified(asset, folder, progress=lambda *_:None, cancelled=lambda:False, session=None):
    session = session or requests.Session()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / asset['name']
    if destination.parent != folder or not re.fullmatch(r'[A-Za-z0-9._-]+\.exe', asset['name']):
        raise ValueError('安装文件路径无效')
    temporary = destination.with_suffix('.download')
    digest, total = hashlib.sha256(), 0
    try:
        with session.get(asset['url'], stream=True, timeout=(15, 45)) as response:
            response.raise_for_status()
            with temporary.open('wb') as out:
                for chunk in response.iter_content(1024*256):
                    if cancelled():
                        raise ValueError('下载已取消')
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > asset['size']:
                        raise ValueError('下载大小与发布清单不符')
                    out.write(chunk)
                    digest.update(chunk)
                    progress(total, asset['size'])
        if cancelled():
            raise ValueError('下载已取消')
        if total != asset['size'] or digest.hexdigest() != asset['sha256']:
            raise ValueError('下载文件校验失败，请重新下载')
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)
