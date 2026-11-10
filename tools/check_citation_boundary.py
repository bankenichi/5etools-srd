"""Compare record semantics and generated HTML across a citation-only change."""
import argparse
from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re

IDS=r'(?:XPHB|XDMG|XMM|SRD52|SRD521)'


def semantic(value,key=None):
    if isinstance(value,dict):return {k:semantic(v,k) for k,v in value.items() if k not in {'source','classSource','subclassSource','page'}}
    if isinstance(value,list):return [semantic(v,key) for v in value]
    if isinstance(value,str):
        value=re.sub(r'(?<=\|)'+IDS+r'(?=[|#}]|$)','SOURCE',value,flags=re.I)
        return re.sub(r'(?<=\|source=)'+IDS+r'(?=[;|}]|$)','SOURCE',value,flags=re.I)
    return value


def records(root):
    result={}
    for file in (root/'data').rglob('*.json'):
        for kind,rows in json.loads(file.read_text(encoding='utf8')).items():
            if not isinstance(rows,list):continue
            for record in rows:
                if not isinstance(record,dict):continue
                key=(kind,*(record.get(k) for k in ('name','abbreviation','className','subclassShortName','level','set')))
                if key in result:raise ValueError('Semantic identity collision: '+repr(key))
                result[key]=semantic(record)
    return result


class MaskCitations(HTMLParser):
    """Preserve HTML verbatim except the actual source span in a metadata row."""
    VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self):
        super().__init__(convert_charrefs=False);self.stack=[];self.output=[];self.capture=None;self.count=0
    def emit(self,text):
        if self.capture is None:self.output.append(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);parent=self.stack[-1] if self.stack else ('',{})
        source=(tag=='span' and parent[0]=='div' and 'meta' in parent[1].get('class','').split() and re.search(r'font-style\s*:\s*italic',attrs.get('style',''),re.I))
        if source:
            if self.capture is not None:raise ValueError('Nested source metadata')
            self.capture=len(self.stack)+1
        else:
            if self.capture is not None:raise ValueError('Complex source metadata requires review')
            self.emit(self.get_starttag_text())
        if tag not in self.VOID:self.stack.append((tag,attrs))
    def handle_endtag(self,tag):
        if self.capture is not None:
            if tag!='span' or len(self.stack)!=self.capture:raise ValueError('Unclosed source metadata')
            self.capture=None;self.output.append('[SOURCE-CITATION]');self.count+=1
        else:self.emit('</'+tag+'>')
        if self.stack:
            for i in range(len(self.stack)-1,-1,-1):
                if self.stack[i][0]==tag:del self.stack[i:];break
    def handle_data(self,text):self.emit(text)
    def handle_entityref(self,name):self.emit('&'+name+';')
    def handle_charref(self,name):self.emit('&#'+name+';')
    def handle_comment(self,text):self.emit('<!--'+text+'-->')
    def handle_decl(self,text):self.emit('<!'+text+'>')
    def handle_pi(self,text):self.emit('<?'+text+'>')
    def handle_startendtag(self,tag,attrs):self.emit(self.get_starttag_text())


def masked(text):
    parser=MaskCitations();parser.feed(text);parser.close()
    if parser.capture is not None:raise ValueError('Incomplete source metadata')
    cards=len(re.findall(r'<h1 class="title"',text))
    if parser.count!=cards or not cards:raise ValueError('Expected exactly one source citation per generated card')
    return ''.join(parser.output),parser.count


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',type=Path,required=True);parser.add_argument('--after',type=Path,required=True)
    parser.add_argument('--before-html',type=Path,required=True);parser.add_argument('--after-html',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    before=records(args.before);after=records(args.after)
    if before!=after:raise AssertionError('Non-citation record semantics changed')
    results={}
    for platform in ('desktop','android'):
        old={p.name:p.read_text(encoding='utf8') for p in (args.before_html/platform).glob('*.html')}
        new={p.name:p.read_text(encoding='utf8') for p in (args.after_html/platform).glob('*.html')}
        if not old or set(old)!=set(new):raise AssertionError('Generated HTML inventory changed')
        files={}
        for name in old:
            a,n=masked(old[name]);b,m=masked(new[name])
            if a!=b or n!=m:raise AssertionError('Generated content/layout/script differs outside source metadata: '+platform+'/'+name)
            files[name]={'source_citations':n,'identical_except_bibliographic_metadata':True,'masked_sha256':hashlib.sha256(a.encode()).hexdigest()}
        results[platform]=files
    report={'scope':__doc__,'records':len(before),'all_record_semantics_equal_except_source_fields_and_pages':True,
      'generated_html':results,'passed':True,'limitation':'This compares generated HTML. It does not certify final browser fit, PDF layout or complete source fidelity.'}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'records':len(before),'identical_html_except_source_citations':{k:len(v) for k,v in results.items()},'passed':True}))


if __name__=='__main__':main()
