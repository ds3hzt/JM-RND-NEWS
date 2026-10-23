"""Fetch recent RSS items, generate a verified-source Korean briefing, archive once per KST date."""
import os, json, re, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parents[1]
TODAY=datetime.now(timezone(timedelta(hours=9))).date().isoformat()
QUERIES=[('국내','도금 표면처리 반도체 패키징'),('국내','전기도금 폐수 금속회수'),('해외','electroplating surface finishing connectors'),('해외','electrodeposition advanced packaging copper plating'),('해외','plating wastewater metal recovery automation')]
EXPANDED_QUERIES=[
    ('국내','커넥터 포고핀 테스트소켓 도금'),
    ('국내','금도금 팔라듐 니켈 전자부품 도금'),
    ('국내','도금 자동화 검사 장비 친환경'),
    ('해외','connector contact gold palladium plating'),
    ('해외','electroplating electronics surface treatment technology'),
    ('해외','semiconductor packaging copper plating process'),
    ('해외','plating wastewater recycling regulation'),
]
def fetch(q,region,lookback_days=7):
    url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q+f' when:{lookback_days}d','hl':'ko' if region=='국내' else 'en-US','gl':'KR' if region=='국내' else 'US','ceid':'KR:ko' if region=='국내' else 'US:en'})
    req=urllib.request.Request(url,headers={'User-Agent':'JM-RND-News/1.0'})
    with urllib.request.urlopen(req,timeout=20) as r: data=r.read()
    root=ET.fromstring(data)
    out=[]
    for x in root.findall('./channel/item'):
        title=(x.findtext('title') or '').strip(); link=(x.findtext('link') or '').strip(); pub=x.findtext('pubDate') or ''
        try: dt=parsedate_to_datetime(pub).astimezone(timezone.utc)
        except Exception: continue
        if dt < datetime.now(timezone.utc)-timedelta(days=lookback_days): continue
        if title and link.startswith('https://'): out.append({'title':title,'source':link,'region':region,'published':dt.date().isoformat()})
    return out

def normalized_title(title):
    title = re.sub(r'\\s*[-–|]\\s*[^-–|]{2,45}$', '', title)
    title = re.sub(r'[^0-9a-zA-Z가-힣]+', ' ', title.lower())
    return ' '.join(title.split())

