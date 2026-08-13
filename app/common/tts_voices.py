# -*- coding: utf-8 -*-
"""
通义 TTS 音色常量（SSOT）

按模型系列分组定义 DashScope 语音合成可用音色列表。
不同音频模型支持不同音色集合，前端切换模型后应重新获取对应音色列表。

数据源（阿里云百炼官方文档）：
  - CosyVoice 音色列表：https://help.aliyun.com/zh/model-studio/tts-voice-list
  - Sambert：官方 Sambert 音色列表
"""

# ==================== CosyVoice v1 系列音色（基础 voice ID，无后缀）====================
_COSYVOICE_V1_VOICES = [
    {"id": "longxiaochun", "name": "龙小淳", "gender": "female", "desc": "知性积极女"},
    {"id": "longwan", "name": "龙婉", "gender": "female", "desc": "温柔婉约女"},
    {"id": "longcheng", "name": "龙橙", "gender": "male", "desc": "沉稳磁性男"},
    {"id": "longhua", "name": "龙华", "gender": "female", "desc": "元气甜美女"},
    {"id": "longfei", "name": "龙飞", "gender": "male", "desc": "热血磁性男"},
    {"id": "longyue", "name": "龙月", "gender": "female", "desc": "清新自然女"},
    {"id": "longyuan", "name": "龙渊", "gender": "male", "desc": "深沉内敛男"},
    {"id": "longshu", "name": "龙叔", "gender": "male", "desc": "浑厚大气男"},
]

# ==================== CosyVoice v2 系列音色（_v2 后缀 voice ID）====================
_COSYVOICE_V2_VOICES = [
    {"id": "longxiaochun_v2", "name": "龙小淳", "gender": "female", "desc": "知性积极女"},
    {"id": "longwan_v2", "name": "龙婉", "gender": "female", "desc": "温柔婉约女"},
    {"id": "longcheng_v2", "name": "龙橙", "gender": "male", "desc": "沉稳磁性男"},
    {"id": "longhua_v2", "name": "龙华", "gender": "female", "desc": "元气甜美女"},
    {"id": "longfei_v2", "name": "龙飞", "gender": "male", "desc": "热血磁性男"},
    {"id": "longyue_v2", "name": "龙月", "gender": "female", "desc": "清新自然女"},
    {"id": "longyuan_v2", "name": "龙渊", "gender": "male", "desc": "深沉内敛男"},
    {"id": "longshu_v2", "name": "龙叔", "gender": "male", "desc": "浑厚大气男"},
]

# ==================== CosyVoice v3-plus 系列音色（仅官方标杆音色，无后缀）====================
# 官方文档：v3-plus 仅提供 2 个社交陪伴标杆音色，不可与 v3-flash 混用
_COSYVOICE_V3_PLUS_VOICES = [
    # 社交陪伴（标杆音色）
    {"id": "longanyang", "name": "龙安洋", "gender": "male", "desc": "阳光大男孩"},
    {"id": "longanhuan", "name": "龙安欢", "gender": "female", "desc": "欢脱元气女（情感版）"},
]

