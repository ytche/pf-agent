# -*- coding: utf-8 -*-
"""M18：译者吐槽/译注删除（KN119 闭环，2026-08-04）

KN119 处置口径（已知问题记录）：按 KN091 先例全库扫描吐槽/译注模式，
清单化后清洗；**保留合法规则注释**（规则数据/术语引用/规则解读）。

删除类别：
- 吐槽/情绪/第一人称口水（【吐槽】【好贵！！】【坑爹】【魂淡】【脑残】…）
- 翻译元信息（译名选择、翻译说明、查无此/存疑/原文如此/勘误/求解、见下文导航）
- 不准确猜测（如「大概是1点技能学2种语言」与正文「1种额外语言」矛盾）
- 插句中破坏流畅的译者补充（黛丝娜全名等非机制背景）

保留清单（合法规则注释，不删）：
- page_129：次要天生武器 BAB 编注 / 先知秘示域奖励法术译注（规则解读）
- page_160：用毒（Poison Use）职业列表编注（规则数据）
- page_165：侏儒精类起源译注（种族机制）
- page_167：精制镣铐脱逃DC35扯断DC28 编注（规则数据）
- page_17：凶猛为兽人特性半兽人没有译注 / 凶暴决意满足先决条件编注（规则解读）
- page_205：战士体质+2→每级多负2点血译注（规则解读）
- page_238：瘟疫之瓶取代突变药剂编注 / 次要天生武器编注（规则解读）
- page_402：类人生物子类术语译注（术语解释）
- page_403：小型1d3中型1d4 / 无法潜行时机译注（规则数据）
- ISR 其他：Xotani CR20 魔法兽注（怪物数据）
- 矮人汇总：工匠（Craftsman）PFS 不开注（PFS 规则）
- page_1456：按葫芦莱西为整轮动作注（动作类型）

删除原则（KN091 先例）：字节级删除文本本身，行尾/周围空白保留。
源数据为混合行尾（CRLF+LF 并存），跨行串自动适配两种行尾。

用法：python3 m18_fix_translator.py（幂等：每处验证旧串恰好存在 1 次）
"""
import glob
import re
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
ROOT = BASE / "pf_rules_md_organized" / "种族"

# 文件名 → 真实路径映射（page_*.md 分布在 常见种族/ 核心种族/ 等子目录）
FILE_MAP = {p.split("/")[-1]: p for p in glob.glob(str(ROOT / "**" / "*.md"), recursive=True)}

# (文件, 旧串) —— 删除；旧串必须恰好存在 1 次
DELETES: list[tuple[str, str]] = []
# (文件, 旧串, 新串) —— 替换（page_163 速查块尾部）
REPLACES: list[tuple[str, str, str]] = []


def dele(fname: str, old: str) -> None:
    DELETES.append((fname, old))


def repl(fname: str, old: str, new: str) -> None:
    REPLACES.append((fname, old, new))


# ---- page_10（半兽人）----
dele("page_10.md",
     "【译注：很不幸，实际上半兽人铳士的天赋职业奖励为【枪柄打击】炫技攻击检定+1/3。因此上面的举例当作是个计算说明就好。】")
# ---- page_11（人类）----
dele("page_11.md", "【译注：身高单位是英尺英吋，你们懂的。】")
dele("page_11.md", "【编注：1英尺=12英吋。】")
# ---- page_13（精灵）----
dele("page_13.md",
     "【译者吐槽：蒂朵——人类啊？太野蛮了。哦史列因还蛮聪明的。嗯？你说潘恩？唔……///^_^///】")
dele("page_13.md", "【译者注：怪不得很多半精灵魔射手专挑精灵下手。】")
# ---- page_14（侏儒）----
dele("page_14.md", "【编者吐槽：你都不写上文那四个专属科研发现是要闹哪样OTL】")
dele("page_14.md", "【译注：大概是1点技能学2种语言的意思】")
# ---- page_13（精灵）小半页描述译注（元信息+指向核心手册，删）----
dele("page_13.md",
     "【译注：此处的小半页描述基本都是充数的，请参见核心手册中德鲁伊动物伙伴的描述，故略去。此外，你可以选择不让植物伙伴获得4级时列出的好处，而是只让其力量和体质分别+2。】")
