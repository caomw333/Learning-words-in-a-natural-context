"""Loopback-only vocabulary service. Standard library, atomic local records, no cloud storage."""
import copy
import hashlib
import subprocess
import json
import os
import random
import re
import threading
import urllib.request
import urllib.error
import urllib.parse
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('VOCAB_DATA_DIR', str(ROOT / 'data')))
DATA.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()
LOOKUP_LOCK = threading.Lock()
SPEECH_LOCK = threading.Lock()
RNG = random.SystemRandom()
DEFAULT_CONFIG = {'baseUrl':'https://api.deepseek.com','model':'deepseek-v4-flash','apiKey':''}
THEMES = ['a village library rescue','a lost camera on a train','a school radio programme','an unexpected cooking contest','a community garden experiment','a rainy mountain trip','a small museum mystery','a student repairing bicycles','a neighbourhood science fair','a seaside volunteer team','a theatre rehearsal','a first day at a summer job']

def now(): return datetime.now(timezone.utc).isoformat()
def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else copy.deepcopy(default)
def atomic(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)

class Store:
    def __init__(self, directory=DATA, vocabulary=None):
        self.directory=Path(directory); self.directory.mkdir(parents=True,exist_ok=True)
        self.vocab = vocabulary or read(ROOT/'data/vocabulary.json',{})
        self.state = read(self.directory/'state.json',{'version':1,'rounds':[],'overrides':{},'statuses':{}})
        self.config = read(self.directory/'config.local.json',DEFAULT_CONFIG)
        recovered=[]
        for r in self.state['rounds']:
            if r['status']=='generating':
                r['status']='interrupted'; r['error']='程序曾中断；已完成短文和请求记录已保留。可继续未完成部分。'
                for req in r['requests']:
                    if req['status']=='sending': req['status']='unknown'
                recovered.append(r)
        self.save()
        for r in recovered: self.archive(r)

    def save(self):
        atomic(self.directory/'state.json',self.state)

    def archive(self,r):
        self.save()
        folder=self.directory/'rounds'; folder.mkdir(exist_ok=True)
        atomic(folder/(r['id']+'.json'),r)
        lines=[f"# 第 {r['number']} 轮",f"创建：{r['createdAt']}",f"状态：{r['status']}","",'## 输入词表（实际顺序）']
        lines += [f"- {w['id']} {w['word']} — {w['meaning']}" for w in r['words']]
        for i,a in enumerate(r['articles']):
            lines += ['',f"## {i+1}. {a['title']}",a['body'],'','### 词汇注释']
            lines += [f"- {w['word']} — {w['meaning']}（正文 {a['counts'].get(w['id'],0)} 次）" for w in r['words'] if a['counts'].get(w['id'],0)]
        lines += ['',f"本轮实际覆盖 {len(coverage(r))} / {len(r['words'])} 个目标词。",'每读懂一个句子，都是在向四级更进一步。']
        path=folder/(r['id']+'.md'); tmp=path.with_suffix('.md.tmp'); tmp.write_text('\n\n'.join(lines),encoding='utf-8'); os.replace(tmp,path)

    def words(self):
        stats={w['id']:{'selectedCount':0,'occurrences':0,'roundCount':0,'lastSeen':None} for w in self.vocab['words']}
        for r in self.state['rounds']:
            for req in r['requests']:
                for wid in req['wordIds']:
                    if wid in stats: stats[wid]['selectedCount']+=1
            hits=coverage(r)
            for wid,c in hits.items():
                if wid in stats:
                    stats[wid]['occurrences']+=c; stats[wid]['roundCount']+=1
                    last=max(a.get('createdAt',r['createdAt']) for a in r['articles'] if a['counts'].get(wid,0))
                    stats[wid]['lastSeen']=max(stats[wid]['lastSeen'] or '',last)
        output=[]
        for original in self.vocab['words']:
            w={**original,**self.state['overrides'].get(original['id'],{}),**stats[original['id']]}
            w['status']=self.state['statuses'].get(w['id']) or ('seen' if w['occurrences'] else 'new')
            if w['status']=='new' and w['occurrences']: w['status']='seen'
            output.append(w)
        return output

    def public(self):
        return {'words':self.words(),'rounds':self.state['rounds'],'source':self.vocab['source'],
                'config':{'baseUrl':self.config['baseUrl'],'model':self.config['model'],'hasKey':bool(self.config['apiKey'])}}

