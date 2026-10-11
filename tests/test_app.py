import csv, io, json, sys, tempfile, threading, unittest, urllib.request, urllib.error, zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core, pipeline, server

V1='abcdefghijk';V2='12345678901';V3='abcdefghij2'
def history(vid=V1,time='2026-10-10T08:00:00Z',title='曲',channel='Artist - Topic'):
    return {'title':title+' 을(를) 시청했습니다.','titleUrl':'https://www.youtube.com/watch?v='+vid,'time':time,'subtitles':[{'name':channel}]}
class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=core.connect(Path(self.tmp.name)/'db.sqlite3')
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def ingest(self,rows):return core.import_bytes(self.db,json.dumps(rows,ensure_ascii=False).encode(),'history.json')
    def test_log_decay_retains_old_familiar_songs_and_is_monotonic(self):
        weights=[core.time_weight(age,90) for age in [0,30,90,365,1095]]
        self.assertEqual(weights[0],1);self.assertEqual(weights,sorted(weights,reverse=True))
        self.assertGreater(weights[-1],.25);self.assertEqual(core.time_weight(-1,90),1)
        old_weight=30*core.time_weight(365,90)
        old_score=.5*old_weight/(old_weight+5)+.3*core.time_weight(365,30)
        recent_once=.5/6+.3
        self.assertGreater(old_score,recent_once)
        self.ingest([history(time='2025-10-10T08:00:00Z',title='Familiar') for _ in range(1)]+[history(V2,title='Recent')])
        core.rebuild(self.db)
        familiar=next(t for t in core.tracks(self.db) if t['title']=='Familiar')
        self.assertGreater(familiar['recency_score'],.08)

    def test_import_idempotent_and_incremental(self):
        self.assertEqual(self.ingest([history()])['new_records'],1)
        self.assertEqual(self.ingest([history()])['duplicate_records'],1)
        self.assertEqual(self.ingest([history(time='2026-10-09T08:00:00Z')])['new_records'],1)
        core.rebuild(self.db);self.assertEqual(core.tracks(self.db)[0]['history_records'],2)
    def test_html_import_kst_millisecond_dedup_and_search_exclusion(self):
        self.ingest([history(time='2026-10-10T08:00:00.649Z')])
        def card(vid,action,date):
            return f'<div class="outer-cell"><div><div class="content-cell mdl-cell--6-col"><a href="https://www.youtube.com/watch?v={vid}">曲 &amp; Title</a> {action}<br><a href="https://www.youtube.com/channel/abc">Artist - Topic</a><br>{date}<br></div><div class="content-cell mdl-cell--6-col mdl-typography--text-right">Other text</div></div></div>'
        html='<html>'+card(V1,'을(를) 시청했습니다.','2026. 10. 10. 오후 5:00:00 KST')+card(V2,'을(를) 시청했습니다.','2023. 1. 28. 오전 1:36:15 KST')+card(V3,'검색했습니다.','2023. 1. 28. 오후 12:00:00 KST')+'</html>'
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:z.writestr('Takeout/내 활동/YouTube/내활동.html',html)
        result=core.import_bytes(self.db,buffer.getvalue(),'takeout.zip')
        self.assertEqual(result['new_records'],1);self.assertEqual(result['duplicate_records'],1)
        self.assertEqual(result['html_activity_counts']['non_watch_cards'],1)
        self.assertEqual(self.db.execute('SELECT time FROM events WHERE video_id=?',(V1,)).fetchone()[0],'2026-10-10T08:00:00.649Z')
        self.assertEqual(self.db.execute('SELECT time FROM events WHERE video_id=?',(V2,)).fetchone()[0],'2023-01-27T16:36:15Z')
        self.assertEqual(core.import_bytes(self.db,buffer.getvalue(),'takeout.zip')['new_records'],0)
    def test_library_only_songs_never_recommended(self):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:
            z.writestr('Takeout/watch-history.json',json.dumps([history()]))
            z.writestr('music library songs.csv','Video ID,Song Title,Artist Name 1\n'+V2+',Unwatched,Artist\n')
        core.import_bytes(self.db,buffer.getvalue(),'takeout.zip');core.rebuild(self.db)
        self.assertEqual(len(core.tracks(self.db)),1);self.assertNotIn(V2,core.tracks(self.db)[0]['video_ids'])
    def test_song_grouping_follow_and_persistence(self):
        self.ingest([history(title='言って。',channel='Yorushika - Topic'),history(V2,title='言って。',channel='ヨルシカ - Topic')])
        core.rebuild(self.db);tracks=core.tracks(self.db);self.assertEqual(len(tracks),1);self.assertEqual(tracks[0]['history_records'],2)
        base=tracks[0]['score'];core.set_state(self.db,'follows',['ヨルシカ'],'user_state');self.db.commit()
        self.assertAlmostEqual(core.tracks(self.db)[0]['score']-base,.2,places=5)
        core.set_state(self.db,'queue',[tracks[0]['id']],'user_state');self.db.commit();core.rebuild(self.db)
        self.assertEqual(core.get_state(self.db,'queue',[],'user_state'),[tracks[0]['id']])
    def test_music_category_is_not_song_and_generic_topic_is_review(self):
        self.assertEqual(core.classify({'category':'Music','title':'Guitar pedal comparison'})['status'],'review')
        self.assertEqual(core.classify({'title':'フォニイ','channel':'Release - Topic'})['status'],'review')
        self.assertEqual(core.classify({'title':'Deleted video'})['status'],'unknown')
    def test_structured_description_music_outside_category(self):
        v={'category':'Entertainment','description':'Provided to YouTube by Label\n\nSong · Artist\n\nAuto-generated by YouTube.'}
        c=core.classify(v);self.assertEqual(c['status'],'song');self.assertEqual(c['title'],'Song')
    def test_ordinary_artist_video_and_original_versus_cover_or_talk(self):
        song=core.classify({'title':'Orangestar - 空奏列車 (feat. IA & 初音ミク) Official Video','channel':'Orangestar','category':'Music'})
        self.assertEqual(song['title'],'空奏列車');self.assertEqual(song['artist'],'Orangestar')
        original=core.classify({'title':'【初音ミク】　しう　【オリジナル】','channel':'MARETU','category':'Music'})
        self.assertEqual(original['title'],'しう')
        cover=core.classify({'title':'Orangestar - 空奏列車 cover','channel':'Orangestar','category':'Music'})
        self.assertEqual(cover['status'],'review')
        talk=core.classify({'title':'기타 초보자 연습 팁','channel':'Guitar Lesson','category':'Music'})
        self.assertEqual(talk['status'],'review')
        quoted=core.classify({'title':'ずっと真夜中でいいのに。ZUTOMAYO New Music Video「あかねさす頃」','channel':'ずっと真夜中でいいのに。 ZUTOMAYO','category':'Music'})
        self.assertEqual(quoted['title'],'あかねさす頃');self.assertEqual(quoted['artist'],'ずっと真夜中でいいのに。')
        multi=core.classify({'title':'A／B／C／D [オリジナル]','channel':'Artist','category':'Music'})
        self.assertEqual(multi['status'],'review')
    def test_title_and_artist_both_required_cover_candidate_only(self):
        track={'title':'Re:Re:','artist':'結束バンド'}
        cat=[{'brand':'tj','no':'123','title':'Re:Re:','singer':'ASIAN KUNG-FU GENERATION'}]
        exact,candidates=core.match_track(track,cat,'2026-10-10');self.assertFalse(exact);self.assertEqual(len(candidates),1)
    def test_feature_artist_alias_and_future_release(self):
        track={'title':'夜明けと蛍','artist':'N-buna'}
        cat=[{'brand':'tj','no':'123','title':'夜明けと蛍','singer':'n-buna(Feat.初音ミク)','release':'2020-01-01'}]
        exact,_=core.match_track(track,cat,'2026-10-10');self.assertEqual(len(exact),1)
        cat[0]['release']='2026-11-01';exact,candidates=core.match_track(track,cat,'2026-10-10');self.assertFalse(exact);self.assertEqual(candidates[0]['reason'],'수록 예정')
        self.assertEqual(core.artist_base('Feather'),'Feather')
    def test_manual_corrections_survive_import(self):
        self.ingest([history(channel='Talk',title='Video')]);core.set_state(self.db,'corrections',{V1:{'title':'My Song','artist':'My Artist'}},'user_state');self.db.commit()
        self.ingest([history(channel='Talk',title='Updated Video')]);core.rebuild(self.db)
        self.assertEqual(core.tracks(self.db)[0]['title'],'My Song')
    def test_api_batches_and_does_not_log_key(self):
        self.ingest([history(),history(V2)])
        body={'items':[{'id':V1,'snippet':{'title':'Song','channelTitle':'Artist - Topic','categoryId':'10','description':''}}]}
        response=io.BytesIO(json.dumps(body).encode())
        with patch('pipeline.urllib.request.urlopen',return_value=response) as mocked:pipeline.enrich_api(self.db,'test-key-not-real')
        request=mocked.call_args[0][0]
        self.assertNotIn('test-key-not-real',request.full_url)
        self.assertEqual(core.video_data(self.db,V1)['category'],'Music')
        self.assertEqual(core.video_data(self.db,V2)['metadata_status'],'unavailable')
        self.assertEqual(core.get_state(self.db,'job')['done'],2)
    def test_rate_limit_circuit_breaker(self):
        self.ingest([history(),history(V2),history(V3)])
        with patch('pipeline.metadata',return_value={'video_id':V1,'metadata_status':'error','rate_limited':True}) as mocked:pipeline.enrich(self.db,workers=1)
        self.assertEqual(mocked.call_count,1);self.assertEqual(core.get_state(self.db,'job')['status'],'blocked')

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.music_patch=patch('music_metadata.ensure',return_value={'status':'ok','cards':[]})
        self.music_patch.start();self.addCleanup(self.music_patch.stop)
        self.db_patch=patch('song_databases.search',return_value={'status':'unresolved','candidates':[],'databases':[]})
        self.db_patch.start();self.addCleanup(self.db_patch.stop)
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.original=core.DB;core.DB=Path(cls.tmp.name)/'db.sqlite3'
        db=core.connect();core.import_bytes(db,json.dumps([history()]).encode(),'history.json');core.rebuild(db);db.close()
        cls.server=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.url='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();core.DB=cls.original;cls.tmp.cleanup()
    def post(self,path,payload,token=True):
        req=urllib.request.Request(self.url+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json',**({'X-App-Token':server.TOKEN} if token else {})})
        return json.load(urllib.request.urlopen(req))
    def test_public_api_and_private_files(self):
        with urllib.request.urlopen(self.url+'/api/bootstrap') as r:response=json.load(r)
        self.assertEqual(response['stats']['records'],1);self.assertNotIn('api_key',response)
        with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(self.url+'/data/karaoke.sqlite3')
        self.assertEqual(ctx.exception.code,404)
    def test_google_failure_keeps_full_title_and_search_link(self):
        db=core.connect();v=core.video_data(db,V1);query=v.get('title') or v.get('history_title','');db.close()
        with patch('google_search.search',side_effect=ValueError('timeout')) as search:
            result=self.post('/api/google-song-search',{'video_id':V1})
        self.assertEqual(result['status'],'unavailable');self.assertEqual(result['query'],query)
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlparse(result['search_url']).query)['q'],[query])
        self.assertEqual(search.call_args.args[1],query);self.assertEqual(result['candidates'],[])
    def test_bulk_targets_respect_category_and_omit_registered_songs(self):
        path=Path(self.tmp.name)/'bulk-targets.sqlite3'
        db=core.connect(path)
        rows=[history(V1,time='2026-10-09T08:00:00Z',title='target A',channel='Talk'),history(V1,title='target A',channel='Talk'),history(V2,title='target B',channel='Talk')]
        rows += [history(V3,time=f'2026-10-0{day}T08:00:00Z',title='target confirmed') for day in (6,7,8)]
        core.import_bytes(db,json.dumps(rows).encode(),'history.json');core.rebuild(db);db.close()
        with patch('core.DB',path):
            def get(minimum,status='all'):
                with urllib.request.urlopen(self.url+f'/api/recognition-targets?status={status}&q=target&min_views={minimum}') as response:return json.load(response)
            self.assertEqual([x['video_id'] for x in get(2)['items']],[V1])
            self.assertEqual([x['video_id'] for x in get(1)['items']],[V1,V2])
            self.assertEqual(get(2,'song')['total'],0)
            self.assertEqual([x['video_id'] for x in get(2,'unknown')['items']],[V1])
            self.assertEqual(get(2,'review')['total'],0)
            db=core.connect(path);db.execute('INSERT OR REPLACE INTO recognition_results VALUES (?,?)',(V1,json.dumps({'status':'ambiguous','candidates':[{'title':'Song','artist':'Artist'}]})));db.commit();db.close()
            with urllib.request.urlopen(self.url+'/api/recognition-targets?status=all&q=target&min_views=1&retry=0') as response:fresh=json.load(response)
            self.assertEqual({i['video_id'] for i in fresh['items']},{V2});self.assertEqual(fresh['skipped'],1)
            with urllib.request.urlopen(self.url+'/api/videos?status=all&q=target') as response:
                self.assertEqual({v['video_id'] for v in json.load(response)['items']},{V1,V2})
            with self.assertRaises(urllib.error.HTTPError):get(0)
    def test_review_sort_filters_before_pagination(self):
        path=Path(self.tmp.name)/'review-sort.sqlite3'
        db=core.connect(path)
        rows=[history(V1,time=f'2026-10-0{day}T08:00:00Z',title='target A',channel='Talk') for day in (6,7,8)]
        rows += [history(V2,title='target B',channel='Talk')]
        rows += [history(V3,time=f'2026-10-0{day}T08:00:00Z',title='unrelated',channel='Talk') for day in (6,7,8,9)]
        core.import_bytes(db,json.dumps(rows).encode(),'history.json');core.rebuild(db);db.close()
        with patch('core.DB',path):
            def get(sort,offset=0):
                with urllib.request.urlopen(self.url+f'/api/videos?status=unknown&q=target&sort={sort}&limit=1&offset={offset}') as response:return json.load(response)
            most=get('frequency');self.assertEqual(most['total'],2)
            self.assertEqual(most['items'][0]['video_id'],V1);self.assertEqual(most['items'][0]['history_records'],3)
            self.assertEqual(most['items'][0]['last_watch'],'2026-10-08T08:00:00Z')
            self.assertEqual(get('frequency',1)['items'][0]['video_id'],V2)
            self.assertEqual(get('recent')['items'][0]['video_id'],V2)
            with self.assertRaises(urllib.error.HTTPError) as ctx:get('bad')
            self.assertEqual(ctx.exception.code,400)
    def test_follows_queue_and_export(self):
        self.post('/api/follow',{'artist':'Artist','follow':True});db=core.connect();tid=core.tracks(db)[0]['id'];db.close()
        self.post('/api/queue',{'id':tid,'enabled':True})
        with urllib.request.urlopen(self.url+'/api/export') as r:rows=list(csv.reader(io.StringIO(r.read().decode('utf-8-sig'))))
        self.assertEqual(len(rows),2);self.assertEqual(rows[1][1],'Artist')
        self.post('/api/queue',{'id':tid,'enabled':False})
    def test_rating_accumulates_and_changes_ranking_without_hiding(self):
        path=Path(self.tmp.name)/'ratings.sqlite3'
        with patch('core.DB',path):
            db=core.connect();core.import_bytes(db,json.dumps([history(V1,title='A'),history(V2,title='B')]).encode(),'history.json');core.rebuild(db);a,b=core.tracks(db);db.close()
            self.post('/api/karaoke-rating',{'id':a['id'],'delta':-1})
            self.post('/api/karaoke-rating',{'id':a['id'],'delta':-1})
            db=core.connect();items=core.tracks(db);rated=next(t for t in items if t['id']==a['id'])
            self.assertEqual(rated['karaoke_rating'],-2);self.assertEqual(rated['karaoke_rating_score'],-.1);self.assertFalse(rated['hidden']);self.assertEqual(items[-1]['id'],a['id']);db.close()
            self.post('/api/karaoke-rating',{'id':a['id'],'delta':1})
            db=core.connect();self.assertEqual(next(t for t in core.tracks(db) if t['id']==a['id'])['karaoke_rating'],-1);db.close()

    def test_karaoke_good_toggles_score_and_is_exclusive_with_hidden(self):
        db=core.connect();tid=core.tracks(db)[0]['id'];db.close()
        self.post('/api/karaoke-good',{'id':tid,'enabled':True})
        db=core.connect();t=core.tracks(db)[0];self.assertTrue(t['karaoke_good']);self.assertEqual(t['karaoke_good_score'],.2);db.close()
        self.post('/api/hide',{'id':tid,'enabled':True})
        db=core.connect();t=core.tracks(db)[0];self.assertTrue(t['hidden']);self.assertFalse(t['karaoke_good']);db.close()
        self.post('/api/karaoke-good',{'id':tid,'enabled':True})
        db=core.connect();t=core.tracks(db)[0];self.assertFalse(t['hidden']);self.assertTrue(t['karaoke_good']);db.close()
        self.post('/api/karaoke-good',{'id':tid,'enabled':False})
        db=core.connect();self.assertFalse(core.tracks(db)[0]['karaoke_good']);db.close()

    def test_unfollow_alias_removes_artist_and_follow_bonus(self):
        self.post('/api/follow',{'artist':'Yorushika','follow':True})
        self.post('/api/follow',{'artist':'요루시카','follow':False})
        with urllib.request.urlopen(self.url+'/api/bootstrap') as response:state=json.load(response)
        self.assertNotIn('ヨルシカ',state['stats']['follows'])
        self.post('/api/follow',{'artist':'Artist','follow':True})
        with urllib.request.urlopen(self.url+'/api/bootstrap') as response:self.assertTrue(json.load(response)['tracks'][0]['followed'])
        self.post('/api/follow',{'artist':'Artist','follow':False})
        with urllib.request.urlopen(self.url+'/api/bootstrap') as response:self.assertFalse(json.load(response)['tracks'][0]['followed'])

    def test_mutation_requires_token_and_rejects_host(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.post('/api/follow',{'artist':'Bad'},False)
        self.assertEqual(ctx.exception.code,403)
        req=urllib.request.Request(self.url+'/api/bootstrap',headers={'Host':'evil.example'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code,403)
    def test_correction_and_restore(self):
        self.post('/api/correct',{'video_id':V1,'exclude':True})
        db=core.connect();self.assertEqual(len(core.tracks(db)),0);db.close()
        self.post('/api/correct',{'video_id':V1,'reset':True})
        db=core.connect();self.assertEqual(len(core.tracks(db)),1);db.close()
    def test_recognize_endpoint_saves_clicked_video_only(self):
        path=Path(self.tmp.name)/'recognition.sqlite3'
        with patch('core.DB',path):
            db=core.connect();core.import_bytes(db,json.dumps([history(V1,title='Artist「Song」',channel='Artist'),history(V2,title='Unknown',channel='Talk')]).encode(),'history.json');core.rebuild(db);db.close()
            result=self.post('/api/recognize',{'video_id':V1});self.assertEqual(result['status'],'recognized')
            unresolved=self.post('/api/recognize',{'video_id':V2});self.assertEqual(unresolved['status'],'unresolved')
            db=core.connect();edits=core.get_state(db,'corrections',{},'user_state');self.assertEqual(set(edits),{V1});self.assertEqual(core.tracks(db)[0]['sources'],['auto_recognition']);db.close()
    def test_recognize_fetches_missing_original_then_saves_cover_only(self):
        path=Path(self.tmp.name)/'original-http.sqlite3'
        with patch('core.DB',path),patch('server.load_key',return_value='test-key'):
            db=core.connect();core.import_bytes(db,json.dumps([history(V1,title='Song Cover',channel='Singer')]).encode(),'history.json')
            video=core.video_data(db,V1);video['description']='Original: https://youtu.be/'+V2;core.save_video(db,video);db.commit();core.rebuild(db);db.close()
            item={'id':V2,'snippet':{'title':'Artist - Song','channelTitle':'Artist','description':'Music : Artist','categoryId':'10'}}
            with patch('original_metadata.request_videos',return_value={'status':'ok','items':[item]}) as request:
                result=self.post('/api/recognize',{'video_id':V1})
                self.assertEqual(result['status'],'recognized');self.assertEqual(result['original_metadata']['fetched'],1)
                self.post('/api/recognize',{'video_id':V1});self.assertEqual(request.call_count,1)
            db=core.connect();self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
            self.assertEqual(core.tracks(db)[0]['video_ids'],[V1]);self.assertEqual(core.get_state(db,'corrections',{},'user_state')[V1]['original_video_id'],V2);db.close()
            with urllib.request.urlopen(self.url+'/api/videos?status=all') as response:videos=json.load(response)
            self.assertEqual(videos['items'],[])

    def test_different_song_api_dismisses_and_restores_pair(self):
        path=Path(self.tmp.name)/'different-http.sqlite3'
        with patch('core.DB',path):
            db=core.connect();core.import_bytes(db,json.dumps([history(V1,title='Song name'),history(V2,title='Song names')]).encode(),'history.json');core.rebuild(db);a,b=core.tracks(db);db.close()
            self.post('/api/different-songs',{'source':a['id'],'target':b['id']})
            with urllib.request.urlopen(self.url+'/api/merge-candidates') as response:result=json.load(response)
            self.assertEqual(result['candidates'],[]);self.assertEqual(len(result['different']),1)
            self.post('/api/different-songs',{'source':b['id'],'target':a['id'],'restore':True})
            with urllib.request.urlopen(self.url+'/api/merge-candidates') as response:self.assertEqual(len(json.load(response)['candidates']),1)

    def test_merge_and_unmerge_http_preserve_queue(self):
        path=Path(self.tmp.name)/'merge-http.sqlite3'
        with patch('core.DB',path):
            db=core.connect();core.import_bytes(db,json.dumps([history(V1,title='Song A'),history(V2,title='Song B')]).encode(),'history.json');core.rebuild(db)
            a,b=core.tracks(db);core.set_state(db,'queue',[a['id']],'user_state');db.commit();db.close()
            change=self.post('/api/merge',{'source':a['id'],'target':b['id']})
            with urllib.request.urlopen(self.url+'/api/bootstrap') as response:merged=json.load(response)
            self.assertEqual(len(merged['tracks']),1);self.assertEqual(merged['queue'],[b['id']])
            self.post('/api/queue',{'id':b['id'],'enabled':False})
            with urllib.request.urlopen(self.url+'/api/bootstrap') as response:self.assertEqual(json.load(response)['queue'],[])
            self.post('/api/unmerge',{'id':change['id']})
            db=core.connect();self.assertEqual(len(core.tracks(db)),2);db.close()

if __name__=='__main__':unittest.main(verbosity=2)
