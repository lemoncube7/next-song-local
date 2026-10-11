import unittest
import recognition

class ConfirmedAliasTests(unittest.TestCase):
    def test_human_vocal_credit_does_not_confirm_composer_as_artist(self):
        import song_databases
        song={'id':1,'name':'Song','songType':'Original','pvs':[{'service':'Youtube','pvId':'abcdefghijk'}],
              'artists':[{'name':'Composer','categories':'Producer','effectiveRoles':'Composer'},
                         {'name':'Arranger','categories':'Producer','effectiveRoles':'Arranger'},
                         {'name':'Singer','categories':'Vocalist'}]}
        candidate=song_databases.voca_candidate(song,'abcdefghijk')
        self.assertFalse(candidate['confident'])
        self.assertEqual(candidate['artist'],'Composer')

    def test_saved_alias_requires_artist_and_unique_identity(self):
        track={'id':'one','title':'フューチャー・イヴ','artist':'sasakure.UK','aliases':[{'title':'FUTURE EVE','artist':'sasakure.UK'}]}
        video={'title':'フューチャー・イヴ Official Video','music_metadata':{'cards':[{'title':'FUTURE EVE','artist':'sasakure.UK'}]}}
        self.assertEqual(recognition.recognize(video,tracks=[track])['track']['title'],track['title'])
        video['music_metadata']['cards'][0]['artist']='Other singer'
        self.assertIsNone(recognition.confirmed_identity(video,[track]))
        video['music_metadata']['cards'][0]['artist']='sasakure.UK'
        self.assertIsNone(recognition.confirmed_identity(video,[track,{**track,'id':'two'}]))
        video['title']='FUTURE EVE cover'
        self.assertIsNone(recognition.confirmed_identity(video,[track]))
        video['title']='Compilation'
        video['music_metadata']['cards'].append({'title':'Other song','artist':'Other artist'})
        self.assertIsNone(recognition.confirmed_identity(video,[track]))

    def test_cover_original_uses_confirmed_identity_before_raw_metadata(self):
        video={'title':'Song Cover','description':'Original: https://youtu.be/abcdefghijk'}
        original={'title':'Ambiguous old title','classification':{'status':'song','title':'Song','artist':'Original artist'}}
        result=recognition.recognize(video,lookup=lambda _:original)
        self.assertEqual(result['status'],'recognized')
        self.assertEqual(result['track']['artist'],'Original artist')
