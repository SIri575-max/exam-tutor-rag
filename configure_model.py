"""Local-only credential setup and an explicit, textbook-free connection check."""
import argparse
from datetime import datetime, timedelta, timezone
import getpass
import json
import os
import sys
from pathlib import Path
import tempfile
import urllib.error
from urllib.parse import urlparse
from tutor_provider import configuration, transport

ROOT=Path(__file__).resolve().parent
NAMES=['TUTOR_ENABLE_LLM','TUTOR_BASE_URL','TUTOR_MODEL','TUTOR_API_KEY']


def validate(values):
    missing=[key for key in NAMES[1:] if not values.get(key,'').strip()]
    if missing:raise ValueError('尚未填写：'+', '.join(missing))
    if values.get('TUTOR_ENABLE_LLM') not in {'0','1'}:raise ValueError('TUTOR_ENABLE_LLM应为0或1')
    for key in NAMES:
        value=values.get(key,'')
        if any(ch in value for ch in ['\n','\r','\x00','"',"'"]):raise ValueError(key+' 包含无效字符')
    parsed=urlparse(values['TUTOR_BASE_URL'])
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname or not (
        parsed.scheme=='https' or parsed.scheme=='http' and parsed.hostname in {'127.0.0.1','localhost'}):
        raise ValueError('Base URL 应是HTTPS服务端点，或本机HTTP端点；不能带密码、查询参数或片段')
    if parsed.path.rstrip('/').endswith('/chat/completions'):
        raise ValueError('请填写Base URL，去掉末尾的/chat/completions')
    if any(x in values['TUTOR_BASE_URL'] for x in ['{','}','<','>']):
        raise ValueError('服务地址仍有占位符，请从控制台复制实际端点')
    if any(ch.isspace() for ch in values['TUTOR_MODEL']+values['TUTOR_API_KEY']):
        raise ValueError('模型名或密钥中不能包含空白字符')


def save(values,path=None):
    validate(values)
    target=Path(path) if path else ROOT/'.env'
    original=target.read_text(encoding='utf-8-sig') if target.exists() else ''
    lines=[];done=set()
    for line in original.splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key=line.split('=',1)[0].strip()
            if key in NAMES:
                if key not in done:lines.append(key+'='+values[key]);done.add(key)
                continue
        lines.append(line)
    lines.extend(key+'='+values[key] for key in NAMES if key not in done)
    # A temporary file stays in an ignored private folder, never beside tracked sources.
    private=target.parent/'data/private/model-setup';private.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=private,delete=False,suffix='.env') as stream:
            temp=Path(stream.name);stream.write('\n'.join(lines)+'\n')
        os.replace(temp,target)
    finally:
        if temp and temp.exists():temp.unlink()


def safe_status(values=None):
    values=configuration() if values is None else values
    return {'enabled':values.get('TUTOR_ENABLE_LLM')=='1',
            'missing_fields':[key for key in NAMES[1:] if not values.get(key,'').strip()],
            'environment_overrides_present':[key for key in NAMES if key in os.environ],
            'key_present':bool(values.get('TUTOR_API_KEY'))}


def connection_test(values=None,request=transport):
    values=configuration() if values is None else values
    validate(values)
    if values.get('TUTOR_ENABLE_LLM')!='1':raise ValueError('模型未启用；先在本机设置TUTOR_ENABLE_LLM=1')
    body={'model':values['TUTOR_MODEL'],'messages':[{'role':'user','content':'这是接口连通性测试，请只回复 OK。'}],
          'stream':False,'temperature':0,'max_tokens':128}
    result={'created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'textbook_sent':False,'live_call_verified':False,'connected':False,'generation_ready':False}
    try:
        response=request(values['TUTOR_BASE_URL'].rstrip('/')+'/chat/completions',body,values['TUTOR_API_KEY'])
        message=response['choices'][0]['message'];text=message.get('content')
        result.update(connected=True,live_call_verified=request is transport,
                      generation_ready=isinstance(text,str) and bool(text.strip()),
                      response_model=response.get('model'),usage=response.get('usage',{}),
                      status='response_received' if text else 'response_without_final_text')
    except urllib.error.HTTPError as error:
        result.update(status='provider_http_error',http_status=error.code)
    except (OSError,ValueError,KeyError,IndexError,TypeError):result['status']='connection_or_response_failed'
    return result


def interactive():
    if not sys.stdin.isatty():raise ValueError('请在交互式终端运行向导，或直接编辑本机.env；此处不读取密钥')
    current=configuration()
    print('本机模型配置：输入控制台的Base URL和已开通模型名；密钥输入不回显。')
    print('保存后启用模型，但本向导不会自动请求外部服务或发送教材。')
    values={}
    for key,label in [('TUTOR_BASE_URL','Base URL（不包含/chat/completions）'),('TUTOR_MODEL','模型名称')]:
        hint=' [回车保留已有值]' if current.get(key) else ''
        values[key]=input(label+hint+': ').strip() or current.get(key,'')
    hint=' [回车保留已有密钥]' if current.get('TUTOR_API_KEY') else ''
    values['TUTOR_API_KEY']=getpass.getpass('API Key'+hint+': ').strip() or current.get('TUTOR_API_KEY','')
    values['TUTOR_ENABLE_LLM']='1';save(values)
    print('已保存到项目本机.env。刷新Demo即可读取；未显示密钥，也未调用模型。')
    if any(key in os.environ for key in NAMES):print('注意：当前进程有同名环境变量，应用会优先使用它们。')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--test',action='store_true',
        help='Make one real, short provider request without any textbook content.')
    args=parser.parse_args()
    try:
        if args.check:print(json.dumps(safe_status(),ensure_ascii=False,indent=2));return 0
        if args.test:
            result=connection_test();folder=ROOT/'data/private/model-setup';folder.mkdir(parents=True,exist_ok=True)
            (folder/'connection-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['generation_ready'] else 1
        interactive();return 0
    except (ValueError,EOFError,KeyboardInterrupt) as error:
        print(str(error) if isinstance(error,ValueError) else '未完成输入，配置未保存。');return 1


if __name__=='__main__':raise SystemExit(main())
