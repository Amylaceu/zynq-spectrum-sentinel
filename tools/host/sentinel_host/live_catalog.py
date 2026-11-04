"""Live presentation routes; historical inventory remains an audit record.

An absent scene is deliberately not an invitation to load an old measurement.
Only implemented operations may be dispatched by the product window.
"""
from dataclasses import replace

from .catalog import FEATURES as HISTORICAL_FEATURES

PAGES = ('系统与硬件', '频谱全景', '监测识别', '广播收听', '精度与验证',
         '空口与鲁棒性', '性能与优化', '现场采集', '自动演示', '功能总目录')

TITLES = {
    '7': '发射安全状态', '9': '现场全景扫描', '10': '扫描逐段进度',
    '28': '现场广播音频', '32': '现场生成序列逐位比对',
    '33': '本轮 IQ 采集与处理', '36': '现场十类空口识别与混淆矩阵',
    '37': '本轮样本注噪与识别', '39': '本轮十类与八大类统计',
    '49a': '本轮会话记录', '49b': '现场 IQ 采集与分析',
    '49c': '现场板载广播', '49d': '现场全景扫描',
    '49e': '现场空口逐类测试', '49f': '本轮 IQ 硬件处理',
    '49g': '本轮 PNG / CSV / IQ / HTML 导出',
    '51': 'B 组：环境 → 现场空口 → 注噪 → 性能',
    '52a': '全部现场功能索引',
}
# Build reports and past development are documentation, not live experiments.
DOCUMENT_ONLY = frozenset(('4', '6', '8', '11', '29', '30', '35', '40',
                           '46', '47', '48', '52b', '52c', '52d', '52e', '52f'))
LOCAL_ACTIONS = frozenset(('13', '18', '22', '49a', '49g', '52a'))
FEATURES = tuple(replace(item, title=TITLES.get(item.key, item.title), sources=(),
    action=(item.action if item.scene else {
        '13': '转到现场监测', '18': '识别所选信号', '22': '导出本轮 IQ',
        '49a': '记录本轮会话', '49g': '导出本轮数据', '52a': '打开功能索引',
    }.get(item.key, '工程文档项' if item.key in DOCUMENT_ONLY else '现场功能待接入')))
    for item in HISTORICAL_FEATURES)
BY_KEY = {item.key: item for item in FEATURES}


def executable(feature):
    return bool(feature.scene or feature.key in LOCAL_ACTIONS)
