# -*- coding: utf-8 -*-
"""诊断实体提取问题"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from recall.processor.entity_extractor import EntityExtractor
from recall.graph.relation_extractor import RelationExtractor

extractor = EntityExtractor()
relation_extractor = RelationExtractor(entity_extractor=extractor)

text = '''我发现很恐怖的事情，就是现在很多项目，比如说n8n比如说扣子，这种成熟的以工作流为导向的。
我给扣子说我需要你帮我总结这一个月最火的前50个GitHub项目。
我会跟你说一个事儿，就是从2023年开始，我发现mjd这种诸如mamachapp，azone等品牌娃娃突然价格炒越来越高。
在bjd，mjd的圈子里面对科技了解的人不多，但是整体都是比较高净值的人群。
我通过ai写脚本，然后在日本中古网站抢低价娃，再在国内按照市场价卖出。
基本上可以做到几百块买进，上千块甚至一万块卖出。
2025我在闲鱼上卖娃达到了100万流水，50万净利润。
煤炉因为我在国内没有日本账号，下单方式和骏河屋差别较大导致很难抢过在日本本土的黄牛。'''

print('=== 1. spaCy NER 原始结果 ===')
nlp = extractor.nlp
doc = nlp(text)
print(f'发现 {len(doc.ents)} 个命名实体:')
for ent in doc.ents:
    print(f'  - "{ent.text}" [{ent.label_}]')
print()

print('=== 2. 实体提取器结果 ===')
entities = extractor.extract(text)
print(f'提取到 {len(entities)} 个实体:')
for e in entities:
    print(f'  - "{e.name}" [{e.entity_type}] conf={e.confidence}')
print()

print('=== 3. 关系提取器结果 ===')
relations = relation_extractor.extract(text, turn=0)
print(f'提取到 {len(relations)} 个关系:')
for r in relations:
    print(f'  - {r[0]} --[{r[1]}]--> {r[2]}')
print()

print('=== 4. 问题分析 ===')
# 检查 spaCy 模型类型
if 'zh' in str(nlp.meta.get('lang', '')):
    print('✓ 使用中文模型')
else:
    print(f'✗ 使用的是 {nlp.meta.get("lang", "unknown")} 模型，不是中文模型！')
    print('  这可能导致中文实体识别效果差')

# 检查是否缺少中文专有名词
expected_entities = ['n8n', '扣子', 'GitHub', 'mamachapp', 'azone', 'bjd', 'mjd', 
                     '日本', '闲鱼', '骏河屋', '煤炉', '黄牛']
found = [e.name for e in entities]
missing = [x for x in expected_entities if x not in found and x.lower() not in [f.lower() for f in found]]
if missing:
    print(f'✗ 缺少预期实体: {missing}')
else:
    print('✓ 核心实体都已提取')
