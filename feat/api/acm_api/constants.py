# -*- coding: utf-8 -*-
"""ACM 助手 — 常量与帮助文本。"""
import logging

LOG = logging.getLogger("acm_api")

CHALLENGE_DONE_RECENT_LIMIT = 10
# 自动同步同时处理的用户数量，避免串行拖慢周期，也避免无限并发触发平台限流。
SYNC_USER_CONCURRENCY = 4
# 平台级并发限制：洛谷单独串行，其余平台利用全局用户并发提高吞吐。
PLATFORM_SYNC_CONCURRENCY = {
    "codeforces": 4,
    "luogu": 1,
    "nowcoder": 4,
    "atcoder": 4,
    "cjlu": 2,
}

# ACM 菜单同时用于文字帮助和图片菜单，避免图片菜单再维护一份容易过期的命令清单。
MENU_SECTIONS = (
    (
        "常用",
        (
            ("/acm help", "查看完整命令帮助"),
            ("/acm 改昵称 <新昵称>", "修改自己的成员昵称"),
            ("/acm bind <平台> <账号>", "绑定刷题平台账号"),
            ("/acm me", "查看自己的账号、统计和最近做题"),
            ("/acm recommend [平台]", "以图片随机推荐尚未完成的题目"),
            ("/acm inactive on|off [天数]", "开启或关闭不活跃提醒"),
        ),
    ),
    (
        "查询与排行榜",
        (
            ("/acm rank [all]", "近 7 日或生涯刷题排行榜"),
            ("/acm 总榜 [oj]", "生成生涯总过题排行榜图片"),
            ("/acm past <天数>", "生成指定天数过题排行榜图片"),
            ("/acm 过题 <身份> [天数]", "按身份查看排行榜"),
            ("/acm trend [天数]", "生成刷题趋势图片"),
            ("/acm streak", "查看连续刷题天数"),
            ("/acm difficulty", "查看难度分布"),
            ("/acm 查询 <QQ号>", "生成用户最近过题记录图片"),
            ("/acm <昵称|CF名|QQ号> cf", "生成 Codeforces 公开战绩卡"),
            ("/acm contests <CF Handle>", "生成 CF 参赛记录图片"),
            ("/acm rating <CF Handle>", "生成 Codeforces Rating 图片"),
            ("/acm contest", "生成近期 Codeforces 比赛图片"),
            ("/acm contest <HH:MM|off>", "管理员设置或关闭每日近期比赛播报"),
            ("/acm hourly [小时数]", "生成小时过题速报图片"),
        ),
    ),
    (
        "训练与挑战",
        (
            ("/acm random_challenge [平台] [标签]", "以图片展示按挑战 Rating 抽到的题目"),
            ("/acm challenge_done", "检查真实 AC 并完成随机挑战"),
            ("/acm challenge_giveup", "放弃当前随机挑战"),
            ("/训练 <平台> <难度> [标签]", "以图片生成巩固、同段、挑战三道题"),
            ("/完成训练 <巩固|同段|挑战>", "检查并完成训练任务"),
            ("/取消挑战 [巩固|同段|挑战]", "取消训练任务"),
            ("/acm recommend_add <平台> <题号> <链接>", "管理员维护推荐题库"),
        ),
    ),
    (
        "账号绑定",
        (
            ("/acm bind cf <Handle>", "绑定 Codeforces"),
            ("/acm bind luogu <UID>", "绑定洛谷"),
            ("/acm bind nowcoder <UID>", "绑定牛客"),
            ("/acm bind atcoder <Handle>", "绑定 AtCoder"),
            ("/acm bind cjlu <用户名>", "绑定 CJLU 校 OJ"),
            ("/acm bind confirm [平台]", "确认已填写验证码并完成绑定"),
            ("/acm unbind <平台>", "解绑并清理该平台旧记录"),
            ("/acm bind cf=<Handle> luogu=<UID>", "为多个平台创建绑定验证"),
        ),
    ),
    (
        "管理员",
        (
            ("/acm 后台启动 / 后台关闭", "启动或关闭 Web 管理后台"),
            ("/acm sync_user <QQ号> [天数]", "同步指定用户记录"),
            ("/acm 深度同步 <QQ号> <平台> [天数]", "同步指定平台记录"),
            ("/acm sync_status / sync_cancel <编号>", "查看或取消同步任务"),
            ("/acm sql <天数>", "全员深度同步并生成排行榜"),
            ("/acm report on|off", "开启或关闭定时播报"),
            ("/acm contest <HH:MM|off>", "设置或关闭每日近期比赛播报"),
            ("/acm set group|cron|hourly_limit", "设置播报群、时间和数量"),
            ("/acm 数据检查 [repair]", "检查或修复重复题目记录"),
            ("/acm del_user <QQ号>", "删除用户及其刷题记录"),
        ),
    ),
)

