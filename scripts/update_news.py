"""Fetch recent RSS items, generate a verified-source Korean briefing, archive once per KST date."""
import os, json, re, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from collections import Counter
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parents[1]
TODAY=datetime.now(timezone(timedelta(hours=9))).date().isoformat()
QUERIES=[('국내','도금 표면처리 반도체 패키징'),('국내','전기도금 폐수 금속회수'),('해외','electroplating surface finishing connectors'),('해외','electrodeposition advanced packaging copper plating'),('해외','plating wastewater metal recovery automation')]
def fetch(q,region):
    url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q+' when:7d','hl':'ko' if region=='국내' else 'en-US','gl':'KR' if region=='국내' else 'US','ceid':'KR:ko' if region=='국내' else 'US:en'})
    req=urllib.request.Request(url,headers={'User-Agent':'JM-RND-News/1.0'})
    with urllib.request.urlopen(req,timeout=20) as r: data=r.read()
    root=ET.fromstring(data)
    out=[]
    for x in root.findall('./channel/item'):
        title=(x.findtext('title') or '').strip(); link=(x.findtext('link') or '').strip(); pub=x.findtext('pubDate') or ''
        try: dt=parsedate_to_datetime(pub).astimezone(timezone.utc)
        except Exception: continue
        if dt < datetime.now(timezone.utc)-timedelta(days=7): continue
        if title and link.startswith('https://'): out.append({'title':title,'source':link,'region':region,'published':dt.date().isoformat()})
    return out

