"""Debug script to check quality scores"""
from pattern_analyzer import load_and_apply_rules
from database import get_active_rules
from extractor import MangaTitleExtractor

rules = get_active_rules()
e = MangaTitleExtractor()

cases = [
    '(C105) [electromonkey (エム)] 鬼滅の刃H (単行本フルカラー版)',
    '尾崎健 WITCHY 1-13',
    '[HORROR] Star Rail Gravure #01 (スターレイルグラビア)#01)',
    '[モモ林萌 (ももりん)] ファンタジーC妻 (ファンタizzyC妻) [DL版]',
]

for c in cases:
    extracted = load_and_apply_rules(c, rules)
    q = e._estimate_quality(c, extracted)
    print(f'{q:.2f} | extracted: [{extracted}]')
    print(f'  original: {c}')

print(f'\nthreshold: {e._estimate_quality.__doc__}')
from config import get_quality_threshold
print(f'threshold value: {get_quality_threshold()}')