# ---- page_1366（侏儒相关）----
dele("page_1366.md", "［注：大概是1点技能学2种语言的意思］")
dele("page_1366.md", "［注：侏儒的话也许是地底侏儒的遗传？］")
# ---- page_15（半精灵）----
dele("page_15.md",
     "【译者吐槽：坦尼斯老弟，咱明天要去砍小龙人了，今儿再陪俺火炉喝一杯。】")
dele("page_15.md",
     "【译者吐槽：泰斯！我会把你从那条鳄鱼的嘴里揪出来的，不过你最好先解释下为啥我的钱包又在你手里？！】")
dele("page_15.md",
     "【译注：原文如此，但是关于等级的数据一定在哪里有些不对，估计是该能力加值的提升是在17和20级，而不是16和19级。】")
dele("page_15.md",
     "【编注：我倒觉得错的是此能力获得等级，【伪装】是游侠的12级能力。】")
dele("page_15.md", "【编者吐槽：喂那躺在地上的我不就死透了吗？！】")
# ---- page_16（半身人）----
dele("page_16.md", "【译注：梦境，星辰，旅行，机运之女神黛丝娜（Desna）】")
dele("page_16.md", "【编注：譬如你5级，那么所受减值就是-15。】")
dele("page_16.md", "【译者吐槽：我能明白为什么指环王第一部的霍比特之乡如同仙境一般了。】")
# ---- page_17（半兽人）----
dele("page_17.md",
     "【译注：旧CHM翻译为战斗骑乘（Combat \nRiding），此处以paizo官网为准。】")
dele("page_17.md", "【编者吐槽：2-20+17=1，原文如此，可作为数死早的范例。】")
# ---- page_18（人类海贼）----
dele("page_18.md",
     "【编注：豁免DC原文如此，但估计应为“10+1/2海贼等级+魅力修正”。】")
dele("page_18.md",
     "【译注：‘老水手的诅咒’以及‘黑色印记’法术在人类法术中，见下文。】")
dele("page_18.md", "【译注：上限还是用感知决定，而且是paizo故意的】")
# ---- page_19（半兽人/天狗装备段）----
dele("page_19.md", "【编者吐槽：你们够了……】")
dele("page_19.md",
     "【译注：查无此天赋，疑为【定位攻击（Positioning Attack, APG）】。】")
dele("page_19.md",
     "【译注：瘟疫医生面具（plague doctor’s mask）为中世纪欧洲医生戴的面具，玩过刺客信条的人应该都会了解吧。有兴趣可以google图片一下。】")
# ---- page_27（黑暗精灵?）----
dele("page_27.md", "【编者吐槽：看，那里有一坨4英尺高会动的阴影。去掉头就可以吃了。】")
# ---- page_129（神裔）----
dele("page_129.md",
     "【译注：因为本职业中出现大量不同的平静，宁静，平和，安宁词汇，故为了不产生记忆困扰，统一译作宁静。】")
# ---- page_160（猫族）----
dele("page_160.md", "【译注：拥有攀爬速度不是已经可以取10了么！坑爹么？！】")
dele("page_160.md", "【译者吐槽：卧了个大槽！尼玛这是喵星人还是汪星人啊！】")
# ---- page_163（吸血鬼/吸血裔）----
dele("page_163.md", "【译注：原文没有提到豁免的问题。】")
dele("page_163.md", "【译注：请参见《恶魔城——月下夜想曲》。】")
repl("page_163.md", "，译者 \n**沙包**", "")  # 保留【速查：吸血鬼弱点】主体
# ---- page_164（卓尔，论坛外链译注）----
dele("page_164.md",
     "【译注：点击查看[巨壁虎](http://www.goddessfantasy.net/bbs/index.php?topic=50580)和[巨大化模板](http://www.goddessfantasy.net/bbs/index.php?topic=50681)。】")