# ==================== CosyVoice v3-flash 系列音色（官方完整列表，_v3 后缀）====================
# 数据源：https://help.aliyun.com/zh/model-studio/tts-voice-list（2026-07-07 更新）
# 注意：longanhuan_v3 与 longanhuan 均为 v3-flash 合法独立音色，功能不同，不可合并：
#   - longanhuan_v3：支持方言（普通话、广东话、东北话等9种）
#   - longanhuan：支持情感控制（neutral、happy 等7种情感值）
_COSYVOICE_V3_FLASH_VOICES = [
    # 社交陪伴（标杆音色）
    {"id": "longanyang", "name": "龙安洋", "gender": "male", "desc": "阳光大男孩"},
    {"id": "longanhuan_v3", "name": "龙安欢", "gender": "female", "desc": "欢脱元气女（方言版）"},
    {"id": "longanhuan", "name": "龙安欢", "gender": "female", "desc": "欢脱元气女（情感版）"},
    # 童声（标杆音色）
    {"id": "longhuhu_v3", "name": "龙呼呼", "gender": "female", "desc": "天真烂漫女童"},
    # 智能玩具/儿童故事机
    {"id": "longpaopao_v3", "name": "龙泡泡", "gender": "female", "desc": "飞天泡泡音"},
    {"id": "longjielidou_v3", "name": "龙杰力豆", "gender": "male", "desc": "阳光顽皮男"},
    {"id": "longxian_v3", "name": "龙仙", "gender": "female", "desc": "豪放可爱女"},
    {"id": "longling_v3", "name": "龙铃", "gender": "female", "desc": "稚气呆板女"},
    # 消费电子-儿童有声书
    {"id": "longshanshan_v3", "name": "龙闪闪", "gender": "female", "desc": "戏剧化童声"},
    {"id": "longniuniu_v3", "name": "龙牛牛", "gender": "male", "desc": "阳光男童声"},
    # 方言
    {"id": "longjiaxin_v3", "name": "龙嘉欣", "gender": "female", "desc": "优雅粤语女"},
    {"id": "longjiayi_v3", "name": "龙嘉怡", "gender": "female", "desc": "知性粤语女"},
    {"id": "longanyue_v3", "name": "龙安粤", "gender": "male", "desc": "欢脱粤语男"},
    {"id": "longlaotie_v3", "name": "龙老铁", "gender": "male", "desc": "东北直率男"},
    {"id": "longshange_v3", "name": "龙陕哥", "gender": "male", "desc": "原味陕北男"},
    {"id": "longanmin_v3", "name": "龙安闽", "gender": "female", "desc": "清纯萝莉女"},
    # 出海营销-韩语
    {"id": "loongkyong_v3", "name": "loongkyong", "gender": "female", "desc": "韩语女"},
    {"id": "loongjihun_v3", "name": "Jihun", "gender": "male", "desc": "韩语男"},
    # 出海营销-日语
    {"id": "loongriko_v3", "name": "Riko", "gender": "female", "desc": "二次元霓虹女"},
    {"id": "loongtomoka_v3", "name": "loongtomoka", "gender": "female", "desc": "日语女"},
    {"id": "loongtomoya_v3", "name": "loongtomoya", "gender": "male", "desc": "日语男"},
    {"id": "loongyuuna_v3", "name": "Yuuna", "gender": "female", "desc": "日语女"},
    {"id": "loongyuuma_v3", "name": "Yuuma", "gender": "male", "desc": "日语男"},
    # 出海营销-印尼语
    {"id": "loongindah_v3", "name": "loongindah", "gender": "female", "desc": "印尼女"},
    # 出海营销-美式英语
    {"id": "loongabby_v3", "name": "loongabby", "gender": "female", "desc": "美式英文女"},
    {"id": "loongandy_v3", "name": "loongandy", "gender": "male", "desc": "美式英文男"},
    {"id": "loongannie_v3", "name": "loongannie", "gender": "female", "desc": "美式英文女"},
    {"id": "loongava_v3", "name": "loongava", "gender": "female", "desc": "美式英文女"},
    {"id": "loongbeth_v3", "name": "loongbeth", "gender": "female", "desc": "美式英文女"},
    {"id": "loongbetty_v3", "name": "loongbetty", "gender": "female", "desc": "美式英文女"},
    {"id": "loongcally_v3", "name": "loongcally", "gender": "female", "desc": "美式英文女"},
    {"id": "loongcindy_v3", "name": "loongcindy", "gender": "female", "desc": "美式英文女"},
    {"id": "loongdavid_v3", "name": "loongdavid", "gender": "male", "desc": "美式英文男"},
    {"id": "loongdonna_v3", "name": "loongdonna", "gender": "female", "desc": "美式英文女"},
    # 出海营销-英式英语
    {"id": "loongemily_v3", "name": "loongemily", "gender": "female", "desc": "英式英文女"},
    {"id": "loongeric_v3", "name": "loongeric", "gender": "male", "desc": "英式英文男"},
    {"id": "loongluna_v3", "name": "loongluna", "gender": "female", "desc": "英式英文女"},
    {"id": "loongluca_v3", "name": "loongluca", "gender": "male", "desc": "英式英文男"},
    # 诗词朗诵
    {"id": "longfei_v3", "name": "龙飞", "gender": "male", "desc": "热血磁性男"},
    # 电话销售
    {"id": "longyingxiao_v3", "name": "龙应笑", "gender": "female", "desc": "清甜推销女"},
    # 客服
    {"id": "longyingxun_v3", "name": "龙应询", "gender": "male", "desc": "年轻青涩男"},
    {"id": "longyingjing_v3", "name": "龙应静", "gender": "female", "desc": "低调冷静女"},
    {"id": "longyingling_v3", "name": "龙应聆", "gender": "female", "desc": "温和共情女"},
    {"id": "longyingtao_v3", "name": "龙应桃", "gender": "female", "desc": "温柔淡定女"},
    # 语音助手
    {"id": "longxiaochun_v3", "name": "龙小淳", "gender": "female", "desc": "知性积极女"},
    {"id": "longxiaoxia_v3", "name": "龙小夏", "gender": "female", "desc": "沉稳权威女"},
    {"id": "longyumi_v3", "name": "YUMI", "gender": "female", "desc": "正经青年女"},
    {"id": "longanyun_v3", "name": "龙安昀", "gender": "male", "desc": "居家暖男"},
    {"id": "longanwen_v3", "name": "龙安温", "gender": "female", "desc": "优雅知性女"},
    {"id": "longanli_v3", "name": "龙安莉", "gender": "female", "desc": "利落从容女"},
    {"id": "longanlang_v3", "name": "龙安朗", "gender": "male", "desc": "清爽利落男"},
    {"id": "longyingmu_v3", "name": "龙应沐", "gender": "female", "desc": "优雅知性女"},
    # 社交陪伴
    {"id": "longantai_v3", "name": "龙安台", "gender": "female", "desc": "嗲甜台湾女"},
    {"id": "longhua_v3", "name": "龙华", "gender": "female", "desc": "元气甜美女"},
    {"id": "longcheng_v3", "name": "龙橙", "gender": "male", "desc": "智慧青年男"},
    {"id": "longze_v3", "name": "龙泽", "gender": "male", "desc": "温暖元气男"},
    {"id": "longzhe_v3", "name": "龙哲", "gender": "male", "desc": "呆板大暖男"},
    {"id": "longyan_v3", "name": "龙颜", "gender": "female", "desc": "温暖春风女"},
    {"id": "longxing_v3", "name": "龙星", "gender": "female", "desc": "温婉邻家女"},
    {"id": "longtian_v3", "name": "龙天", "gender": "male", "desc": "磁性理智男"},
    {"id": "longwan_v3", "name": "龙婉", "gender": "female", "desc": "细腻柔声女"},
    {"id": "longqiang_v3", "name": "龙嫱", "gender": "female", "desc": "浪漫风情女"},
    {"id": "longfeifei_v3", "name": "龙菲菲", "gender": "female", "desc": "甜美娇气女"},
    {"id": "longhao_v3", "name": "龙浩", "gender": "male", "desc": "多情忧郁男"},
    {"id": "longanrou_v3", "name": "龙安柔", "gender": "female", "desc": "温柔闺蜜女"},
    {"id": "longhan_v3", "name": "龙寒", "gender": "male", "desc": "温暖痴情男"},
    {"id": "longanzhi_v3", "name": "龙安智", "gender": "male", "desc": "睿智轻熟男"},
    {"id": "longanling_v3", "name": "龙安灵", "gender": "female", "desc": "思维灵动女"},
    {"id": "longanya_v3", "name": "龙安雅", "gender": "female", "desc": "高雅气质女"},
    {"id": "longanqin_v3", "name": "龙安亲", "gender": "female", "desc": "亲和活泼女"},
    # 有声书
    {"id": "longmiao_v3", "name": "龙妙", "gender": "female", "desc": "抑扬顿挫女"},
    {"id": "longsanshu_v3", "name": "龙三叔", "gender": "male", "desc": "沉稳质感男"},
    {"id": "longyuan_v3", "name": "龙媛", "gender": "female", "desc": "温暖治愈女"},
    {"id": "longyue_v3", "name": "龙悦", "gender": "female", "desc": "温暖磁性女"},
    {"id": "longxiu_v3", "name": "龙修", "gender": "male", "desc": "博才说书男"},
    {"id": "longnan_v3", "name": "龙楠", "gender": "male", "desc": "睿智青年男"},
    {"id": "longwanjun_v3", "name": "龙婉君", "gender": "female", "desc": "细腻柔声女"},
    {"id": "longyichen_v3", "name": "龙逸尘", "gender": "male", "desc": "洒脱活力男"},
    {"id": "longlaobo_v3", "name": "龙老伯", "gender": "male", "desc": "沧桑岁月爷"},
    {"id": "longlaoyi_v3", "name": "龙老姨", "gender": "female", "desc": "烟火从容阿姨"},
    # 短视频配音
    {"id": "longjiqi_v3", "name": "龙机器", "gender": "male", "desc": "呆萌机器人"},
    {"id": "longhouge_v3", "name": "龙猴哥", "gender": "male", "desc": "经典猴哥"},
    {"id": "longdaiyu_v3", "name": "龙黛玉", "gender": "female", "desc": "娇率才女音"},
    # 直播带货
    {"id": "longanran_v3", "name": "龙安燃", "gender": "female", "desc": "活泼质感女"},
    {"id": "longanxuan_v3", "name": "龙安宣", "gender": "female", "desc": "经典直播女"},
    # 新闻播报
    {"id": "longshuo_v3", "name": "龙硕", "gender": "male", "desc": "博才干练男"},
    {"id": "longshu_v3", "name": "龙书", "gender": "male", "desc": "沉稳青年男"},
    {"id": "loongbella_v3", "name": "Bella3.0", "gender": "female", "desc": "精准干练女"},
]