def variants(word):
    # Only explicitly listed spelling variants, never guessed stemming.
    result=[]
    for part in word.split('/'):
        if re.search(r'\([a-z]+\)',part):
            result += [re.sub(r'\([a-z]+\)','',part),part.replace('(','').replace(')','')]
        else: result.append(part)
    return [v.lower() for v in result if re.fullmatch(r'[A-Za-z]+(?:[- ][A-Za-z]+)*',v)]

def count_word(body,word):
    return sum(len(re.findall(r"(?<![A-Za-z-])"+re.escape(v)+r"(?![A-Za-z-])",body,re.I)) for v in set(variants(word)))
def coverage(r):
    counts={}
    for a in r['articles']:
        for wid,c in a['counts'].items():
            if c: counts[wid]=counts.get(wid,0)+c
    return counts
def shuffle(words, previous=None):
    result=list(words); RNG.shuffle(result)
    if len(result)>1 and [w['id'] for w in result]==previous: result=result[1:]+result[:1]
    return result

def select_words(words,count,old_percent,start,end):
    available=[w for w in words if not w['review'] and variants(w['word']) and start<=int(w['id'])<=end and w['status']!='mastered']
    old=[w for w in available if w['occurrences']>0]; new=[w for w in available if not w['occurrences']]
    RNG.shuffle(old); RNG.shuffle(new)
    old.sort(key=lambda w:(0 if w['status']=='review' else 1,w['roundCount'],w['lastSeen'] or ''))
    wanted_old=int(count*old_percent/100+0.5)
    chosen_old=old[:wanted_old]; chosen_new=new[:count-len(chosen_old)]
    if len(chosen_old)+len(chosen_new)<count: chosen_old=old[:count-len(chosen_new)]
    chosen=chosen_old+chosen_new
    if not chosen: raise ValueError('这个范围没有可练习的词。请扩大范围，或先核对词条。')
    return shuffle(chosen)

def validate_article(obj,words,previous):
    if not isinstance(obj,dict) or not isinstance(obj.get('title'),str) or not isinstance(obj.get('body'),str):
        raise ValueError('返回格式不正确，需要 title 和 body 字符串。原始回复已保存。')
    title=obj['title'].strip(); body=obj['body'].strip()
    if not title or not body or len(body)>18000: raise ValueError('返回的短文为空或过长。原始回复已保存。')
    wc=len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*",body))
    counts={w['id']:count_word(body,w['word']) for w in words}
    issues=[]
    if not 150<=wc<=200: issues.append(f'篇幅 {wc} 词，要求 150–200 词')
    if re.search(r'[\u4e00-\u9fff]',body): issues.append('正文含中文，请保持英文短文')
    normalized=lambda s: re.sub(r'[^a-z]+',' ',s.lower()).strip()
    if any(normalized(body)==normalized(a['body']) for a in previous): issues.append('正文与历史短文完全相同')
    return {'id':uuid.uuid4().hex[:12],'title':title[:240],'body':body,'wordCount':wc,'counts':counts,'issues':issues,'copied':False,'createdAt':now()}

def make_messages(r,group,prior,repair=False):
    history=[{'title':a['title'],'opening':a['body'][:280]} for a in prior][-60:]
    return [{'role':'system','content':
        'You are a CET-4 foundation reading tutor for a Chinese high-school graduate with 2500–3000 words. '
        'Write a natural, coherent NEW English story of 150–200 English words, with simple grammar and concrete contextual clues for every target word. '
        'Use ALL assigned target words in their supplied order of first appearance; use the exact spelling or one explicitly listed alternative, not inflections. '
        'Do not list words mechanically. Do not reuse any supplied previous plot, characters or setting. '
        'Return ONLY a JSON object with two string fields: title (English title), body (English paragraphs separated by \\n\\n). No markdown, translations or vocabulary list in body.'},
        {'role':'user','content':json.dumps({'round':r['number'],'theme':r['theme'],'task':'Write a new supplementary story' if repair else 'Write a new story','targetWords':[{'word':w['word'],'meaning':w['meaning']} for w in group],'previousStoriesToAvoid':history},ensure_ascii=False)}]