dele("page_164.md",
     "【译注：天界与炼狱模板见[http://45.79.87.129/bbs/index.php?topic=63055.msg585513#msg585513](http://45.79.87.129/bbs/index.php?topic=63055.msg585513#msg585513)】")
# ---- page_165（窃影鬼）----
dele("page_165.md", "【译注：原文并没注明操控影子的动作类型。】")
# ---- page_166（地精）----
dele("page_166.md", "【译注：原文较为混乱，此处依据举例整理了格式。】")
dele("page_166.md", "【译者吐槽：我这可是涂满了火药的炸弹】")
# ---- page_167（地精/大地精）----
dele("page_167.md", "【译注：原文并没注明是何种豁免，不过耳聋一般都是强韧吧。】")
dele("page_167.md", "【译者吐槽：这就是大！地！精！】")
# ---- page_204（狗头人）----
dele("page_204.md", "【编注：此处存疑。】")
dele("page_204.md",
     "【译注：【猎手羁绊】赋予盟友的宿敌是按照种类分、与敌人数量无关，此处怀疑是提高赋予盟友的宿敌加值加成。】")
dele("page_204.md",
     "【编注：这个说法很奇怪，因为通过常规重击或击杀恢复勇毅值也只有1点。】")
dele("page_204.md",
     "【译注：核心书隐匿技能说明冲锋或者奔跑时无法隐匿。不知是否有勘误，求解。】")
# ---- page_205（兽人）----
dele("page_205.md", "【编注：体质法术为旧版奇葩能力，留着纪念下。】")
dele("page_205.md", "【译注：我不能接受男性兽人女巫这种说法啊魂淡……】")
dele("page_205.md", "【译注：这不是脑残么，兽人肌肉女巫变体没魔宠，兽人标准女巫智力-2！】")
# ---- page_238（鼠族）----
dele("page_238.md", "【编注：节操起见，1点为宜。】")
dele("page_238.md",
     "【译注：查无此发现，疑为【毒性肌肤（Nauseating \nFlesh, \nUC）】。】")
dele("page_238.md",
     "【译注：该能力没有提及需要剩余的勇毅值、消耗的勇毅值或任何和勇毅值相关的描述。】")
dele("page_238.md", "【译者吐槽：现在先进火器都出来了，小老鼠们不做飞行员或坦克手吗！】")
# ---- page_324 ----
dele("page_324.md", "【译注：原文如此，与后面的每日使用次数矛盾】")
# ---- page_440（土元素裔）----
dele("page_440.md", "【好贵！！】")
dele("page_440.md",
     "【译注：原文是shaitan \nancestors，虽然查到了Shaitan是古代苏默人（Sumerian）所敬拜的魔神沙旦（Shaitan），但是不确定是不是沿用的这个含义，所以在此音译了这个词。】")
# ---- page_442 ----
dele("page_442.md", "【译注：就是说穿刺伤害型武器啦。】")
dele("page_442.md", "【译注：等等你们产什么，拿什么去交易啊？农夫山泉？】")
# ---- page_815/816/940（怪物种族）----
dele("page_815.md", "（译者注：原文疑似漏掉了成分。）")
dele("page_816.md", "（译者吐槽：合法幼女？）")
dele("page_940.md", "（译者注：这里可能是PAIZO在写的时候用了3R版本的多重射击）")
# ---- 人类种族特性替换汇总 ----
dele("人类种族特性替换汇总.md", "［注：切利亚斯人和塔尔多人表示？？？］")
# ---- 内海种族ISR_新种族（兽态人 3 注）----
dele("内海种族ISR_新种族.md",
     "［注：男神网上的是B5书的版本，但由于缺少不少数据，所以我建议还是以ISR的版本为准］")