# ==================== Sambert 系列音色（每个音色即独立模型，id 为完整模型名）====================
# 模型值为 "sambert"，实际调用时根据用户选择的音色 ID（如 sambert-betty-v1）作为真实模型名传递
_SAMBERT_VOICES = [
    # 英文音色
    {"id": "sambert-betty-v1", "name": "Betty", "gender": "female", "desc": ""},
    {"id": "sambert-brian-v1", "name": "Brian", "gender": "male", "desc": ""},
    {"id": "sambert-cally-v1", "name": "Cally", "gender": "female", "desc": ""},
    {"id": "sambert-camila-v1", "name": "Camila", "gender": "female", "desc": ""},
    {"id": "sambert-cindy-v1", "name": "Cindy", "gender": "female", "desc": ""},
    {"id": "sambert-clara-v1", "name": "Clara", "gender": "female", "desc": ""},
    {"id": "sambert-donna-v1", "name": "Donna", "gender": "female", "desc": ""},
    {"id": "sambert-eva-v1", "name": "Eva", "gender": "female", "desc": ""},
    {"id": "sambert-hanna-v1", "name": "Hanna", "gender": "female", "desc": ""},
    {"id": "sambert-indah-v1", "name": "Indah", "gender": "female", "desc": ""},
    {"id": "sambert-perla-v1", "name": "Perla", "gender": "female", "desc": ""},
    {"id": "sambert-waan-v1", "name": "Waan", "gender": "female", "desc": ""},
    # 中文音色
    {"id": "sambert-zhichu-v1", "name": "知厨", "gender": "male", "desc": ""},
    {"id": "sambert-zhida-v1", "name": "知达", "gender": "male", "desc": ""},
    {"id": "sambert-zhide-v1", "name": "知德", "gender": "male", "desc": ""},
    {"id": "sambert-zhifei-v1", "name": "知飞", "gender": "male", "desc": ""},
    {"id": "sambert-zhigui-v1", "name": "知柜", "gender": "female", "desc": ""},
    {"id": "sambert-zhihao-v1", "name": "知浩", "gender": "male", "desc": ""},
    {"id": "sambert-zhijia-v1", "name": "知佳", "gender": "female", "desc": ""},
    {"id": "sambert-zhijing-v1", "name": "知婧", "gender": "female", "desc": ""},
    {"id": "sambert-zhilun-v1", "name": "知伦", "gender": "male", "desc": ""},
    {"id": "sambert-zhimao-v1", "name": "知猫", "gender": "female", "desc": ""},
    {"id": "sambert-zhimiao-emo-v1", "name": "知妙（多情感）", "gender": "female", "desc": ""},
    {"id": "sambert-zhiming-v1", "name": "知茗", "gender": "female", "desc": ""},
    {"id": "sambert-zhimo-v1", "name": "知墨", "gender": "male", "desc": ""},
    {"id": "sambert-zhina-v1", "name": "知娜", "gender": "female", "desc": ""},
    {"id": "sambert-zhinan-v1", "name": "知楠", "gender": "male", "desc": ""},
    {"id": "sambert-zhiqi-v1", "name": "知琪", "gender": "female", "desc": ""},
    {"id": "sambert-zhiqian-v1", "name": "知倩", "gender": "female", "desc": ""},
    {"id": "sambert-zhiru-v1", "name": "知茹", "gender": "female", "desc": ""},
    {"id": "sambert-zhishu-v1", "name": "知树", "gender": "male", "desc": ""},
    {"id": "sambert-zhishuo-v1", "name": "知硕", "gender": "male", "desc": ""},
    {"id": "sambert-zhistella-v1", "name": "知莎", "gender": "female", "desc": ""},
    {"id": "sambert-zhiting-v1", "name": "知婷", "gender": "female", "desc": ""},
    {"id": "sambert-zhiwei-v1", "name": "知薇", "gender": "female", "desc": ""},
    {"id": "sambert-zhixiang-v1", "name": "知祥", "gender": "male", "desc": ""},
    {"id": "sambert-zhixiao-v1", "name": "知笑", "gender": "female", "desc": ""},
    {"id": "sambert-zhiya-v1", "name": "知雅", "gender": "female", "desc": ""},
    {"id": "sambert-zhiye-v1", "name": "知晔", "gender": "male", "desc": ""},
    {"id": "sambert-zhiying-v1", "name": "知颖", "gender": "female", "desc": ""},
    {"id": "sambert-zhiyuan-v1", "name": "知媛", "gender": "female", "desc": ""},
    {"id": "sambert-zhiyue-v1", "name": "知悦", "gender": "female", "desc": ""},
]