def api_request(config,payload):
    req=urllib.request.Request(config['baseUrl'].rstrip('/')+'/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+config['apiKey'],'Content-Type':'application/json'},method='POST')
    # No redirects: an endpoint must never forward the bearer key to another host.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): return None
    with urllib.request.build_opener(NoRedirect).open(req,timeout=180) as response:
        raw=response.read(2_000_001)
        if len(raw)>2_000_000: raise ValueError('API 返回内容过大。')
        return json.loads(raw)

def run_generation(store,rid,groups,config):
    try:
        for group in groups:
            with LOCK:
                r=next(r for r in store.state['rounds'] if r['id']==rid)
                if r.get('stopRequested'): break
                prior=[a for rr in store.state['rounds'] for a in rr['articles']]
                messages=make_messages(r,group,prior,bool(r['articles']))
                payload={'model':config['model'],'messages':messages,'max_tokens':4096,'stream':False,'response_format':{'type':'json_object'}}
                if config['model'].startswith('deepseek-v4'): payload['thinking']={'type':'disabled'}
                req={'id':uuid.uuid4().hex,'wordIds':[w['id'] for w in group],'submittedAt':now(),'endpoint':config['baseUrl']+'/chat/completions','payload':payload,'status':'sending'}
                r['requests'].append(req); store.archive(r)
            try:
                response=api_request(config,payload)
                with LOCK:
                    req['response']=response; req['status']='received'; store.archive(r)
                choices=response.get('choices')
                if not choices or not isinstance(choices,list): raise ValueError('API 缺少 choices，完整回复已留档。')
                content=choices[0].get('message',{}).get('content')
                if not isinstance(content,str): raise ValueError('API 未返回文本。完整回复已留档。')
                clean=re.sub(r'^```(?:json)?\s*|\s*```$','',content.strip())
                obj=json.loads(clean)
                article=validate_article(obj,r['words'],prior)
                missing=[w['word'] for w in group if not article['counts'].get(w['id'])]
                if missing: article['issues'].append('本篇分配词遗漏：'+', '.join(missing))
                first_positions=[]
                for w in group:
                    found=[m.start() for v in variants(w['word']) for m in re.finditer(r'(?<![A-Za-z-])'+re.escape(v)+r'(?![A-Za-z-])',article['body'],re.I)]
                    if found: first_positions.append(min(found))
                if first_positions!=sorted(first_positions): article['issues'].append('目标词首次出现顺序与输入不一致')
                if choices[0].get('finish_reason')=='length': article['issues'].append('API 输出达到长度上限，可能被截断')
                with LOCK:
                    r['articles'].append(article); req['status']='done'; req['articleId']=article['id']; store.archive(r)
            except urllib.error.HTTPError as e:
                with LOCK: req['status']='failed'; req['error']=f'API HTTP {e.code}（检查地址、模型、Key 或余额）'
                raise ValueError(req['error']) from None
            except (TimeoutError,urllib.error.URLError) as e:
                with LOCK: req['status']='unknown'
                raise ValueError('网络请求未确认完成，可能已产生用量。未自动重试；可检查服务商记录后继续。') from None
            except (ValueError,KeyError,TypeError) as e:
                with LOCK: req['status']='invalid'; req['error']=str(e)
                raise
        with LOCK:
            r=next(r for r in store.state['rounds'] if r['id']==rid)
            current_issues=[issue for a in r['articles'] for issue in a['issues'] if not issue.startswith('本篇分配词遗漏')]
            r['status']='complete' if len(coverage(r))==len(r['words']) and not current_issues else 'needs_attention'
            r['stopRequested']=False; r['finishedAt']=now(); store.archive(r)
    except Exception as e:
        with LOCK:
            r=next(r for r in store.state['rounds'] if r['id']==rid)
            r['status']='needs_attention'; r['error']=str(e).replace(config['apiKey'],'[hidden]') if config['apiKey'] else str(e)
            store.archive(r)

STORE=None
def speech_audio(store,b):
    with LOCK:
        article=next((a for r in store.state['rounds'] for a in r['articles'] if a['id']==b.get('articleId')),None)
        if not article: raise ValueError('短文不存在')
        text=article['body']
    if os.name!='nt': raise ValueError('本地音频使用 Windows 英语语音；其他系统请使用支持朗读的浏览器')
    token=hashlib.sha256(('windows-english-v1:'+text).encode()).hexdigest()
    folder=store.directory/'audio';folder.mkdir(exist_ok=True)
    output=folder/(token+'.wav')
    with SPEECH_LOCK:
        if not output.exists():
            temp=folder/(token+'.tmp.wav')
            try:
                result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/speak.ps1'),'-OutputFile',str(temp)],input=text.encode('utf-8'),capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode or not temp.exists() or temp.stat().st_size<44:
                    raise ValueError('Windows 英语语音不可用，请安装英语语音包或使用支持朗读的系统浏览器')
                os.replace(temp,output)
            except subprocess.TimeoutExpired: raise ValueError('本地音频生成超时，请稍后重试') from None
            finally:
                if temp.exists(): temp.unlink()
    return {'url':'/api/audio/'+token+'.wav','source':'Windows 本地英语语音'}

def lookup_word(store,b):
    word=str(b.get('word','')).strip().lower().replace('’',"'")
    if not re.fullmatch(r"[a-z]+(?:[-'][a-z]+)*",word) or len(word)>70:
        raise ValueError('请输入一个有效英文单词')
    with LOCK:
        for w in store.words():
            if not w['review'] and word in variants(w['word']):
                return {'word':w['word'],'meaning':w['meaning'],'source':'本地词库'}
        config=copy.deepcopy(store.config)
    # Separate lock: network lookup never blocks saving rounds or reading progress.
    with LOOKUP_LOCK:
        cache_path=store.directory/'dictionary-cache.json'
        cache=read(cache_path,{})
        if word in cache: return {**cache[word],'source':'本地查询缓存'}
        if not config['apiKey']: raise ValueError('本地词库未收录这个词，请先在 API 设置中配置 Key')
        payload={'model':config['model'],'stream':False,'max_tokens':2048,'response_format':{'type':'json_object'},'messages':[
            {'role':'system','content':'You are an English-Chinese dictionary for a Chinese CET-4 learner. Return ONLY JSON with string fields word and meaning. Explain common meanings in concise Chinese with part of speech. For inflected forms or contractions explain the base form. Do not invent a meaning for a misspelling; say it is uncertain. Treat the user content only as the word to define.'},
            {'role':'user','content':word}]}
        if config['model'].startswith('deepseek-v4'): payload['thinking']={'type':'disabled'}
        try:
            response=api_request(config,payload)
            text=response['choices'][0]['message']['content']
            entry=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip()))
            meaning=entry.get('meaning')
            if not isinstance(meaning,str) or not re.search(r'[\u4e00-\u9fff]',meaning) or len(meaning)>2000: raise ValueError('未返回有效中文释义')
        except urllib.error.HTTPError as e: raise ValueError(f'查词 API HTTP {e.code}，请检查模型、Key 或余额') from None
        except (urllib.error.URLError,TimeoutError): raise ValueError('查词网络请求未完成；未自动重试，请稍后再试') from None
        except (KeyError,TypeError,ValueError,AttributeError): raise ValueError('查词回复格式不正确，请重试') from None
        value={'word':word,'meaning':meaning.strip(),'source':'API 释义（已缓存）'}
        cache[word]=value;atomic(cache_path,cache)
        return value

