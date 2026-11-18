"""Fetch the pinned public SenseVoice CPU model, without sending user data."""
import argparse,hashlib,shutil,tarfile
from pathlib import Path
import requests

URL='https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09.tar.bz2'
SHA256='7305f7905bfcf77fa0b39388a313f3da35c68d971661a65475b56fb2162c8e63'

def fetch(folder):
    folder.mkdir(parents=True,exist_ok=True)
    archive=folder/'download.tar.bz2'
    digest=hashlib.sha256()
    try:
        with requests.get(URL,stream=True,timeout=(20,120)) as response:
            response.raise_for_status()
            with archive.open('wb') as out:
                for block in response.iter_content(1024*1024):
                    out.write(block);digest.update(block)
        if digest.hexdigest()!=SHA256:raise ValueError('Model checksum mismatch')
        with tarfile.open(archive) as tar:
            for item in tar:
                filename=Path(item.name).name
                if item.isfile() and filename in ('model.int8.onnx','tokens.txt','README.md'):
                    with tar.extractfile(item) as src,(folder/filename).open('wb') as dst:
                        shutil.copyfileobj(src,dst)
        if not all((folder/n).is_file() for n in ('model.int8.onnx','tokens.txt')):
            raise ValueError('Model archive missing files')
        shutil.copy2(Path(__file__).with_name('MODEL_LICENSE'),folder/'LICENSE')
        print('Model installed:',folder)
    finally:archive.unlink(missing_ok=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    fetch(parser.parse_args().output)