# ==================== 通义 TTS 音色映射（模型名 → 音色列表）====================
TONGYI_TTS_VOICES = {
    "cosyvoice-v1": _COSYVOICE_V1_VOICES,
    "cosyvoice-v2": _COSYVOICE_V2_VOICES,
    "cosyvoice-v3-plus": _COSYVOICE_V3_PLUS_VOICES,
    "cosyvoice-v3-flash": _COSYVOICE_V3_FLASH_VOICES,
    "sambert": _SAMBERT_VOICES,
}


def get_tongyi_voices(model: str) -> list:
    """获取指定通义 TTS 模型的可用音色列表（序列化格式，含性别描述）。"""
    voices = TONGYI_TTS_VOICES.get(model, [])
    gender_cn = {"female": "女声", "male": "男声"}
    result = []
    for v in voices:
        parts = [v["name"], "(", gender_cn.get(v["gender"], "")]
        if v.get("desc"):
            parts.append(v["desc"])
        parts.append(")")
        result.append({"id": v["id"], "name": "".join(parts), "type": v["gender"]})
    return result


def resolve_tongyi_voice(model: str, speaker_id: str) -> str:
    """解析 speaker_id 到通义 TTS voice 参数值（无效时回退首个音色）。"""
    voices = TONGYI_TTS_VOICES.get(model, [])
    for v in voices:
        if v["id"] == speaker_id:
            return v["id"]
    if voices:
        return voices[0]["id"]
    raise ValueError(f"模型 {model} 未配置可用音色")
