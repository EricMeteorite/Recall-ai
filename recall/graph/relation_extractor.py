"""关系提取器 - 从对话中自动发现实体关系 (7.0 Universal)

支持领域:
- RP / 角色扮演 (原有)
- 因果 / Causal
- 商业 / Business
- 金融 / Financial
- 技术 / Technical
- 学术 / Academic
- 科学 / Scientific
- 法律 / Legal
- 医学 / Medical
- 通用知识 / General Knowledge
"""

import re
from typing import List, Tuple, Callable

# ── 通用实体片段 ──────────────────────────────────────────────
# Reusable regex fragments for entity capture groups
_ZH = r'[\u4e00-\u9fa5A-Za-z0-9·\-]{1,20}'   # 中英文实体
_EN = r'[\w][\w\s\-]{0,25}[\w]'                # 英文实体 (2+ chars)


class RelationExtractor:
    """从文本中自动提取实体关系 (7.0 Universal Edition)"""

    # ═══════════════════════════════════════════════════════════
    #  关系模式（正则匹配）
    #  每条: (regex_pattern, lambda match -> (source, rel_type, target))
    # ═══════════════════════════════════════════════════════════
    PATTERNS: List[Tuple[str, Callable]] = [

        # ─────────────────────────────────────────────────────
        # 1. RP / 角色扮演 (Original — KEPT)
        # ─────────────────────────────────────────────────────

        # 中文 RP 模式
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})是([\u4e00-\u9fa5A-Za-z]{1,15})的(朋友|敌人|家人|老师|学生|上司|下属)',
         lambda m: (m.group(1), 'IS_' + {'朋友':'FRIEND', '敌人':'ENEMY', '家人':'FAMILY',
                    '老师':'MENTOR', '学生':'STUDENT', '上司':'BOSS', '下属':'SUBORDINATE'}.get(m.group(3), 'RELATED') + '_OF', m.group(2))),

        (r'([\u4e00-\u9fa5A-Za-z]{1,15})爱上了([\u4e00-\u9fa5A-Za-z]{1,15})', lambda m: (m.group(1), 'LOVES', m.group(2))),
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})喜欢([\u4e00-\u9fa5A-Za-z]{1,15})', lambda m: (m.group(1), 'LIKES', m.group(2))),
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})讨厌([\u4e00-\u9fa5A-Za-z]{1,15})', lambda m: (m.group(1), 'HATES', m.group(2))),
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})住在([\u4e00-\u9fa5]{1,10})', lambda m: (m.group(1), 'LIVES_IN', m.group(2))),
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})去了([\u4e00-\u9fa5]{1,10})', lambda m: (m.group(1), 'TRAVELS_TO', m.group(2))),
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})拥有([\u4e00-\u9fa5A-Za-z]{1,15})', lambda m: (m.group(1), 'OWNS', m.group(2))),
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})给([\u4e00-\u9fa5A-Za-z]{1,15})了(.{1,15})', lambda m: (m.group(1), 'GAVE_TO', m.group(2))),

        # 英文 RP 模式
        (r'(\w+) is (?:a )?friend of (\w+)', lambda m: (m.group(1), 'IS_FRIEND_OF', m.group(2))),
        (r'(\w+) loves (\w+)', lambda m: (m.group(1), 'LOVES', m.group(2))),
        (r'(\w+) lives in (\w+)', lambda m: (m.group(1), 'LIVES_IN', m.group(2))),

        # ─────────────────────────────────────────────────────
        # 2. 因果关系 / Causal Relations  (6 rules)
        # ─────────────────────────────────────────────────────

        # ZH: A 导致/引起/造成 B
        (r'({z})(?:导致|引起|造成|引发|促使)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'CAUSES', m.group(2))),
        # ZH: 因为A所以B / A因此B
        (r'因为({z})(?:，|,|\s)*所以({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'CAUSES', m.group(2))),
        # ZH: A 依赖 B
        (r'({z})依赖于?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'DEPENDS_ON', m.group(2))),
        # EN: A causes / leads to / results in B
        (r'({e}) (?:causes?|leads? to|results? in|triggers?|gives? rise to) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'CAUSES', m.group(2))),
        # EN: A depends on B
        (r'({e}) depends? on ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'DEPENDS_ON', m.group(2))),
        # EN: A is caused by B  (reversed direction)
        (r'({e}) is caused by ({e})'.format(e=_EN),
         lambda m: (m.group(2), 'CAUSES', m.group(1))),

        # ─────────────────────────────────────────────────────
        # 3. 商业 / Business Relations  (8 rules)
        # ─────────────────────────────────────────────────────

        # ZH: A 收购/并购 B
        (r'({z})(?:收购|并购|兼并)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'ACQUIRES', m.group(2))),
        # ZH: A 与 B 合作
        (r'({z})与({z})(?:合作|协作|联手)'.format(z=_ZH),
         lambda m: (m.group(1), 'PARTNERS_WITH', m.group(2))),
        # ZH: A 竞争 B / A 是 B 的竞争对手
        (r'({z})(?:是({z})的竞争对手|与({z})竞争)'.format(z=_ZH),
         lambda m: (m.group(1), 'COMPETES_WITH', m.group(2) or m.group(3))),
        # ZH: A 供应/供给 B
        (r'({z})(?:供应|供给|提供)(?:给|了)?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'SUPPLIES', m.group(2))),
        # ZH: A 雇佣/聘请 B
        (r'({z})(?:雇佣|聘请|招聘|雇用)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'EMPLOYS', m.group(2))),
        # EN: A acquires / merges with B
        (r'({e}) (?:acquires?|bought|merged? with|takes? over) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'ACQUIRES', m.group(2))),
        # EN: A partners / collaborates with B
        (r'({e}) (?:partners?|collaborates?|cooperates?) with ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'PARTNERS_WITH', m.group(2))),
        # EN: A competes with B
        (r'({e}) competes? with ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'COMPETES_WITH', m.group(2))),

        # ─────────────────────────────────────────────────────
        # 4. 金融 / Financial Relations  (6 rules)
        # ─────────────────────────────────────────────────────

        # ZH: A 投资 B
        (r'({z})投资了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'INVESTS_IN', m.group(2))),
        # ZH: A 融资于 B / A 从 B 融资
        (r'({z})(?:从({z}))?(?:融资|获得融资)'.format(z=_ZH),
         lambda m: (m.group(2) if m.group(2) else 'UNKNOWN', 'FUNDS', m.group(1))),
        # ZH: A 借贷给 B / A 贷款给 B
        (r'({z})(?:借贷|贷款)给({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'LENDS_TO', m.group(2))),
        # EN: A invests in B
        (r'({e}) invests? in ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'INVESTS_IN', m.group(2))),
        # EN: A funds / finances B
        (r'({e}) (?:funds?|finances?|bankrolls?) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'FUNDS', m.group(2))),
        # EN: A is a subsidiary of B
        (r'({e}) is (?:a )?subsidiary of ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'SUBSIDIARY_OF', m.group(2))),

        # ─────────────────────────────────────────────────────
        # 5. 技术 / Technical & Engineering Relations  (8 rules)
        # ─────────────────────────────────────────────────────

        # ZH: A 基于 B / A 使用 B
        (r'({z})(?:基于|使用|采用|运行在)({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'USES', m.group(2))),
        # ZH: A 实现/实作 B
        (r'({z})(?:实现|实作|实装)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'IMPLEMENTS', m.group(2))),
        # ZH: A 继承 B / A 扩展 B
        (r'({z})(?:继承|扩展|派生自)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'EXTENDS', m.group(2))),
        # ZH: A 兼容 B
        (r'({z})(?:兼容|支持)({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'COMPATIBLE_WITH', m.group(2))),
        # EN: A is built on / uses / depends on B
        (r'({e}) (?:is built on|uses?|utilizes?|runs? on|leverages?) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'USES', m.group(2))),
        # EN: A implements B
        (r'({e}) implements? ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'IMPLEMENTS', m.group(2))),
        # EN: A extends / inherits from B
        (r'({e}) (?:extends?|inherits? from) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'EXTENDS', m.group(2))),
        # EN: A is compatible with B
        (r'({e}) is compatible with ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'COMPATIBLE_WITH', m.group(2))),

        # ─────────────────────────────────────────────────────
        # 6. 学术 / Academic & Research Relations  (8 rules)
        # ─────────────────────────────────────────────────────

        # ZH: A 发表/发布/出版 B
        (r'({z})(?:发表|发布|出版)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'PUBLISHES', m.group(2))),
        # ZH: A 引用 B
        (r'({z})引用了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'CITES', m.group(2))),
        # ZH: A 研究/探索 B
        (r'({z})(?:研究|探索|探讨|调研)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'RESEARCHES', m.group(2))),
        # ZH: A 毕业于 B / A 就读于 B
        (r'({z})(?:毕业于|就读于|就学于)({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'STUDIED_AT', m.group(2))),
        # EN: A publishes B
        (r'({e}) (?:publishes?|authored?|wrote) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'PUBLISHES', m.group(2))),
        # EN: A cites B
        (r'({e}) cites? ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'CITES', m.group(2))),
        # EN: A researches / studies B
        (r'({e}) (?:researches?|studies?|investigates?) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'RESEARCHES', m.group(2))),
        # EN: A graduated from / studied at B
        (r'({e}) (?:graduated from|studied at|attended) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'STUDIED_AT', m.group(2))),

        # ─────────────────────────────────────────────────────
        # 7. 科学 / Scientific Relations  (6 rules)
        # ─────────────────────────────────────────────────────

        # ZH: A 由 B 组成 / A 包含 B
        (r'({z})(?:由({z})组成|包含({z}))'.format(z=_ZH),
         lambda m: (m.group(1), 'COMPOSED_OF', m.group(2) or m.group(3))),
        # ZH: A 属于 B (分类)
        (r'({z})属于({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'BELONGS_TO', m.group(2))),
        # ZH: A 产生/合成 B
        (r'({z})(?:产生|合成|生成|制造)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'PRODUCES', m.group(2))),
        # EN: A is composed of / contains B
        (r'({e}) (?:is composed of|contains?|comprises?) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'COMPOSED_OF', m.group(2))),
        # EN: A belongs to / is a type of B
        (r'({e}) (?:belongs? to|is (?:a )?(?:type|kind|form|class) of) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'BELONGS_TO', m.group(2))),
        # EN: A produces / synthesizes B
        (r'({e}) (?:produces?|synthesizes?|generates?|creates?) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'PRODUCES', m.group(2))),

        # ─────────────────────────────────────────────────────
        # 8. 法律 / Legal Relations  (6 rules)
        # ─────────────────────────────────────────────────────

        # ZH: A 起诉/控告 B
        (r'({z})(?:起诉|控告|告了|诉讼)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'SUES', m.group(2))),
        # ZH: A 违反 B (法规)
        (r'({z})违反了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'VIOLATES', m.group(2))),
        # ZH: A 授权/许可 B
        (r'({z})(?:授权|许可|批准)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'AUTHORIZES', m.group(2))),
        # EN: A sues / litigates against B
        (r'({e}) (?:sues?|litigates? against|prosecutes?) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'SUES', m.group(2))),
        # EN: A violates B
        (r'({e}) violates? ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'VIOLATES', m.group(2))),
        # EN: A is regulated by B
        (r'({e}) is regulated by ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'REGULATED_BY', m.group(2))),

        # ─────────────────────────────────────────────────────
        # 9. 医学 / Medical Relations  (8 rules)
        # ─────────────────────────────────────────────────────

        # ZH: A 治疗 B (疾病)
        (r'({z})(?:治疗|医治|缓解|治愈)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'TREATS', m.group(2))),
        # ZH: A 诊断出 B
        (r'({z})(?:诊断出|确诊为|患有)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'DIAGNOSED_WITH', m.group(2))),
        # ZH: A 的症状是 B / A 表现为 B
        (r'({z})(?:的症状是|表现为|症状包括)({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'HAS_SYMPTOM', m.group(2))),
        # ZH: A 抑制/阻断 B
        (r'({z})(?:抑制|阻断|阻止)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'INHIBITS', m.group(2))),
        # EN: A treats / cures B
        (r'({e}) (?:treats?|cures?|alleviates?|remedies?) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'TREATS', m.group(2))),
        # EN: A is diagnosed with B
        (r'({e}) (?:is diagnosed with|has|suffers? from) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'DIAGNOSED_WITH', m.group(2))),
        # EN: A inhibits / blocks B
        (r'({e}) (?:inhibits?|blocks?|suppresses?) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'INHIBITS', m.group(2))),
        # EN: A is a symptom of B
        (r'({e}) is (?:a )?symptom of ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'SYMPTOM_OF', m.group(2))),

        # ─────────────────────────────────────────────────────
        # 10. 通用知识 / General Knowledge Relations  (10 rules)
        # ─────────────────────────────────────────────────────

        # ZH: A 位于/坐落于 B
        (r'({z})(?:位于|坐落于|地处|在)({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'LOCATED_IN', m.group(2))),
        # ZH: A 创建/创立/发明 B
        (r'({z})(?:创建|创立|创办|发明|创造|建立)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'CREATED', m.group(2))),
        # ZH: A 管理/领导 B
        (r'({z})(?:管理|领导|指挥|统治|主管)着?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'MANAGES', m.group(2))),
        # ZH: A 影响 B
        (r'({z})影响了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'INFLUENCES', m.group(2))),
        # ZH: A 参与/加入 B
        (r'({z})(?:参与|加入|参加)了?({z})'.format(z=_ZH),
         lambda m: (m.group(1), 'PARTICIPATES_IN', m.group(2))),
        # EN: A is located in B
        (r'({e}) is (?:located|situated|based) in ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'LOCATED_IN', m.group(2))),
        # EN: A created / founded / invented B
        (r'({e}) (?:created?|founded?|invented?|established?) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'CREATED', m.group(2))),
        # EN: A manages / leads B
        (r'({e}) (?:manages?|leads?|directs?|governs?|heads?) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'MANAGES', m.group(2))),
        # EN: A influences / affects B
        (r'({e}) (?:influences?|affects?|impacts?) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'INFLUENCES', m.group(2))),
        # EN: A participates in / joins B
        (r'({e}) (?:participates? in|joins?|takes? part in) ({e})'.format(e=_EN),
         lambda m: (m.group(1), 'PARTICIPATES_IN', m.group(2))),
    ]
    
    def __init__(self, entity_extractor=None):
        self.entity_extractor = entity_extractor
    
    def extract(self, text: str, turn: int = 0, entities: list = None) -> List[Tuple[str, str, str, str]]:
        """
        从文本中提取关系
        
        Args:
            text: 原始文本
            turn: 轮次（暂未使用）
            entities: 可选，已提取的实体列表。如果提供则复用，否则重新提取。
                      支持 ExtractedEntity 对象列表或字符串列表。
        
        Returns:
            [(source, relation_type, target, source_text), ...]
        """
        relations = []
        
        # 1. 基于模式匹配
        for pattern, extractor in self.PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    source, rel_type, target = extractor(match)
                    relations.append((source.strip(), rel_type, target.strip(), match.group(0)))
                except Exception:
                    continue
        
        # 2. 基于共现（同一句话中出现的实体可能有关系）
        # 优先使用传入的实体列表，否则重新提取
        if entities is None and self.entity_extractor:
            entities = self.entity_extractor.extract(text)
        
        if entities:
            sentences = re.split(r'[。.!?！？\n]', text)
            
            # 统一转换为实体名列表
            entity_names = []
            for e in entities:
                if hasattr(e, 'name'):
                    entity_names.append(e.name)
                elif isinstance(e, str):
                    entity_names.append(e)
                elif isinstance(e, dict) and 'name' in e:
                    entity_names.append(e['name'])
            
            for sentence in sentences:
                if len(sentence) < 3:
                    continue
                # 找出此句子中包含的实体
                sentence_entities = [name for name in entity_names if name in sentence]
                # 如果同一句话有多个实体，建立弱关系
                if len(sentence_entities) >= 2:
                    for i, e1 in enumerate(sentence_entities[:-1]):
                        for e2 in sentence_entities[i+1:]:
                            relations.append((e1, 'MENTIONED_WITH', e2, sentence))
        
        return relations