def is_same_story(a, b):
    a, b = normalized_title(a), normalized_title(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    ta, tb = set(a.split()), set(b.split())
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return (len(ta & tb) >= 3 and overlap >= 0.60) or SequenceMatcher(None, a, b).ratio() >= 0.69

def deduplicate(items, prior_titles=()):
    chosen = []
    for item in items:
        if any(is_same_story(item['title'], title) for title in prior_titles):
            continue
        if any(is_same_story(item['title'], previous['title']) for previous in chosen):
            continue
        chosen.append(item)
    return chosen

def collect_candidates(archive):
    old_titles=[x.get('title','') for x in archive[:70]]

    def collect(queries,lookback_days):
        found=[]
        for region,q in queries:
            try: found.extend(fetch(q,region,lookback_days))
            except Exception as e: print('RSS error:',q,str(e))
        unique={x['source']:x for x in found}
        return sorted(deduplicate(list(unique.values()),old_titles),
                      key=lambda x:x['published'],reverse=True)

    candidates=collect(QUERIES,7)
    if candidates:
        return candidates
    print('기본 검색에서 새 후보가 없어 검색어와 기간을 넓혀 재검색합니다.')
    candidates=collect(EXPANDED_QUERIES,30)
    if not candidates:
        raise RuntimeError('기본·확대 검색에서 새 후보를 찾지 못했습니다. RSS 검색 결과를 확인해 주세요.')
    return candidates

def generate(items):
    key=os.getenv('OPENAI_API_KEY')
    if not key: raise RuntimeError('OPENAI_API_KEY secret 미설정: 뉴스 게시를 건너뜁니다.')
    count=min(5,len(items))
    # Use Chat Completions with strict JSON format; supplied URLs must be chosen verbatim from the RSS list.
    payload={'model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),'temperature':0.2,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':(f'당신은 한국 정밀 전기도금 기술 뉴스 편집자입니다. 제공된 RSS 후보에서만 사실을 선택합니다. 후보의 제목과 날짜만으로 확인 불가능한 수치, 성능, 인용, 계약은 추측하지 않습니다. 서로 다른 사건의 뉴스 1~{count}건을 추천합니다. 후보가 적으면 있는 후보만 추천하고, 국내/해외 균형은 가능한 범위에서만 고려합니다. 같은 기업의 같은 전시회나 발표를 다룬 기사는 하나만 선정. 최근성 우선, 전날 뉴스와 중복 제외. source는 후보 URL을 글자 하나도 변경하지 않고 사용. JSON 객체 {"articles":[{"date":"YYYY-MM-DD","region":"국내 또는 해외","category":"도금기술/전자부품/친환경·회수/자동화·검사/산업동향 중 하나","title":"...","summary":"확인 가능한 사실만 2~3문장","keywords":["..."],"background":"일반 기술 배경","impact":"도금 현장 적용 시사점 (추론 표시)","source":"https://..."}]} 형식만 출력. 기사 본문은 제공되지 않았으므로 RSS 제목에서 검증되지 않은 구체 수치는 쓰지 마세요.')},{'role':'user','content':json.dumps({'date':TODAY,'candidates':items},ensure_ascii=False)}]}
    req=urllib.request.Request('https://api.openai.com/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=100) as r: response=json.load(r)
    return json.loads(response['choices'][0]['message']['content'])['articles']

def main():
    path=ROOT/'news.json'; archive=json.loads(path.read_text(encoding='utf-8'))
    if any(x.get('date')==TODAY for x in archive): print('Already published today');return
    candidates=collect_candidates(archive)
    items=generate(candidates[:90])

    def validate(generated):
        allowed={x['source']:x for x in candidates}; clean=[]; seen=set()
        for x in generated:
            src=x.get('source'); original=allowed.get(src)
            if not original or src in seen: continue
            if x.get('region')!=original['region']: continue
            if x.get('category') not in ['도금기술','전자부품','친환경·회수','자동화·검사','산업동향']: continue
            x['date']=TODAY;x['published']=original['published'];seen.add(src);clean.append(x)
            if len(clean)==5: break
        return clean

    clean=validate(items)
    if not clean:
        print('후보는 수집했지만 추천 결과를 검증하지 못해, 최신 후보 1건으로 다시 요청합니다.')
        clean=validate(generate(candidates[:1]))
    if not clean: raise RuntimeError('수집 후보 중 게시 가능한 추천을 만들지 못했습니다. 오늘 자료는 게시하지 않습니다.')
    if len(deduplicate(clean))!=len(clean): raise RuntimeError('중복 기사 감지: 게시하지 않습니다.')
    path.write_text(json.dumps(clean+archive,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Published',TODAY,len(clean))
if __name__=='__main__': main()"""Fetch recent RSS items, generate a verified-source Korean briefing, archive once per KST date."""
import os, json, re, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parents[1]
TODAY=datetime.now(timezone(timedelta(hours=9))).date().isoformat()
QUERIES=[('국내','도금 표면처리 반도체 패키징'),('국내','전기도금 폐수 금속회수'),('해외','electroplating surface finishing connectors'),('해외','electrodeposition advanced packaging copper plating'),('해외','plating wastewater metal recovery automation')]
EXPANDED_QUERIES=[
        ('국내','커넥터 포고핀 테스트소켓 도금'),
        ('국내','금도금 팔라듐 니켈 전자부품 도금'),
        ('국내','도금 자동화 검사 장비 친환경'),
        ('해외','connector contact gold palladium plating'),
        ('해외','electroplating electronics surface treatment technology'),
        ('해외','semiconductor packaging copper plating process'),
        ('해외','plating wastewater recycling regulation'),
]
def fetch(q,region,lookback_days=7):
        url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q+f' when:{lookback_days}d','hl':'ko' if region=='국내' else 'en-US','gl':'KR' if region=='국내' else 'US','ceid':'KR:ko' if region=='국내' else 'US:en'})
        req=urllib.request.Request(url,headers={'User-Agent':'JM-RND-News/1.0'})
        with urllib.request.urlopen(req,timeout=20) as r: data=r.read()
                root=ET.fromstring(data)
    out=[]
    for x in root.findall('./channel/item'):
                title=(x.findtext('title') or '').strip(); link=(x.findtext('link') or '').strip(); pub=x.findtext('pubDate') or ''
                try: dt=parsedate_to_datetime(pub).astimezone(timezone.utc)
except Exception: continue
        if dt < datetime.now(timezone.utc)-timedelta(days=lookback_days): continue
                    if title and link.startswith('https://'): out.append({'title':title,'source':link,'region':region,'published':dt.date().isoformat()})
                            return out

def normalized_title(title):
        title = re.sub(r'\\s*[-–|]\\s*[^-–|]{2,45}$', '', title)
    title = re.sub(r'[^0-9a-zA-Z가-힣]+', ' ', title.lower())
    return ' '.join(title.split())

def is_same_story(a, b):
        a, b = normalized_title(a), normalized_title(b)
    if not a or not b:
                return False
            if a == b or a in b or b in a:
                        return True
                    ta, tb = set(a.split()), set(b.split())
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return (len(ta & tb) >= 3 and overlap >= 0.60) or SequenceMatcher(None, a, b).ratio() >= 0.69

def deduplicate(items, prior_titles=()):
        chosen = []
    for item in items:
                if any(is_same_story(item['title'], title) for title in prior_titles):
                                continue
                            if any(is_same_story(item['title'], previous['title']) for previous in chosen):
                                            continue
                                        chosen.append(item)
    return chosen

def collect_candidates(archive):
        old_titles=[x.get('title','') for x in archive[:70]]

    def collect(queries,lookback_days):
                found=[]
        for region,q in queries:
                        try: found.extend(fetch(q,region,lookback_days))
except Exception as e: print('RSS error:',q,str(e))
        unique={x['source']:x for x in found}
        return sorted(deduplicate(list(unique.values()),old_titles),
                                            key=lambda x:x['published'],reverse=True)

    candidates=collect(QUERIES,7)
    if candidates:
                return candidates
    print('기본 검색에서 새 후보가 없어 검색어와 기간을 넓혀 재검색합니다.')
    candidates=collect(EXPANDED_QUERIES,30)
    if not candidates:
                raise RuntimeError('기본·확대 검색에서 새 후보를 찾지 못했습니다. RSS 검색 결과를 확인해 주세요.')
    return candidates

def generate(items):
        key=os.getenv('OPENAI_API_KEY')
    if not key: raise RuntimeError('OPENAI_API_KEY secret 미설정: 뉴스 게시를 건너뜁니다.')
            count=min(5,len(items))
    # Use Chat Completions with strict JSON format; supplied URLs must be chosen verbatim from the RSS list.
    payload={'model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),'temperature':0.2,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':(f'당신은 한국 정밀 전기도금 기술 뉴스 편집자입니다. 제공된 RSS 후보에서만 사실을 선택합니다. 후보의 제목과 날짜만으로 확인 불가능한 수치, 성능, 인용, 계약은 추측하지 않습니다. 서로 다른 사건의 뉴스 1~{count}건을 추천합니다. 후보가 적으면 있는 후보만 추천하고, 국내/해외 균형은 가능한 범위에서만 고려합니다. 같은 기업의 같은 전시회나 발표를 다룬 기사는 하나만 선정. 최근성 우선, 전날 뉴스와 중복 제외. source는 후보 URL을 글자 하나도 변경하지 않고 사용. JSON 객체 {"articles":[{"date":"YYYY-MM-DD","region":"국내 또는 해외","category":"도금기술/전자부품/친환경·회수/자동화·검사/산업동향 중 하나","title":"...","summary":"확인 가능한 사실만 2~3문장","keywords":["..."],"background":"일반 기술 배경","impact":"도금 현장 적용 시사점 (추론 표시)","source":"https://..."}]} 형식만 출력. 기사 본문은 제공되지 않았으므로 RSS 제목에서 검증되지 않은 구체 수치는 쓰지 마세요.')},{'role':'user','content':json.dumps({'date':TODAY,'candidates':items},ensure_ascii=False)}]}
    req=urllib.request.Request('https://api.openai.com/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=100) as r: response=json.load(r)
            return json.loads(response['choices'][0]['message']['content'])['articles']

def main():
        path=ROOT/'news.json'; archive=json.loads(path.read_text(encoding='utf-8'))
    if any(x.get('date')==TODAY for x in archive): print('Already published today');return
            candidates=collect_candidates(archive)
    items=generate(candidates[:90])

    def validate(generated):
                allowed={x['source']:x for x in candidates}; clean=[]; seen=set()
        for x in generated:
                        src=x.get('source'); original=allowed.get(src)
                        if not original or src in seen: continue
                                        if x.get('region')!=original['region']: continue
                                                        if x.get('category') not in ['도금기술','전자부품','친환경·회수','자동화·검사','산업동향']: continue
                                                                        x['date']=TODAY;x['published']=original['published'];seen.add(src);clean.append(x)
            if len(clean)==5: break
                        return clean

    clean=validate(items)
    if not clean:
                print('후보는 수집했지만 추천 결과를 검증하지 못해, 최신 후보 1건으로 다시 요청합니다.')
        clean=validate(generate(candidates[:1]))
    if not clean: raise RuntimeError('수집 후보 중 게시 가능한 추천을 만들지 못했습니다. 오늘 자료는 게시하지 않습니다.')
            if len(deduplicate(clean))!=len(clean): raise RuntimeError('중복 기사 감지: 게시하지 않습니다.')
                    path.write_text(json.dumps(clean+archive,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Published',TODAY,len(clean))
if __name__=='__main__': main()
