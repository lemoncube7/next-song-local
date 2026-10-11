"""Windows entry point; the Python runtime is bundled in the release."""
import json,sys,urllib.request,webbrowser
import server

if __name__=='__main__':
    port=sys.argv[sys.argv.index('--port')+1] if '--port' in sys.argv else '8765'
    url='http://127.0.0.1:'+port
    no_open='--no-open' in sys.argv
    if no_open:sys.argv.remove('--no-open')
    try:
        state=json.load(urllib.request.urlopen(url+'/api/stats',timeout=2))
        if state.get('app')=='local-karaoke-v1':
            if not no_open:webbrowser.open(url)
            sys.exit(0)
    except (OSError,ValueError):pass
    if not no_open and '--open' not in sys.argv:sys.argv.append('--open')
    server.main()
