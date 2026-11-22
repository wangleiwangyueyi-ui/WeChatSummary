import hashlib
import json
from pathlib import Path
import tempfile
import importlib.util
import os
import unittest
from unittest.mock import Mock, patch
import update_service as updates


class ReleaseTests(unittest.TestCase):
    def release(self):
        files={};remote=[]
        for kind in ('setup','update','media'):
            name=f'WeChatSummary-{kind}-1.2.0.exe'
            files[kind]={'name':name,'size':3,'sha256':hashlib.sha256(b'abc').hexdigest()}
            remote.append({'name':name,'size':3,'browser_download_url':updates.asset_url('1.2.0',name)})
        manifest={'schema':1,'version':'1.2.0','runtime_version':'1','assets':files}
        remote.append({'name':'release.json','size':1000,'browser_download_url':updates.asset_url('1.2.0','release.json')})
        release={'tag_name':'v1.2.0','assets':remote,'body':'Test release'}
        return release,manifest

    def session(self,release,manifest):
        api=Mock(status_code=200);api.json.return_value=release
        doc=Mock(content=json.dumps(manifest).encode());doc.json.return_value=manifest
        session=Mock();session.get.side_effect=[api,doc]
        return session

    def test_valid_release_and_dependency_selection(self):
        release,manifest=self.release()
        with patch.object(updates,'VERSION','1.1.0'):
            value=updates.read_release(self.session(release,manifest))
        self.assertTrue(value['newer'])
        self.assertIn('update',updates.choose_asset(value)['name'])
        self.assertIn('setup',updates.choose_asset(value,installed=False)['name'])
        value['runtime_version']='2'
        self.assertIn('setup',updates.choose_asset(value)['name'])
        self.assertIn('media',updates.choose_asset(value,components=True)['name'])

    def test_reject_wrong_host_wrong_manifest_and_prerelease(self):
        for mode in ('host','version','digest','size','prerelease'):
            with self.subTest(mode=mode):
                release,manifest=self.release()
                if mode=='host':release['assets'][0]['browser_download_url']='https://example.com/install.exe'
                if mode=='version':manifest['version']='1.0.0'
                if mode=='digest':manifest['assets']['setup']['sha256']='invalid'
                if mode=='size':manifest['assets']['setup']['size']=999
                if mode=='prerelease':release['prerelease']=True
                with self.assertRaises(ValueError):updates.read_release(self.session(release,manifest))

    def test_versions_are_numeric_and_formal(self):
        self.assertGreater(updates.version_tuple('v1.10.0'),updates.version_tuple('1.9.9'))
        for value in ('v1.2.0-beta',None,'../../1.2.0','1.2'):
            with self.assertRaises(ValueError):updates.version_tuple(value)

    def test_download_rejects_tampering_and_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset={'name':'installer.exe','size':3,'sha256':hashlib.sha256(b'abc').hexdigest(),'url':'https://example.com'}
            target=Path(tmp)/'installer.exe';target.write_bytes(b'old')
            response=Mock();response.iter_content.return_value=[b'bad']
            context=Mock();context.__enter__=Mock(return_value=response);context.__exit__=Mock(return_value=False)
            session=Mock();session.get.return_value=context
            with self.assertRaises(ValueError):updates.download_verified(asset,tmp,session=session)
            self.assertEqual(target.read_bytes(),b'old')
            self.assertFalse(target.with_suffix('.download').exists())
            response.iter_content.return_value=[b'a',b'bc']
            self.assertEqual(updates.download_verified(asset,tmp,session=session).read_bytes(),b'abc')
            with self.assertRaises(ValueError):updates.download_verified(asset,tmp,cancelled=lambda:True,session=session)
            self.assertEqual(target.read_bytes(),b'abc')

    def test_new_user_has_no_owner_account_or_automatic_jobs(self):
        from secure_store import DEFAULT
        self.assertEqual(DEFAULT['wechat_dir'],'')
        self.assertEqual(DEFAULT['proxy_url'],'')
        self.assertFalse(DEFAULT['enabled'])
        self.assertFalse(DEFAULT['selected_groups'])
        self.assertFalse(DEFAULT['enable_voice_asr'])

    def test_release_scan_only_allows_project_icon_paths(self):
        from release_tools.publish_release import scan

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            assets = source/'assets'
            assets.mkdir()
            for name in ('wechat-summary.ico', 'wechat-summary.png'):
                (assets/name).write_bytes((Path(__file__).parent/'assets'/name).read_bytes())
            scan(source)
            (source/'screenshot.png').write_bytes((assets/'wechat-summary.png').read_bytes())
            with self.assertRaisesRegex(ValueError, 'screenshot.png'):
                scan(source)

    def test_installed_data_path_preserves_existing_portable_config(self):
        import app_paths
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'program';root.mkdir()
            script=root/'app_paths.py';script.write_bytes(Path(app_paths.__file__).read_bytes())
            (root/'installed-mode.json').write_text('{}')
            with patch.dict(os.environ,{'LOCALAPPDATA':str(Path(tmp)/'data')}):
                os.environ.pop('WECHATSUMMARY_DATA_DIR',None)
                def load():
                    spec=importlib.util.spec_from_file_location('test_paths',script)
                    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                    return module
                self.assertEqual(load().DATA_DIR,Path(tmp)/'data'/'WeChatSummary')
                (root/'config.json').write_text('{"test":true}')
                self.assertEqual(load().DATA_DIR,root.resolve())


if __name__=='__main__':unittest.main()
