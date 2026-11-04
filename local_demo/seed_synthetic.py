"""Explicit optional offline seed for a new local acceptance checkout."""
from server import LABELS
from synthetic_fixtures import build_fixture

if __name__ == '__main__':
    if LABELS.exists():
        raise SystemExit('目标标签目录已存在，拒绝覆盖。请使用新的本地验收工作副本。')
    build_fixture(LABELS)
    print('已创建 10 道合成验收题及 Mock 译文；真实 API 请求为 0。重启本地服务后可查看。')
