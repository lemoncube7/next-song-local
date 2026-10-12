import unittest,tempfile,zipfile
from pathlib import Path
import app_update
class UpdateTests(unittest.TestCase):
 def test_version_order(self):
  self.assertGreater(app_update.version_tuple('v0.1.10'),app_update.version_tuple('0.1.9'))
  with self.assertRaises(ValueError):app_update.version_tuple('v1.0.0/../../')
 def test_package_allowlist_and_data_preservation(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);stage=root/'stage';stage.mkdir();archive=root/'new.zip'
   with zipfile.ZipFile(archive,'w') as z:
    z.writestr('NextSong/NextSong.exe','new');z.writestr('NextSong/_internal/runtime.dll','runtime')
   app_update.extract(archive,stage)
   self.assertEqual((stage/'NextSong.exe').read_text(),'new')
   for bad in ('NextSong/data/history.db','NextSong/../history.db','NextSong/_internal/../../evil','NextSong/C:/evil'):
    with zipfile.ZipFile(archive,'w') as z:z.writestr(bad,'bad')
    with self.assertRaises(ValueError):app_update.extract(archive,stage)
 def test_source_install_is_disabled(self):
  with self.assertRaises(ValueError):app_update.start()
 def test_untrusted_download_host(self):
  with self.assertRaises(ValueError):app_update.fetch('https://example.com/update.zip')