dele("内海种族ISR_新种族.md", "［注：其他我想叫他半兽化人或兽化裔，不过还是沿用以前译名吧］")
dele("内海种族ISR_新种族.md", "［注：原书的图都太丑了，我实在不想放…］")
# ---- 夜之血脉BotN（僵尸裔/茉莉裔）----
dele("夜之血脉BotN_吸血裔种族特性.md", "【吐槽：这是因为僵尸是用跳的缘故么？")
dele("夜之血脉BotN_吸血裔种族特性.md", "（译者：这话好别扭，求更好的翻译）")
dele("夜之血脉BotN_吸血裔种族特性.md", "【这个有意思！！！……】")
# ---- 冒险之路AP_怪物 ----
dele("冒险之路AP_怪物.md", "【译注：该卡的生态中没有宝藏，原文如此】")
# ---- page_1456（莱西）----
dele("page_1456.md", "【译注：此处提及confused一词，但个人认为仅为描述用语】")
dele("page_1456.md", "【译注：被遗忘的捕蝇草莱西在角落哭泣】")


def variants(s: str):
    """跨行串适配混合行尾（CRLF 与 LF 并存）"""
    yield s
    if "\n" in s:
        yield s.replace("\n", "\r\n")


def variants(s: str):
    """跨行串适配混合行尾（CRLF 与 LF 并存）"""
    yield s
    if "\n" in s:
        yield s.replace("\n", "\r\n")


def main() -> None:
    """二进制替换：只删目标串字节，CRLF 行尾原样保留（pf-organized-source-crlf-convention）"""
    import re
    from collections import defaultdict
    blobs: dict[str, bytes] = {}
    for fname, *_ in DELETES + REPLACES:
        if fname not in blobs:
            blobs[fname] = Path(FILE_MAP[fname]).read_bytes()
    applied = 0
    for fname, old in DELETES:
        data = blobs[fname]
        old_b = old.encode("utf-8")
        for v in variants(old):
            vb = v.encode("utf-8")
            n = data.count(vb)
            if n == 0:
                continue
            if n > 1:
                print(f"[跳过/重复] {fname}: {old[:40]!r} 出现 {n} 次")
                break
            blobs[fname] = data.replace(vb, b"")
            applied += 1
            break
        else:
            print(f"[跳过/缺失] {fname}: {old[:40]!r}")
    for fname, old, new in REPLACES:
        data = blobs[fname]
        old_b = old.encode("utf-8")
        new_b = new.encode("utf-8")
        for v in variants(old):
            vb = v.encode("utf-8")
            n = data.count(vb)
            if n == 0:
                continue
            if n > 1:
                print(f"[跳过/重复] {fname} (替换): {old[:40]!r} 出现 {n} 次")
                break
            blobs[fname] = data.replace(vb, new_b)
            applied += 1
            break
        else:
            print(f"[跳过/缺失] {fname} (替换): {old[:40]!r}")
    print(f"应用 {applied}/{len(DELETES) + len(REPLACES)} 处")
    for fname, data in blobs.items():
        Path(FILE_MAP[fname]).write_bytes(data)
    # 删除后校验：已删模式不应残留（抽样）；CRLF 不应减少
    leftovers = []
    for fname, data in blobs.items():
        text = data.decode("utf-8")
        for pat, desc in [
            (r"【(?:译者|编者)?(?:吐槽|译注|编注)", "吐槽/译注/编注"),
            (r"【好贵！！】", "好贵"),
            (r"（译者|［注：|〔注：", "译者括号注"),
            (r"坑爹|闹哪样|魂淡|脑残|死透|卧了个大槽", "口水词"),
        ]:
            for m in re.finditer(pat, text):
                leftovers.append(f"{fname}: {desc}@{text[max(0,m.start()-10):m.end()+10]!r}")
        crlf = data.count(b"\r\n")
        if crlf == 0:
            print(f"[警告] {fname} 无 CRLF（LF 原本或异常）")
    if leftovers:
        print(f"[残留 {len(leftovers)} 处]（人工复核，可能为保留项或新增发现）:")
        for l in leftovers[:25]:
            print("  ", l)
    else:
        print("[校验] 已删模式零残留")


if __name__ == "__main__":
    main()
