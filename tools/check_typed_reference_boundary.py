"""Bound the three reviewed class-source corrections in data and generated HTML.

This compares actual input/output bytes. It does not certify browser fitting or
PDF fidelity, which require separate rendered-output checks.
"""
import argparse
import copy
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from printed_text import materialize
from source_identity import remap
from locate_source_citations import canon


class Cards(HTMLParser):
    def __init__(self,text):
        super().__init__(convert_charrefs=False)
        self.text=text;self.offsets=[0]
        for line in text.splitlines(keepends=True):self.offsets.append(self.offsets[-1]+len(line))
        self.cards=[];self.depth=0;self.begin=None
        self.feed(text)
        if self.begin is not None:raise ValueError('Unclosed card markup')

    def offset_at(self):
        line,col=self.getpos()
        return self.offsets[line-1]+col

    def handle_starttag(self,tag,attrs):
        if tag!='div':return
        if 'card' in dict(attrs).get('class','').split():
            if self.begin is not None:raise ValueError('Nested card markup')
            self.begin=self.offset_at();self.depth=1
        elif self.begin is not None:self.depth+=1

    def handle_endtag(self,tag):
        if tag!='div' or self.begin is None:return
        self.depth-=1
        if self.depth==0:
            end=self.offset_at()+len('</div>')
            self.cards.append((self.begin,end,self.text[self.begin:end]));self.begin=None

    def shell(self):
        result=[];end=0
        for start,stop,_ in self.cards:
            result.extend((self.text[end:start],'<!-- CARD -->'));end=stop
        result.append(self.text[end:])
        return ''.join(result)


class Content(HTMLParser):
    def __init__(self,text):
        super().__init__(convert_charrefs=True)
        self.depth=0;self.words=[];self.feed(text)

    def handle_starttag(self,tag,attrs):
        if tag!='div':return
        if 'content-inner' in dict(attrs).get('class','').split():
            assert not self.depth
            self.depth=1
        elif self.depth:self.depth+=1

    def handle_endtag(self,tag):
        if tag=='div' and self.depth:self.depth-=1

    def handle_data(self,text):
        if self.depth:self.words.append(text)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for option in ('before','after','before-html','after-html','out'):
        parser.add_argument('--'+option,type=Path,required=True)
    args=parser.parse_args()
    policy=json.loads((Path(__file__).resolve().parents[1]/'corrections/zzz-structured-references.json').read_text(encoding='utf8'))
    allowed={patch['file']:patch for patch in policy['records']}
    paths=lambda root:{p.relative_to(root).as_posix() for p in (root/'data').rglob('*.json')}
    assert paths(args.before)==paths(args.after),'Data inventory changed'
    changes=[];equal=0
    for rel in sorted(paths(args.before)):
        old_raw=(args.before/rel).read_bytes();new_raw=(args.after/rel).read_bytes()
        if rel not in allowed:
            assert old_raw==new_raw,rel
            equal+=1;continue
        expected=json.loads(old_raw);patch=allowed[rel]
        matches=[r for r in expected[patch['kind']] if all(r.get(k)==v for k,v in patch['identity'].items() if k!='source')]
        assert len(matches)==1,rel
        for edit in patch['edits']:
            parts=edit['path'].strip('/').split('/');parent=matches[0]
            for key in parts[:-1]:parent=parent[int(key)] if isinstance(parent,list) else parent[key]
            key=int(parts[-1]) if isinstance(parent,list) else parts[-1]
            parent[key]=remap(materialize(copy.deepcopy(edit['value'])))
        assert expected==json.loads(new_raw),rel
        changes.append({'file':rel,'kind':patch['kind'],'identity':{k:v for k,v in patch['identity'].items() if k!='source'},'changed_paths':[e['path'] for e in patch['edits']]})
    html_proof={}
    for platform in ('desktop','android'):
        oldroot=args.before_html/platform;newroot=args.after_html/platform
        html_paths={p.name for p in oldroot.glob('*.html')}
        assert html_paths and html_paths=={p.name for p in newroot.glob('*.html')}
        html_proof[platform]={}
        for name in sorted(html_paths):
            old=(oldroot/name).read_text(encoding='utf8');new=(newroot/name).read_text(encoding='utf8')
            if old==new:
                html_proof[platform][name]={'byte_identical':True};continue
            assert name in ('classes.html','all.html'),name
            ac=Cards(old);bc=Cards(new)
            assert len(ac.cards)==len(bc.cards) and ac.shell()==bc.shell(),name
            changed=[];families={family:{'before':[],'after':[]} for family in ('Paladin','Ranger')}
            for index,((_,_,a),(_,_,b)) in enumerate(zip(ac.cards,bc.cards,strict=True)):
                def title(h):return unescape(re.search(r'<h1 class="title"[^>]*>\s*<span>(.*?)</span>',h,re.S)[1])
                assert title(a)==title(b)
                for family in families:
                    if re.fullmatch(family+r' \d+/\d+',title(a)):
                        families[family]['before'].extend(Content(a).words)
                        families[family]['after'].extend(Content(b).words)
                if a==b:continue
                assert re.fullmatch(r'(Paladin|Ranger) \d+/\d+',title(b)),(index,title(b))
                changed.append({'index':index,'title':title(b)})
            assert {c['title'] for c in changed}=={'Paladin 1/4','Paladin 2/4','Paladin 3/4','Paladin 4/4','Ranger 1/3','Ranger 2/3'},changed
            for patch in policy['records']:
                family=patch['identity']['className']
                if family not in families:continue
                alternative=patch['edits'][0]['value']
                insertion=canon(alternative['name']+': '+alternative['entries'][0])
                before_text=canon(' '.join(families[family]['before']))
                after_text=canon(' '.join(families[family]['after']))
                assert after_text.count(insertion)==1,(family,'Missing/duplicate printed alternative')
                assert canon(after_text.replace(insertion,''))==before_text,(family,'Other class text changed')
            html_proof[platform][name]={'cards':len(ac.cards),'changed_cards':changed,
              'all_other_cards_byte_identical':True,'html_outside_cards_byte_identical':True,
              'complete_paladin_and_ranger_text_identical_except_two_printed_insertions':True}
    report={'scope':__doc__,'unchanged_data_files':equal,'changed_records':changes,'generated_html':html_proof,'passed':True}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'passed':True,'unchanged_data_files':equal,'changed_records':len(changes),'html_files_per_platform':len(html_proof['desktop']),'changed_class_cards_per_platform':6,'printed_text_insertions':2}))


if __name__=='__main__':main()
