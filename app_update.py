"""Public release updater; user data never enters the download or replacement set."""
import hashlib,json,os,re,shutil,subprocess,sys,threading,time,urllib.request,zipfile
from pathlib import Path
import core

VERSION='0.1.16'
REPO='lemoncube7/next-song-local'
STATE={'status':'idle','version':VERSION}
LOCK=threading.Lock()
def version_tuple(value):
    if not re.fullmatch(r'v?\d+\.\d+\.\d+',value):raise ValueError('지원하지 않는 버전 형식입니다.')
    return tuple(map(int,value.lstrip('v').split('.')))
def fetch(url):
    if not url.startswith(('https://api.github.com/repos/'+REPO+'/', 'https://github.com/'+REPO+'/releases/download/')):raise ValueError('업데이트 주소 오류')
    return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'NextSong-Updater','Accept':'application/vnd.github+json'}),timeout=30)
def check():
    with fetch('https://api.github.com/repos/'+REPO+'/releases/latest') as response:release=json.load(response)
    latest=release['tag_name'];available=version_tuple(latest)>version_tuple(VERSION)
    assets={a['name']:a for a in release.get('assets',[])}
    if 'NextSong-Windows-x64.zip' not in assets or 'SHA256SUMS.txt' not in assets:raise ValueError('업데이트 파일이 없는 릴리스입니다.')
    STATE.update(status='available' if available else 'current',version=VERSION,latest=latest,available=available,
                 install_supported=bool(getattr(sys,'frozen',False)),reason='')
    return assets
def extract(archive,stage):
    allowed={'NextSong.exe','_internal','tools','README.md','NOTICE.md'}
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist())>800*1024*1024:raise ValueError('업데이트 압축 크기 초과')
        for item in z.infolist():
            parts=item.filename.replace('\\','/').split('/')
            if parts[0]!='NextSong' or '..' in parts or any(':' in p for p in parts):raise ValueError('업데이트 경로 오류')
            if len(parts)<2 or parts[1] not in allowed:raise ValueError('업데이트에 허용하지 않은 파일이 있습니다.')
            if (item.external_attr>>16)&0o170000==0o120000:raise ValueError('링크 파일은 허용하지 않습니다.')
            target=stage.joinpath(*parts[1:])
            if item.is_dir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(item) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
    if not (stage/'NextSong.exe').is_file() or not (stage/'_internal').is_dir():raise ValueError('실행 파일이 없는 업데이트입니다.')
def start():
    if not getattr(sys,'frozen',False):raise ValueError('소스 실행 환경에서는 자동 교체를 지원하지 않아요. Windows 실행 패키지에서 사용하세요.')
    if not LOCK.acquire(False):return dict(STATE)
    def work():
        try:
            assets=check()
            if not STATE['available']:return
            STATE.update(status='downloading')
            folder=core.ROOT/'.updates';folder.mkdir(exist_ok=True)
            with fetch(assets['SHA256SUMS.txt']['browser_download_url']) as r:sums=r.read(4096).decode('utf8')
            match=re.search(r'(?m)^([a-fA-F0-9]{64})\s+\*?NextSong-Windows-x64.zip\s*$',sums)
            if not match:raise ValueError('업데이트 검증값이 없습니다.')
            archive=folder/'download.zip';digest=hashlib.sha256();size=0
            with fetch(assets['NextSong-Windows-x64.zip']['browser_download_url']) as r,archive.open('wb') as f:
                while chunk:=r.read(1024*1024):
                    size+=len(chunk)
                    if size>150*1024*1024:raise ValueError('업데이트 다운로드 크기 초과')
                    digest.update(chunk);f.write(chunk);STATE['downloaded_bytes']=size
            if digest.hexdigest()!=match[1].lower():raise ValueError('업데이트 파일 검증에 실패했어요.')
            stage=folder/('stage-'+STATE['latest']);stage.mkdir(exist_ok=True);extract(archive,stage)
            STATE.update(status='ready',stage=str(stage))
        except Exception as exc:STATE.update(status='error',reason=str(exc) if isinstance(exc,ValueError) else '업데이트 조회·다운로드 실패: '+type(exc).__name__)
        finally:LOCK.release()
    STATE['status']='checking';threading.Thread(target=work,daemon=True).start();return dict(STATE)
def apply(port):
    if STATE.get('status')!='ready' or not getattr(sys,'frozen',False):raise ValueError('준비된 업데이트가 없습니다.')
    script=core.ROOT/'.updates'/'apply.ps1'
    script.write_text(HELPER,encoding='utf-8-sig')
    subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-Root',str(core.ROOT),'-Stage',STATE['stage'],'-AppPid',str(os.getpid()),'-Port',str(port)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    STATE.update(status='restarting')
    threading.Timer(1,lambda:os._exit(0)).start()
    return {'status':'restarting'}

HELPER=r'''param([string]$Root,[string]$Stage,[int]$AppPid,[int]$Port)
$ErrorActionPreference='Stop'
$rootPath=[IO.Path]::GetFullPath($Root)
$stagePath=[IO.Path]::GetFullPath($Stage)
if(-not $stagePath.StartsWith(($rootPath+'\.updates\'),[StringComparison]::OrdinalIgnoreCase)){throw 'Invalid stage'}
$names=@('NextSong.exe','_internal','tools','README.md','NOTICE.md')
$backup=Join-Path $rootPath ('.updates\backup-'+[Guid]::NewGuid().ToString('N'))
$moved=@();$installed=@();$newProcess=$null
try {
 if(Get-Process -Id $AppPid -ErrorAction SilentlyContinue){Wait-Process -Id $AppPid -Timeout 60}
 New-Item -ItemType Directory -Path $backup | Out-Null
 foreach($name in $names){
  $target=Join-Path $rootPath $name;$source=Join-Path $stagePath $name
  if(Test-Path -LiteralPath $target){Move-Item -LiteralPath $target -Destination (Join-Path $backup $name);$moved+=$name}
  if(Test-Path -LiteralPath $source){Move-Item -LiteralPath $source -Destination $target;$installed+=$name}
 }
 $newProcess=Start-Process -FilePath (Join-Path $rootPath 'NextSong.exe') -ArgumentList @('--port',"$Port") -WorkingDirectory $rootPath -WindowStyle Hidden -PassThru
 $healthy=$false
 for($i=0;$i -lt 90;$i++){
  Start-Sleep -Seconds 1
  try{$s=Invoke-RestMethod "http://127.0.0.1:$Port/api/update-status" -TimeoutSec 2;if($s.version -eq (Split-Path $stagePath -Leaf).Substring(7)){$healthy=$true;break}}catch{}
 }
 if(-not $healthy){throw 'New version failed health check'}
 'Update completed' | Set-Content -LiteralPath (Join-Path $rootPath '.updates\result.txt')
} catch {
 $failure=$_.Exception.Message
 if($newProcess -and -not $newProcess.HasExited){Stop-Process -Id $newProcess.Id}
 foreach($name in $installed){$target=Join-Path $rootPath $name;if(Test-Path -LiteralPath $target){Move-Item -LiteralPath $target -Destination (Join-Path $stagePath $name)}}
 foreach($name in $moved){Move-Item -LiteralPath (Join-Path $backup $name) -Destination (Join-Path $rootPath $name)}
 ('Update failed; previous version restored: '+$failure) | Set-Content -LiteralPath (Join-Path $rootPath '.updates\result.txt')
 if($moved.Count -gt 0){Start-Process -FilePath (Join-Path $rootPath 'NextSong.exe') -ArgumentList @('--port',"$Port") -WorkingDirectory $rootPath -WindowStyle Hidden}
}
'''
