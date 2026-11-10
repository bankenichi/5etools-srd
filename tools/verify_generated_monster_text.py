"""Check every audited monster feature survives both generated HTML documents.

This checks exact word sequences, allowing the existing renderer's heading
punctuation and label capitalization. It does not certify clipping, pixels,
core-stat formatting, typography, or a PDF; those are separate gates.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata


def words(text):
    text=unicodedata.normalize('NFKC',text).translate(str.maketrans({'’':"'",'–':'-','−':'-'}))
    return ' '.join(re.findall(r"[\w]+(?:'[\w]+)?",text.casefold()))


class Cards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.stack=[];self.cards=[];self.card=None;self.body_depth=None;self.title_depth=None;self.title_span=None;self.saw_title_span=False
    def handle_starttag(self,tag,attrs):
        if tag in {'meta','link','img','br','hr','input'}:return
        attrs=dict(attrs);self.stack.append(tag);classes=attrs.get('class','').split()
        if tag=='div' and 'card' in classes:
            self.card={'title':[],'body':[],'depth':len(self.stack)}
        if self.card:
            if tag=='h1' and 'title' in classes:self.title_depth=len(self.stack);self.saw_title_span=False
            if tag=='span' and self.title_depth is not None and not self.saw_title_span:self.title_span=len(self.stack);self.saw_title_span=True
            if tag=='div' and 'content-wrapper' in classes:self.body_depth=len(self.stack)
    def handle_endtag(self,tag):
        if not self.stack:return
        depth=len(self.stack)
        if self.card:
            if self.body_depth is not None:self.card['body'].append(' ')
            if depth==self.body_depth:self.body_depth=None
            if depth==self.title_depth:self.title_depth=None
            if depth==self.title_span:self.title_span=None
            if depth==self.card['depth']:
                self.cards.append({'title':' '.join(''.join(self.card['title']).split()),'body':' '.join(''.join(self.card['body']).split())});self.card=None
        self.stack.pop()
    def handle_data(self,data):
        if self.card:
            if self.body_depth is not None:self.card['body'].append(data)
            if self.title_span is not None:self.card['title'].append(data)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review',type=Path,required=True);parser.add_argument('--desktop',type=Path,required=True);parser.add_argument('--android',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();review=json.loads(args.review.read_text(encoding='utf8'));names=sorted([r['name'] for r in review['records']],key=len,reverse=True);platforms={}
    for platform,file in [('desktop',args.desktop),('android',args.android)]:
        document=Cards();document.feed(file.read_text(encoding='utf8'));bodies={name:[] for name in names}
        for card in document.cards:
            matches=[name for name in names if card['title']==name or re.fullmatch(re.escape(name)+r'\s+\d+/\d+',card['title'])]
            if len(matches)!=1:raise ValueError(('Unmapped generated title',card['title']))
            bodies[matches[0]].append(card['body'])
        missing=[];count=0
        for record in review['records']:
            body=' '+words(' '.join(bodies[record['name']]))+' '
            for entry in record['entries']:
                count+=1;expected=' '+words(entry['text'])+' '
                if expected not in body:missing.append({'name':record['name'],'entry':entry['name'],'expected':entry['text']})
            if record.get('legendary_header'):
                if ' '+words(record['legendary_header']['official'])+' ' not in body:missing.append({'name':record['name'],'entry':'legendary header','expected':record['legendary_header']['official']})
        platforms[platform]={'html_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'cards':len(document.cards),'entries_checked':count,'missing':missing,'passed':not missing}
    out={'scope':__doc__,'review_sha256':hashlib.sha256(args.review.read_bytes()).hexdigest(),'platforms':platforms,'passed':all(p['passed'] for p in platforms.values())}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({p:{k:v for k,v in r.items() if k not in {'missing','html_sha256'}}|{'missing_entries':len(r['missing'])} for p,r in platforms.items()}))
    if not out['passed']:raise SystemExit(1)


if __name__=='__main__':main()