HELP_TEXT = (
    "📚 ACM 助手命令帮助\n\n"
    "【查询与排行榜】\n"
    "/acm help — 查看全部命令格式和功能\n"
    "/acm rank — 近7日刷题排行榜图片 Top 10\n"
    "/acm rank all — 生涯刷题排行榜图片 Top 10\n"
    "/acm 总榜 — 生涯总过题排行榜图片\n"
    "/acm 总榜 oj — 生涯总过题排行榜图片（含校OJ）\n"
    "/acm past <天数> — 近指定天数过题排行榜图片\n"
    "/acm 过题 <身份> [天数] — 按身份查看排行榜图片\n"
    "/acm 查询 <QQ号> — 生成用户最近20条过题记录图片\n"
    "/acm <昵称|CF名|QQ号> cf — 生成 Codeforces 公开战绩卡\n"
    "/acm me — 查看自己的账号、统计和最近做题\n"
    "/acm trend [天数] — 生成自己的刷题趋势图片\n"
    "/acm streak — 查看自己的连续刷题天数\n"
    "/acm contests <CF Handle> — 查询 CF 参赛记录\n"
    "/acm difficulty — 查看自己的难度分布\n"
    "/acm random_challenge [平台] [标签] — 按挑战 Rating 随机抽题并返回图片（支持 cf/洛谷/AtCoder/牛客）\n"
    "/acm challenge_done — 检查对应题目的真实 AC 后完成随机挑战\n"
    "/acm challenge_giveup — 放弃当前随机挑战\n\n"
    "【命令行训练】\n"
    "/训练 <平台> <难度> [标签1|标签2] — 生成巩固、同段、挑战三道题图片（支持 Codeforces/洛谷/AtCoder）\n"
    "/完成训练 <巩固|同段|挑战> — 检查并完成对应训练\n"
    "/取消挑战 [巩固|同段|挑战] — 取消指定区域，省略区域则取消全部训练\n"
    "随机挑战默认 Rating 为 1000，可在 WebUI 成员详情中调整；未找到本地记录时会快速查询平台最近 AC。\n"

    "/acm inactive on|off [天数] — 开关自己的不活跃提醒\n"
    "/acm recommend [平台] — 以图片随机推荐未完成题目\n"
    "/acm recommend_add <平台> <题号> <链接> [难度] [题名] — 管理员维护推荐题库\n\n"
    "/acm 改昵称 <新昵称> — 修改自己的成员昵称\n\n"
    "【账号绑定】普通用户可用，QQ号自动取发送者\n"
    "/acm bind cf <Handle> — 绑定 Codeforces\n"
    "/acm bind luogu <UID> — 绑定洛谷\n"
    "/acm bind nowcoder <UID> — 绑定牛客\n"
    "/acm bind atcoder <Handle> — 绑定 AtCoder\n"
    "/acm bind cjlu <用户名> — 绑定校OJ（中国计量大学）\n"
    "/acm bind cf=<Handle> luogu=<UID> ... — 为多个平台创建绑定验证\n"
    "/acm bind confirm [平台] — 确认已填写验证码并完成绑定\n"
    "/acm unbind <平台> — 解绑并清理该平台旧做题记录\n"
    "首次绑定前会验证账号是否存在，并要求把验证码写入账号公开资料；验证成功后才会写入绑定并重新同步该平台全部历史。\n"
    "同一个 QQ 每个平台只能绑定一个账号；重复输入当前账号会报错，换绑必须先解绑。同一平台账号不能绑定给多个 QQ。\n\n"
    "【外部信息】\n"
    "/acm rating <CF Handle> — 生成 Codeforces Rating 和最近比赛表现图片\n"
    "/acm contest — 生成近期 Codeforces 比赛图片\n"
    "/acm contest <HH:MM|off> — 管理员设置或关闭每日近期比赛播报（北京时间）\n"
    "/acm hourly [小时数] — 生成最近指定小时数的过题速报图片\n\n"
    "【管理员命令】\n"
    "/acm 后台启动 — 启动 Web 管理后台\n"
    "/acm 后台关闭 — 关闭 Web 管理后台\n"
    "/acm status — 查看插件和定时播报状态\n"
    "/acm sync_user <QQ号> [天数] — 同步指定用户历史/指定天数记录\n"
    "/acm sync_status — 查看同步任务列表和状态\n"
    "/acm sync_cancel <任务编号> — 取消正在运行的同步任务\n"
    "/acm 数据检查 [repair] — 检查或修复重复题目记录\n"
    "/acm 深度同步 <QQ号> <平台> [天数] — 仅同步指定用户的指定平台，天数填0表示全部历史\n"
    "/acm del_user <QQ号> — 删除用户及其全部刷题记录\n"
    "/acm sql <天数> — 全员深度同步并生成排行榜\n"
    "/acm report on|off — 开启或关闭定时播报\n"
    "/acm set group <群号> — 设置定时播报目标群\n"
    "/acm set cron <小时> <分钟> — 设置定时播报时间\n"
    "/acm set hourly_limit <数量> — 设置每次播报最多显示题数（1-50）\n\n"
    "Web 管理员也可在设置页设置近期比赛播报时间；播报发送到 /acm set group 配置的群。\n"
    "示例：/acm rank、/acm bind cf tourist、/acm 深度同步 123456789 atcoder 3650"
)
