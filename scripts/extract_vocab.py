"""Extract numbered source entries; never silently repair uncertain OCR."""
import json, re, zipfile, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = next(ROOT.parent.glob('四级大纲词表*.docx'))
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
root = ET.fromstring(zipfile.ZipFile(SOURCE).read('word/document.xml'))
def txt(node):
    return ' '.join(n.text or '' for n in node.findall('.//w:t', NS)).strip()
entries = {}
for table in root.findall('.//w:tbl', NS):
    previous = None
    for row in table.findall('w:tr', NS):
        cells = [txt(c) for c in row.findall('w:tc', NS)]
        if not cells: continue
        number = re.sub(r'\s', '', cells[0])
        if re.fullmatch(r'\d{4}', number) and len(cells) >= 2:
            key = int(number)
            word = re.sub(r'\s+', '', cells[1])
            meaning = ' '.join(cells[3:]).strip() if len(cells) >= 5 else ''
            good = len(cells) >= 5 and bool(cells[2]) and bool(cells[3]) and bool(re.search(r'[\u4e00-\u9fff]', cells[4])) and bool(re.fullmatch(r'[a-zA-Z][a-zA-Z()/-]*', word))
            entry = {'id':number,'word':word,'meaning':meaning,'review':not good,'source':'table','raw':' | '.join(cells)}
            if key not in entries or (entries[key]['review'] and good): entries[key] = entry
            previous = key
        elif previous and len(cells) >= 5 and not any(cells[:3]) and cells[3] and cells[4]:
            addition = ' '.join(cells[3:])
            if addition not in entries[previous]['meaning']: entries[previous]['meaning'] += '；' + addition
body = root.find('w:body', NS)
flat = '\n'.join(txt(p) for p in body.findall('w:p', NS))
pattern = re.compile(r'(?<!\d)(\d\s*\d\s*\d\s*\d)\s*([A-Za-z][A-Za-z()/-]*(?:\s+[a-z](?=\s|/))*)')
matches = list(pattern.finditer(flat))
for i, m in enumerate(matches):
    number = int(re.sub(r'\s','',m[1]))
    if not 1 <= number <= 9999 or number in entries: continue
    word = re.sub(r'\s','',m[2]).rstrip('/')
    segment = flat[m.end():matches[i+1].start() if i+1<len(matches) else len(flat)][:700].strip()
    entries[number] = {'id':f'{number:04d}','word':word,'meaning':'','review':True,'source':'paragraph','raw':m[0]+' '+segment}
maximum = max(entries)
for n in range(1, maximum+1):
    if n not in entries: entries[n] = {'id':f'{n:04d}','word':'','meaning':'','review':True,'source':'missing','raw':'此编号未能从文本层可靠提取，请对照原文补录。'}
seen = set()
for entry in sorted(entries.values(), key=lambda v:v['id']):
    if entry['word'].lower() in seen: entry['review'] = True
    seen.add(entry['word'].lower())
data = {'source':SOURCE.name,'total':len(entries),'ready':sum(not v['review'] for v in entries.values()),'words':sorted(entries.values(),key=lambda v:v['id'])}
(ROOT/'data').mkdir(exist_ok=True)
(ROOT/'data'/'vocabulary.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in data.items() if k!='words'},ensure_ascii=False))
