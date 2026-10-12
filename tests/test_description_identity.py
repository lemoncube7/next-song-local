import unittest
import description_identity as d
class DescriptionIdentityTests(unittest.TestCase):
 def test_original_without_link(self):
  r=d.identity({'title':'「セプテンバーさん」 cover','description':'Original: セプテンバーさん / RADWIMPS'})
  self.assertEqual(r['track']['artist'],'RADWIMPS')
 def test_artist_first_and_feat(self):
  r=d.identity({'title':'Beyond the way cover','description':'Original: Giga - Beyond the way ft.Miku【MV】'})
  self.assertEqual(r['track']['title'],'Beyond the way')
 def test_unrelated_credit_not_saved(self):
  self.assertIsNone(d.identity({'title':'ゲーム実況','description':'music: Song / Artist'}))
 def test_original_vocal_and_channel_agree(self):
  r=d.identity({'title':'End of days','channel':'배카인','description':'Vocal by 배카인\nComposed by 배카인'})
  self.assertEqual(r['track']['artist'],'배카인')
 def test_cover_vocal_not_used_as_original(self):
  self.assertIsNone(d.identity({'title':'Song cover','channel':'Artist','description':'Vocal by Artist\nComposed by Artist'}))
