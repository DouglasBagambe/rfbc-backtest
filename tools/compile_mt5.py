"""Compile with the installed MetaEditor; unique log path prevents stale success."""
import argparse,hashlib,os,re,shutil,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--install',action='store_true');p.add_argument('--source',default='Fx101GoatBridge.mq5');a=p.parse_args()
root=Path(__file__).resolve().parents[1]
prefix=Path(os.getenv('MT5_WINEPREFIX','/home/db/.mt5'))
job=f'Fx101Validation{time.time_ns()}'
work=prefix/'drive_c'/job;work.mkdir()
source=root/'mt5'/a.source;copied=work/source.name;shutil.copyfile(source,copied)
shutil.copytree(root/'mt5/include',work/'include',dirs_exist_ok=True)
dependencies=[]
if a.source=='DnbDemoObserver.mq5':
    dependency=root/'mt5/Fx101GoatBridge.mq5'
    shutil.copyfile(dependency,work/dependency.name)
    dependencies.append(dependency)
inputs=[source]+dependencies+list((root/'mt5/include').glob('*.mqh'))
input_bytes={path:path.read_bytes() for path in inputs}
log=work/'compile.log';binary=work/(source.stem+'.ex5')
env={**os.environ,'WINEPREFIX':str(prefix),'WINEDEBUG':'-all'}
subprocess.run(['wine',str(prefix/'drive_c/Program Files/MetaTrader 5/MetaEditor64.exe'),'/portable',
                f'/compile:C:\\{job}\\{source.name}',f'/log:C:\\{job}\\compile.log'],env=env,timeout=60,capture_output=True)
if not log.exists(): raise SystemExit('No compiler log: compilation not verified')
text=log.read_text(encoding='utf-16')
if not re.search(r'Result: 0 errors, 0 warnings,',text) or not binary.exists() or copied.read_bytes()!=source.read_bytes() or any(path.read_bytes()!=data for path,data in input_bytes.items()):
    print(text);raise SystemExit('Compiler failed or source changed during compilation')
includes=''.join('INCLUDE_SHA256 '+str(p.relative_to(root))+': '+hashlib.sha256(p.read_bytes()).hexdigest()+'\n' for p in sorted((root/'mt5/include').glob('*.mqh')))
includes+=''.join('DEPENDENCY_SHA256 '+str(p.relative_to(root))+': '+hashlib.sha256(p.read_bytes()).hexdigest()+'\n' for p in dependencies)
proof=includes+'SOURCE_SHA256='+hashlib.sha256(source.read_bytes()).hexdigest()+'\nEX5_SHA256='+hashlib.sha256(binary.read_bytes()).hexdigest()+'\n'+text
(root/'docs/evidence'/('mql5-compile.log' if a.source=='Fx101GoatBridge.mq5' else source.stem+'-compile.log')).write_text(proof)
print(text.strip().splitlines()[-1])
if a.install:
    target=prefix/'drive_c/Program Files/MetaTrader 5/MQL5/Experts/Fx101';target.mkdir(exist_ok=True)
    shutil.copytree(root/'mt5/include',target/'include',dirs_exist_ok=True)
    shutil.copyfile(source,target/source.name);shutil.copyfile(binary,target/binary.name)
    for dependency in dependencies:shutil.copyfile(dependency,target/dependency.name)
    print('Installed validated source and EX5; existing chart must reload to use this binary.')