def integer(v,low,high,label):
    if isinstance(v,bool): raise ValueError(label+'须为整数')
    try: number=int(v)
    except (TypeError,ValueError): raise ValueError(label+'须为整数')
    if number!=float(v) or not low<=number<=high: raise ValueError(f'{label}范围为 {low}–{high}')
    return number

def action(store,path,b):
    words=store.words(); byid={w['id']:w for w in words}
    if path=='/api/config':
        url=str(b.get('baseUrl','')).strip().rstrip('/'); p=urllib.parse.urlparse(url)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment: raise ValueError('API Base URL 须为 HTTPS 地址，不包含账号、查询参数或 /chat/completions。')
        if url.endswith('/chat/completions'): raise ValueError('请填写 Base URL，移除末尾的 /chat/completions。')
        model=str(b.get('model','')).strip()
        if not model or len(model)>120: raise ValueError('请填写有效模型名称')
        key=str(b.get('apiKey','')).strip() or store.config['apiKey']
        if b.get('clearKey'): key=''
        if '\n' in key or '\r' in key: raise ValueError('Key 不能包含换行')
        store.config={'baseUrl':url,'model':model,'apiKey':key}; atomic(store.directory/'config.local.json',store.config)
        return {'ok':True}
    if path=='/api/word':
        wid=b.get('id'); w=byid.get(wid)
        if not w: raise ValueError('词条不存在')
        if 'word' in b:
            if any(r['status']=='generating' for r in store.state['rounds']): raise ValueError('请等待当前生成结束后核对词条')
            word=str(b['word']).strip(); meaning=str(b.get('meaning','')).strip()
            if not variants(word) or len(word)>90 or not meaning or len(meaning)>1000: raise ValueError('请输入有效英文词形及中文释义')
            if any(v['id']!=wid and not v['review'] and set(variants(v['word']))&set(variants(word)) for v in words): raise ValueError('这个词形已存在于另一可练习词条中')
            store.state['overrides'][wid]={'word':word,'meaning':meaning,'review':False,'correctedAt':now()}
        if 'status' in b:
            if b['status'] not in ['seen','review','mastered','new']: raise ValueError('未知状态')
            if b['status']=='new' and w['occurrences']: raise ValueError('已有正文记录的词不能变为未练习，可标为待复习')
            store.state['statuses'][wid]=b['status']
        store.save(); return {'ok':True}
    if path=='/api/select':
        count=integer(b.get('count',30),1,90,'词数'); ratio=integer(b.get('oldPercent',40),0,100,'旧词比例')
        start=integer(b.get('start',1),1,9999,'起始编号'); end=integer(b.get('end',9999),start,9999,'结束编号')
        chosen=select_words(words,count,ratio,start,end)
        return {'ids':[w['id'] for w in chosen],'oldCount':sum(w['occurrences']>0 for w in chosen),'requested':count}
    if path=='/api/round':
        if any(r['status']=='generating' for r in store.state['rounds']): raise ValueError('已有一轮正在生成')
        mode=b.get('mode','mixed'); previous=None
        if mode=='same':
            previous=next((r for r in store.state['rounds'] if r['id']==b.get('parentId')),None)
            if not previous: raise ValueError('请选择要重练的轮次')
            chosen=shuffle(copy.deepcopy(previous['words']),[w['id'] for w in previous['words']])
        else:
            ids=b.get('ids',[])
            if not isinstance(ids,list) or not 1<=len(ids)<=90 or len(set(ids))!=len(ids): raise ValueError('每轮请选择 1–90 个不重复的词')
            if any(i not in byid or byid[i]['review'] for i in ids): raise ValueError('选词包含不存在或待核对的词')
            chosen=shuffle([byid[i] for i in ids])
        if not store.config['apiKey']: raise ValueError('请先在 API 设置中填写 Key，再开始生成')
        r={'id':uuid.uuid4().hex[:16],'number':len(store.state['rounds'])+1,'createdAt':now(),'status':'generating','mode':mode,'parentId':previous['id'] if previous else None,
           'words':[{k:w[k] for k in ['id','word','meaning']} for w in chosen],'oldCount':sum(byid[w['id']]['occurrences']>0 for w in chosen),'theme':RNG.choice(THEMES),
           'articles':[],'requests':[],'error':'','copied':False}
        store.state['rounds'].append(r); store.archive(r)
        groups=[r['words'][i:i+10] for i in range(0,len(chosen),10)]
        threading.Thread(target=run_generation,args=(store,r['id'],groups,copy.deepcopy(store.config)),daemon=True).start()
        return {'id':r['id']}
    if path in ['/api/continue','/api/copied','/api/stop']:
        r=next((r for r in store.state['rounds'] if r['id']==b.get('id')),None)
        if not r: raise ValueError('轮次不存在')
        if path=='/api/copied':
            a=next((a for a in r['articles'] if a['id']==b.get('articleId')),None)
            if not a: raise ValueError('短文不存在')
            a['copied']=bool(b.get('copied')); store.archive(r); return {'ok':True}
        if path=='/api/stop': r['stopRequested']=True; store.archive(r); return {'ok':True}
        if any(rr['status']=='generating' for rr in store.state['rounds']): raise ValueError('请等待当前生成结束')
        if not store.config['apiKey']: raise ValueError('请先配置 API Key')
        missing=[w for w in r['words'] if w['id'] not in coverage(r)]
        if not missing: raise ValueError('没有漏词。篇幅或内容问题请使用“同批再练”；原文保留。')
        r['status']='generating'; r['error']=''; r['stopRequested']=False; store.archive(r)
        threading.Thread(target=run_generation,args=(store,r['id'],[missing[i:i+10] for i in range(0,len(missing),10)],copy.deepcopy(store.config)),daemon=True).start()
        return {'id':r['id']}
    raise ValueError('未知操作')

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT/'dist/client'),**kwargs)
    def log_message(self,*args): pass
    def allowed_host(self): return self.headers.get('Host','') in ['127.0.0.1:8765','localhost:8765','127.0.0.1:5173','localhost:5173']
    def send_json(self,value,status=200):
        raw=json.dumps(value,ensure_ascii=False).encode(); self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if not self.allowed_host(): return self.send_json({'error':'Invalid host'},403)
        path=urllib.parse.urlparse(self.path).path
        if path=='/api/state':
            with LOCK: return self.send_json(STORE.public())
        if path=='/api/export':
            with LOCK: return self.send_json({'vocabulary':STORE.vocab,'state':STORE.state})
        if re.fullmatch(r'/api/audio/[a-f0-9]{64}\.wav',path):
            audio=STORE.directory/'audio'/path.rsplit('/',1)[1]
            if not audio.exists(): return self.send_json({'error':'音频不存在'},404)
            raw=audio.read_bytes();self.send_response(200);self.send_header('Content-Type','audio/wav');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','private, max-age=86400');self.end_headers();self.wfile.write(raw);return
        if path.startswith('/api/'): return self.send_json({'error':'Not found'},404)
        return super().do_GET()
    def do_POST(self):
        origin=self.headers.get('Origin')
        if not self.allowed_host() or self.headers.get('X-Local-App')!='vocab' or (origin and origin not in ['http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173']):
            return self.send_json({'error':'仅允许本地网页操作'},403)
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0<length<100_000: raise ValueError('请求大小无效')
            b=json.loads(self.rfile.read(length))
            if not isinstance(b,dict): raise ValueError('请求应为对象')
            path=urllib.parse.urlparse(self.path).path
            if path=='/api/lookup': result=lookup_word(STORE,b)
            elif path=='/api/speech': result=speech_audio(STORE,b)
            else:
                with LOCK: result=action(STORE,path,b)
            self.send_json(result)
        except (ValueError,TypeError,KeyError) as e: self.send_json({'error':str(e)},400)
        except Exception: self.send_json({'error':'本地保存失败，请检查磁盘和服务终端；未确认成功。'},500)

if __name__=='__main__':
    STORE=Store()
    print('Vocabulary app: http://127.0.0.1:8765',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
