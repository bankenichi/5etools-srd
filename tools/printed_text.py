"""Materialize 5etools display tags as literal text in this data-only dataset.

The card apps' existing tag cleaner predates several modern tags. Plain strings
are valid entries in the source schema and let both unchanged consumers retain
the printed words. Structural UIDs and parameterized itemEntry calls remain.
"""
import re

REFS={'spell','item','creature','race','feat','action','condition','status','skill','sense','variantrule','hazard','class','background','itemProperty','itemMastery','table','deck','card','optfeature','language'}
ABILITIES={'str':'Strength','dex':'Dexterity','con':'Constitution','int':'Intelligence','wis':'Wisdom','cha':'Charisma'}
PATTERN=re.compile(r'\{@(\w+)(?: ([^{}]*))?}')


def display(tag,value):
    value=value or '';parts=value.split('|')
    if tag in REFS:return parts[2] if len(parts)>2 and parts[2] else parts[0]
    if tag in {'i','b','filter','book','area','5etools','note','link'}:return parts[0]
    if tag in {'dice','damage'}:
        text=parts[1] if len(parts)>1 and parts[1] else parts[0]
        return text.replace('summonSpellLevel','the spell’s level')
    if tag in {'scaledice','scaledamage'}:return parts[3] if len(parts)>3 and parts[3] else parts[2]
    if tag=='dc':return 'DC '+(parts[1] if len(parts)>1 and parts[1] else parts[0])
    if tag=='hit':return ('' if value.startswith(('+','-')) else '+')+value
    if tag=='hitYourSpellAttack':return value
    if tag=='atkr':
        modes={'m':'Melee','r':'Ranged','mw':'Melee Weapon','rw':'Ranged Weapon','ms':'Melee Spell','rs':'Ranged Spell'}
        return ' or '.join(modes[v] for v in value.split(','))+' Attack Roll:'
    if tag=='h':return 'Hit: '
    if tag=='hom':return 'Hit or Miss: '
    if tag=='actSave':return ABILITIES[value]+' Saving Throw:'
    if tag=='actSaveFail':return {'1':'First Failure:','2':'Second Failure:'}.get(value,'Failure:')
    if tag=='actSaveSuccess':return 'Success:'
    if tag=='actSaveSuccessOrFail':return 'Failure or Success:'
    if tag=='actSaveFailBy':return 'Failure by '+value+' or More:'
    if tag=='actTrigger':return 'Trigger:'
    if tag=='actResponse':return 'Response'+('—' if 'd' in value else ':')
    if tag=='recharge':return '(Recharge '+(value+'–6' if value and value!='6' else '6')+')'
    if tag=='chance':return parts[1] if len(parts)>1 and parts[1] else parts[0]+' percent'
    raise ValueError('Unreviewed display tag: '+tag+' '+value)


def materialize(value):
    if isinstance(value,str):
        # Existing class-table consumers inspect filter parameters such as
        # level=9 to preserve their established table splitting. They already
        # render the tag's display text correctly, so keep that structural tag.
        previous=None
        while value!=previous:
            previous=value
            value=PATTERN.sub(lambda m:m.group(0) if m.group(1)=='filter' else display(*m.groups()),value)
        if '{@' in PATTERN.sub(lambda m:'' if m.group(1)=='filter' else m.group(0),value):raise ValueError('Unexpanded display tag: '+value)
        return value
    if isinstance(value,list):return [materialize(item) for item in value]
    if isinstance(value,dict):return {key:materialize(item) for key,item in value.items()}
    return value
