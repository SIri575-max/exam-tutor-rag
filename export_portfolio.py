"""Export a local code-review package with an explicit allowlist, never secrets/corpus."""
import hashlib
import argparse
import json
from pathlib import Path
import re
import zipfile
from sync_sources import ROOT
from tutor_provider import configuration


def build(version='v1.1',date='20261028',release_folder='data/private/v1.1-release'):
    if not re.fullmatch(r'v\d+(?:\.\d+)*',version) or not re.fullmatch(r'\d{8}',date):raise ValueError('无效版本或日期')
    files={}
    for pattern in ['*.py','*.js','*.html','*.css','*.ps1','requirements*.txt']:
        for path in ROOT.glob(pattern):files[path.name]=path.read_bytes()
    for name in ['README.md','资料入库说明.md','.env.example','.gitignore']:
        files[name]=(ROOT/name).read_bytes()
    for folder in ['tests','docs','assets/katex','evaluation']:
        for path in (ROOT/folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                files[path.relative_to(ROOT).as_posix()]=path.read_bytes()
    # Preserve configuration structure without the user's absolute source locations.
    def sanitized(value):
        if isinstance(value,dict):return {k:sanitized(v) for k,v in value.items()}
        if isinstance(value,list):return [sanitized(v) for v in value]
        if isinstance(value,str) and re.match(r'^[A-Za-z]:[\\/]',value):return 'C:/YOUR_DATA/'+Path(value).name
        return value
    for name in ['source_config.json','textbook_source_config.json']:
        value=json.loads((ROOT/name).read_text(encoding='utf-8-sig'))
        files[name.replace('.json','.example.json')]=json.dumps(sanitized(value),ensure_ascii=False,indent=2).encode()
    release=(ROOT/release_folder).resolve()
    if not release.is_relative_to((ROOT/'data/private').resolve()):raise ValueError('代码包必须保存在本项目私有交付目录')
    release.mkdir(parents=True,exist_ok=True)
    files['results/v1-summary.json']=(release/'manifest.json').read_bytes()
    screenshot=release/'portfolio-overview.png'
    if screenshot.exists():files['docs/portfolio-overview.png']=screenshot.read_bytes()
    files['源码包说明.md']=('''# RAG 代码审阅包

本包供本地审阅和作品集归档，未自动公开发布。包含项目源码、测试、依赖清单、运行说明、人工编写的开发输入及实际评测摘要。

不含用户原书PDF、完整解析题库、向量数据库、题图、模型权重、Python环境或API密钥。代码中的教学样板和小型测试不能替代完整题库。

配置模板文件请复制为无.example后缀的JSON并填入自己有权使用的资料路径；模型配置将.env.example复制为.env，在本机输入密钥。完整资料处理步骤见README和docs/V1_交付说明.md。本包不是无需数据即可启动的完整题库镜像。

数学正确性和独立教师审核仍待完成。请按docs/面试与复现练习.md亲自复现，再说明自己掌握的范围。SHA256清单用于检查解压文件是否完整，不构成事实审核。
''').encode()
    key=configuration().get('TUTOR_API_KEY','').encode()
    if key and any(key in raw for raw in files.values()):raise ValueError('导出内容中发现密钥，已停止')
    if any('.env' in Path(name).parts for name in files):raise ValueError('禁止导出私有环境配置')
    inventory={name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in sorted(files.items())}
    files['SHA256.json']=json.dumps(inventory,ensure_ascii=False,indent=2).encode()
    target=release/('exam-tutor-rag-'+version+'-code-'+date+'.zip')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in sorted(files.items()):archive.writestr(name,raw)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for name,meta in inventory.items():assert hashlib.sha256(archive.read(name)).hexdigest()==meta['sha256']
    result={'archive':target.name,'files':len(files),'bytes':target.stat().st_size,
            'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'secret_scan_passed':True,
            'excludes':['private .env','original PDFs','parsed corpus and vectors','photo jobs','model weights','runtime environments'],
            'boundary':'Code review archive; full demo needs separately authorized private data and local runtime.'}
    (release/'code-package.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--version',default='v1.1');parser.add_argument('--date',default='20261028');parser.add_argument('--release-folder',default='data/private/v1.1-release')
    args=parser.parse_args();build(args.version,args.date,args.release_folder)
