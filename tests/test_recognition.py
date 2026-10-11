import json, sys, tempfile, unittest, urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core, recognition

class RecognitionTests(unittest.TestCase):
    def test_additional_credit_and_synth_voice_formats(self):
        cases=[('退廃的人生讃歌 / 重音テト','Ro2noki','◇曲/絵/動画：Ro2noki','退廃的人生讃歌'),
               ('スロウダウナー／初音ミク・GUMI','ろくろ','曲.動画　ろくろ　https://example.org','スロウダウナー'),
               ('LIMITED QUEEN / 鳴花ヒメ・ミコト','きさら - KISARA','music / movie : きさら','LIMITED QUEEN'),
               ('ツクモの契 - 重音テト','naraku','作詞作曲：naraku','ツクモの契'),
               ('オブソミート / 初音ミク・重音テトSV - Obsolete Meat','サツキ','■Music / サツキ','オブソミート'),
               ('みきとP 『 少女レイ 』 MV','みきとP mikitoP OFFICIAL','Music & Words - みきとP','少女レイ')]
        for title,channel,description,song in cases:
            r=recognition.recognize(dict(title=title,channel=channel,description=description))
            self.assertEqual(r['status'],'recognized');self.assertEqual(r['track']['title'],song)
        r=recognition.recognize(dict(title='ミザン／flower, 歌愛ユキ',channel='須田景凪 バルーン',description='music / バルーン, ぬゆり'))
        self.assertEqual(r['track']['artist'],'バルーン, ぬゆり')

    def test_subtitle_original_source_and_translated_title_stays_candidate(self):
        v={'title':'뇌내혁명 걸 脳内革命ガール 자막','description':'원본 영상 출처 - https://youtu.be/abcdefghijk'}
        original={'classification':{'status':'song','title':'脳内革命ガール','artist':'MARETU'}}
        self.assertEqual(recognition.recognize(v,lookup=lambda i:original)['status'],'recognized')
        v['title']='번역된 제목 자막'
        self.assertEqual(recognition.recognize(v,lookup=lambda i:original)['status'],'ambiguous')

    def test_cover_original_link_uses_original_artist_not_cover_singer(self):
        original={'title':'白ゆき / 初音ミク','channel':'ヨルシカ / n-buna Official','description':'music：ナブナ（mylist/30722660）(twitter→@nabuna2)'}
        cover={'title':'白ゆき / Cover Singer Cover','channel':'Cover Singer','description':'Original: 白ゆき / n-buna\nhttps://youtu.be/abcdefghijk'}
        r=recognition.recognize(cover,lookup=lambda vid:original)
        self.assertEqual(r['status'],'recognized');self.assertEqual(r['track']['artist'],'n-buna')

    def test_original_links_ignore_promotion_and_missing_metadata_is_candidate(self):
        v={'title':'Song covered by Singer','channel':'Singer','description':'■原曲\nArtist 様「Song」\nhttps://youtu.be/abcdefghijk\n\nCredits\nPromotion https://youtu.be/12345678901'}
        self.assertEqual([x['video_id'] for x in recognition.original_links(v['description'])],['abcdefghijk'])
        r=recognition.recognize(v,lookup=lambda vid:None)
        self.assertEqual(r['status'],'ambiguous');self.assertEqual(r['candidates'][0]['artist'],'Artist')
        v['description']='Promotion https://youtu.be/abcdefghijk'
        self.assertNotEqual(recognition.recognize(v,lookup=lambda vid:{'classification':{'status':'song','title':'Song','artist':'Other'}})['status'],'recognized')

    def test_cover_link_title_mismatch_and_multiple_originals_not_auto_saved(self):
        v={'title':'Song Cover','description':'Original: https://youtu.be/abcdefghijk'}
        lookup=lambda vid:{'classification':{'status':'song','title':'Different','artist':'Artist'}}
        self.assertNotEqual(recognition.recognize(v,lookup=lookup)['status'],'recognized')
        v['description']='Original: https://youtu.be/abcdefghijk https://youtu.be/12345678901'
        lookup=lambda vid:{'classification':{'status':'song','title':'Song','artist':'Artist'}}
        self.assertNotEqual(recognition.recognize(v,lookup=lookup)['status'],'recognized')

    def test_expanded_original_title_and_creator_formats(self):
        cases=[('花に風／初音ミク','須田景凪 バルーン','music / バルーン','花に風','バルーン'),
               ('オーバーライド - 重音テトSV[吉田夜世]','吉田夜世','曲,詞,動画,Mix,Mastering：吉田夜世','オーバーライド','吉田夜世'),
               ('ド屑 / 歌愛ユキ','なきそ','■音楽：なきそ https://example.org','ド屑','なきそ'),
               ('『アンコールダンス』/ feat. 重音テトSV','MIMI','Music MIMI @mimi','アンコールダンス','MIMI'),
               ('Stellar Stellar / 星街すいせい(official)','Suisei Channel','作曲 : TAKU INOUE','Stellar Stellar','星街すいせい'),
               ('ドラマツルギー - Eve  MV','Eve','作詞/作曲/歌：Eve','ドラマツルギー','Eve'),
               ('【imase】NIGHT DANCER（MV）','imase','作詞・作曲：imase','NIGHT DANCER','imase'),
               ('幽霊東京 / 初音ミク','YOASOBI','・MUSIC & LYRICS : Ayase','幽霊東京','Ayase'),
               ('リコレクションエンドロウル / recollection endroll - miku [オリジナル]','ツミキ / NOMELON NOLEMON','［music/lyric/arrange/mix/movie］ツミキ/tsumiki','リコレクションエンドロウル','ツミキ')]
        for title,channel,description,song,artist in cases:
            with self.subTest(title=title):
                r=recognition.recognize(dict(title=title,channel=channel,description=description))
                self.assertEqual(r['status'],'recognized');self.assertEqual((r['track']['title'],r['track']['artist']),(song,artist))

    def test_expanded_formats_do_not_confirm_reuploads_variants_or_missing_credits(self):
        for v in [dict(title='曲 / 初音ミク',channel='Uploader'),
                  dict(title='曲 / 初音ミク',channel='Fan',description='Music : Artist'),
                  dict(title='Artist「曲」 cover',channel='Artist',description='Music : Artist'),
                  dict(title='曲 (Live) / Artist',channel='Artist'),
                  dict(title='Artist「曲」「別の曲」',channel='Artist',description='Music : Artist'),
                  dict(title='稲葉曇『遷移一区画』Vo. 歌愛ユキ',channel='Thibaut T.')]:
            self.assertNotEqual(recognition.recognize(v)['status'],'recognized',v)

    def test_artist_song_vocal_translation_with_bilingual_uploader(self):
        r=recognition.recognize({'title':'ぬゆり - フラジール / GUMI : Fragile','channel':'Lanndo / ぬゆり Official'})
        self.assertEqual(r['status'],'recognized');self.assertEqual(r['track']['title'],'フラジール');self.assertEqual(r['track']['artist'],'ぬゆり')
    def test_structured_vocal_title_preserves_cover_and_wrong_uploader(self):
        for channel,title in [('Fan','ぬゆり - フラジール / GUMI : Fragile'),('Lanndo / ぬゆり Official','ぬゆり - フラジール / GUMI : Fragile cover')]:
            self.assertNotEqual(recognition.recognize({'title':title,'channel':channel})['status'],'recognized')
    def test_structured_vocal_titles_other_creators_and_colons(self):
        r=recognition.recognize({'title':'Artist - Re:Re: / 初音ミク : English title','channel':'Artist'})
        self.assertEqual(r['status'],'recognized');self.assertEqual(r['track']['title'],'Re:Re:')
    def test_candidate_aliases_combine_local_and_web_credits(self):
        values=[{'title':'ラグトレイン','artist':'稲葉曇'},
                {'title':'ラグトレイン - Lagtrain','artist':'inabakumori'},
                {'title':'Lagtrain','artist':'稲葉曇 feat. 歌愛ユキ','url':'https://utaten.com/lyric/example/'}]
        merged=recognition.merge_candidates(values)
        self.assertEqual(len(merged),1);self.assertEqual(len(merged[0]['alternate_labels']),3)
        self.assertEqual(merged[0]['url'],'https://utaten.com/lyric/example/')
    def test_candidate_other_performers_and_versions_remain_distinct(self):
        values=[{'title':'Song','artist':'Artist'}, {'title':'song','artist':'Artist'},
                {'title':'Song','artist':'Cover Artist'}, {'title':'Song (Live)','artist':'Artist'},
                {'title':'Song (Remix)','artist':'Artist'}]
        self.assertEqual(len(recognition.merge_candidates(values)),4)
    def test_conflicting_extraction_of_artist_suffix_is_one_candidate(self):
        r=recognition.recognize({'title':'帝国少女/R Sound Design feat.初音ミク-Imperial Girl','channel':'R Sound Design','description':'Music/R Sound Design'})
        self.assertEqual(r['status'],'recognized');self.assertEqual(len(r['candidates']),1)
    def test_manual_song_aliases_apply_to_candidates(self):
        values=[{'title':'Flower And Badger Game','artist':'ヨルシカ'},{'title':'花人局','artist':'ヨルシカ'}]
        tracks=[{'id':'same','aliases':[{'title':v['title'],'artist':v['artist']} for v in values]}]
        self.assertEqual(len(recognition.merge_candidates(values,tracks)),1)
    def test_artist_quote_and_channel_agree(self):
        result=recognition.recognize({'title':'稲葉曇『ラグトレイン』Vo. 歌愛ユキ','channel':'稲葉曇','category':'Music'})
        self.assertEqual(result['status'],'recognized');self.assertEqual(result['track']['title'],'ラグトレイン');self.assertEqual(result['track']['artist'],'稲葉曇')
    def test_feat_requires_creator_credit(self):
        video={'title':'マシュマリー / feat.初音ミク','channel':'MIMI','description':'Music/MIMI @mimi_3mi'}
        self.assertEqual(recognition.recognize(video)['status'],'recognized')
        video['description']='';self.assertEqual(recognition.recognize(video)['status'],'unresolved')
    def test_artist_suffix_and_bilingual_channel(self):
        video={'title':'1000年生きてる / いよわ feat.初音ミク（living millennium / Iyowa feat.Hatsune Miku）','channel':'いよわ/ iyowa'}
        self.assertEqual(recognition.recognize(video)['track']['artist'],'いよわ')
    def test_cover_and_multiple_songs_are_not_auto_saved(self):
        for title in ['Artist「Song」 cover','Artist「Song」「Another」']:
            self.assertNotEqual(recognition.recognize({'title':title,'channel':'Artist'})['status'],'recognized')
    def test_same_title_other_artist_only_candidate(self):
        r=recognition.recognize({'title':'Song','channel':'Uploader'},[{'title':'Song','singer':'Artist'}])
        self.assertEqual(r['status'],'ambiguous');self.assertEqual(r['candidates'][0]['artist'],'Artist')
    def test_recognition_correction_survives_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=core.connect(Path(tmp)/'test.sqlite3')
            row={'title':'Song','titleUrl':'https://www.youtube.com/watch?v=abcdefghijk','time':'2026-10-10T08:00:00Z'}
            core.import_bytes(db,json.dumps([row]).encode(),'history.json')
            core.set_state(db,'corrections',{'abcdefghijk':{'title':'Song','artist':'Artist','source':'auto_recognition','reason':'channel match'}},'user_state');db.commit();core.rebuild(db)
            self.assertEqual(core.tracks(db)[0]['sources'],['auto_recognition']);db.close()

if __name__=='__main__':unittest.main()
