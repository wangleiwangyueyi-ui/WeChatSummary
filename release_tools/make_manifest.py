import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from version import VERSION,RUNTIME_VERSION

folder=Path(sys.argv[1])
manifest={'schema':1,'version':VERSION,'runtime_version':RUNTIME_VERSION,'assets':{}}
for kind,prefix in [('setup','Setup'),('update','Update'),('media','Media')]:
    path=folder/f'WeChatSummary-{prefix}-{VERSION}.exe'
    digest=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
    manifest['assets'][kind]={'name':path.name,'size':path.stat().st_size,'sha256':digest}
(folder/'release.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(folder/'SHA256SUMS.txt').write_text('\n'.join(a['sha256']+'  '+a['name'] for a in manifest['assets'].values())+'\n',encoding='ascii')
print(json.dumps(manifest,indent=2))