def normalized_title(title):
    title = re.sub(r'\\s*[-–|]\\s*[^-–|]{2,45}
    key=os.getenv('OPENAI_API_KEY')
    if not key: raise RuntimeError('OPENAI_API_KEY secret 미설정: 뉴스 게시를 건너뜁니다.')
    # Use Chat Completions with strict JSON format; supplied URLs must be chosen verbatim from the RSS list.
    payload={'model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),'temperature':0.2,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':('당신은 한국 정밀 전기도금 기술 뉴스 편집자입니다. 제공된 RSS 후보에서만 사실을 선택합니다. 후보의 제목과 날짜만으로 확인 불가능한 수치, 성능, 인용, 계약은 추측하지 않습니다. 서로 다른 사건의 뉴스 정확히 5건, 국내 2~3건 해외 2~3건, 최근성 우선. 같은 기업의 동일 행사/발표를 여러 언론이 보도한 경우 반드시 한 건만 선택. 전날 뉴스와 중복 제외. source는 후보 URL을 글자 하나도 변경하지 않고 사용. JSON 객체 {"articles":[{"date":"YYYY-MM-DD","region":"국내 또는 해외","category":"도금기술/전자부품/친환경·회수/자동화·검사/산업동향 중 하나","title":"...","summary":"확인 가능한 사실만 2~3문장","keywords":["..."],"background":"일반 기술 배경","impact":"도금 현장 적용 시사점 (추론 표시)","source":"https://..."}]} 형식만 출력. 기사 본문은 제공되지 않았으므로 RSS 제목에서 검증되지 않은 구체 수치는 쓰지 마세요.')},{'role':'user','content':json.dumps({'date':TODAY,'candidates':items},ensure_ascii=False)}]}
    req=urllib.request.Request('https://api.openai.com/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=100) as r: response=json.load(r)
    return json.loads(response['choices'][0]['message']['content'])['articles']

def main():
    path=ROOT/'news.json'; archive=json.loads(path.read_text(encoding='utf-8'))
    if any(x.get('date')==TODAY for x in archive): print('Already published today');return
    candidates=[]
    for region,q in QUERIES:
        try: candidates.extend(fetch(q,region))
        except Exception as e: print('RSS error:',q,str(e))
    unique={x['source']:x for x in candidates}; candidates=list(unique.values())
    old_titles=[x.get('title','') for x in archive[:70]]
    candidates=deduplicate(candidates, old_titles)
    if len(candidates)<5: raise RuntimeError('최근 RSS 후보가 5건 미만입니다. 게시를 건너뜁니다.')
    items=generate(candidates[:90]); allowed={x['source']:x for x in candidates}; clean=[]; seen=set()
    for x in items:
        src=x.get('source'); original=allowed.get(src)
        if not original or src in seen: continue
        if x.get('region')!=original['region']: continue
        if x.get('category') not in ['도금기술','전자부품','친환경·회수','자동화·검사','산업동향']: continue
        x['date']=TODAY;x['published']=original['published'];seen.add(src);clean.append(x)
    if len(deduplicate(clean))!=len(clean): raise RuntimeError('동일 사건 중복 선정: 게시를 건너뜁니다.')
    if len(clean)!=5: raise RuntimeError(f'검증된 기사 {len(clean)}건: 5건 미달로 게시하지 않습니다.')
    if Counter(x['region'] for x in clean)['국내'] not in (2,3): raise RuntimeError('국내/해외 균형 불충족으로 게시하지 않습니다.')
    path.write_text(json.dumps(clean+archive,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Published',TODAY,len(clean))
if __name__=='__main__': main()
, '', title)
    title = re.sub(r'[^0-9a-zA-Z가-힣]+', ' ', title.lower())
    return ' '.join(title.split())

def is_same_story(a, b):
    a, b = normalized_title(a), normalized_title(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    ta, tb = set(a.split()), set(b.split())
    common = ta & tb
    # Detect multiple outlets covering one event, while preserving distinct topics.
    if len(common) >= 3 and len(common) / max(1, min(len(ta), len(tb))) >= .65:
        return True
    return SequenceMatcher(None, a, b).ratio() >= .72

def deduplicate(items, prior_titles=()):
    chosen = []
    for item in items:
        if any(is_same_story(item['title'], t) for t in prior_titles):
            continue
        if any(is_same_story(item['title'], x['title']) for x in chosen):
            continue
        chosen.append(item)
    return chosen

def generate(items):
    key=os.getenv('OPENAI_API_KEY')
    if not key: raise RuntimeError('OPENAI_API_KEY secret 미설정: 뉴스 게시를 건너뜁니다.')
    # Use Chat Completions with strict JSON format; supplied URLs must be chosen verbatim from the RSS list.
    payload={'model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),'temperature':0.2,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':('당신은 한국 정밀 전기도금 기술 뉴스 편집자입니다. 제공된 RSS 후보에서만 사실을 선택합니다. 후보의 제목과 날짜만으로 확인 불가능한 수치, 성능, 인용, 계약은 추측하지 않습니다. 서로 다른 뉴스 5건, 가능하면 국내 2~3건 해외 2~3건, 최근성 우선, 전날 뉴스와 중복 제외. source는 후보 URL을 글자 하나도 변경하지 않고 사용. JSON 객체 {"articles":[{"date":"YYYY-MM-DD","region":"국내 또는 해외","category":"도금기술/전자부품/친환경·회수/자동화·검사/산업동향 중 하나","title":"...","summary":"확인 가능한 사실만 2~3문장","keywords":["..."],"background":"일반 기술 배경","impact":"도금 현장 적용 시사점 (추론 표시)","source":"https://..."}]} 형식만 출력. 기사 본문은 제공되지 않았으므로 RSS 제목에서 검증되지 않은 구체 수치는 쓰지 마세요.')},{'role':'user','content':json.dumps({'date':TODAY,'candidates':items},ensure_ascii=False)}]}
    req=urllib.request.Request('https://api.openai.com/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=100) as r: response=json.load(r)
    return json.loads(response['choices'][0]['message']['content'])['articles']

def main():
    path=ROOT/'news.json'; archive=json.loads(path.read_text(encoding='utf-8'))
    if any(x.get('date')==TODAY for x in archive): print('Already published today');return
    candidates=[]
    for region,q in QUERIES:
        try: candidates.extend(fetch(q,region))
        except Exception as e: print('RSS error:',q,str(e))
    unique={x['source']:x for x in candidates}; candidates=list(unique.values())
    old_titles=[x['title'] for x in archive[-70:]]
    candidates=[x for x in candidates if not any(x['title'].lower() in t.lower() or t.lower() in x['title'].lower() for t in old_titles)]
    if len(candidates)<5: raise RuntimeError('최근 RSS 후보가 5건 미만입니다. 게시를 건너뜁니다.')
    items=generate(candidates[:90]); allowed={x['source']:x for x in candidates}; clean=[]; seen=set()
    for x in items:
        src=x.get('source'); original=allowed.get(src)
        if not original or src in seen: continue
        if x.get('region')!=original['region']: continue
        if x.get('category') not in ['도금기술','전자부품','친환경·회수','자동화·검사','산업동향']: continue
        x['date']=TODAY;x['published']=original['published'];seen.add(src);clean.append(x)
    if len(clean)!=5: raise RuntimeError(f'검증된 기사 {len(clean)}건: 5건 미달로 게시하지 않습니다.')
    if Counter(x['region'] for x in clean)['국내'] not in (2,3): raise RuntimeError('국내/해외 균형 불충족으로 게시하지 않습니다.')
    path.write_text(json.dumps(clean+archive,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Published',TODAY,len(clean))
if __name__=='__main__': main()
