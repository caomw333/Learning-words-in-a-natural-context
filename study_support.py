"""Verified short excerpts are curated locally; never supplied by the model."""
import hashlib,json,re
from pathlib import Path

SOURCES=json.loads((Path(__file__).parent/'data/authentic-sources.json').read_text(encoding='utf-8'))

def select_sources(article):
    words=set(re.findall(r'[a-z]+',article['body'].lower()))
    ranked=sorted(SOURCES,key=lambda s:(-len(words.intersection(s['tags'])),hashlib.sha256((article['id']+s['id']).encode()).hexdigest()))
    return [dict(s,match='主题或词语相关' if words.intersection(s['tags']) else '通用表达拓展') for s in ranked[:2]]

def validate_coach(value,body):
    if not isinstance(value,dict):raise ValueError('表达建议格式不正确')
    summary=value.get('summary');items=value.get('items')
    if not isinstance(summary,str) or not 1<=len(summary)<=1200 or not isinstance(items,list) or len(items)>4:raise ValueError('表达建议格式不正确')
    for item in items:
        if not isinstance(item,dict) or any(not isinstance(item.get(k),str) or not 1<=len(item[k])<=1200 for k in ('original','suggestion','reason')):raise ValueError('表达建议字段不正确')
        if item['original'] not in body:raise ValueError('建议引用的句子不在原文中，未保存这次结果')
    return {'summary':summary,'items':[{k:i[k] for k in ('original','suggestion','reason')} for i in items]}
