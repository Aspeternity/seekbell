"""What each stable fault code means and how an administrator can confirm a fix."""

import re
from dataclasses import asdict, dataclass

AUTO = "auto_retry"
ACTION = "action"
RSS_TEST = "rss_test"
TARGET_TEST = "target_test"
RESTART = "restart"


@dataclass(frozen=True)
class Guide:
    stage: str
    summary: str
    causes: tuple[str, ...]
    steps: tuple[str, ...]
    handling: str
    verify: str | None
    known: bool = True


UNREACHABLE = ("论坛暂时无法访问或响应缓慢", "本机到论坛的网络、DNS 或代理有问题")
CHECK_NETWORK = (
    "在浏览器确认论坛能否打开",
    "用连接测试确认本机能否访问 RSS",
    "测试也失败的话，检查容器网络和代理设置",
)
BAD_FEED = ("来源临时返回了错误页面", "来源调整了 RSS 格式，可能需要更新 SeekBell")
CHECK_FEED = ("用连接测试查看当前结果", "持续失败时检查是否有新版本，或提交问题")
BLOCKED = ("来源启用了验证或访问限制", "本机出口 IP 被来源风控")
CHECK_BLOCK = ("确认本机出口 IP 是否被来源限制", "必要时更换出口后，用连接测试确认")


def _parse(summary: str) -> Guide:
    return Guide("parse", summary, BAD_FEED, CHECK_FEED, AUTO, RSS_TEST)


SOURCE_GUIDES = {
    # The connection never completed (no request reached the forum) versus a request that
    # went out and got no answer in time; older records only had "timeout".
    "connect_timeout": Guide(
        "fetch",
        "连接超时",
        ("本机到论坛的网络线路不稳定", "本机 DNS 或出口网络有问题"),
        CHECK_NETWORK,
        AUTO,
        RSS_TEST,
    ),
    "timeout": Guide("fetch", "请求超时", UNREACHABLE, CHECK_NETWORK, AUTO, RSS_TEST),
    "transport_error": Guide("fetch", "网络连接失败", UNREACHABLE, CHECK_NETWORK, AUTO, RSS_TEST),
    "response_too_large": Guide(
        "fetch",
        "响应超过大小上限",
        ("来源返回了异常内容", "代理或网关改写了响应"),
        CHECK_FEED,
        AUTO,
        RSS_TEST,
    ),
    "access_challenge": Guide("fetch", "来源要求人机验证", BLOCKED, CHECK_BLOCK, ACTION, RSS_TEST),
    "http_403": Guide("fetch", "来源拒绝访问（403）", BLOCKED, CHECK_BLOCK, ACTION, RSS_TEST),
    "http_429": Guide(
        "fetch",
        "请求受限（429）",
        ("请求过于频繁", "同一出口上还有其他实例在访问来源"),
        ("等待限制解除，SeekBell 会按来源要求延后重试", "确认没有重复部署多个实例"),
        AUTO,
        RSS_TEST,
    ),
    "unexpected_content_type": _parse("返回的不是 RSS 内容"),
    "unsupported_content_encoding": _parse("响应压缩方式不受支持"),
    "invalid_or_unsafe_xml": _parse("XML 无效或不安全"),
    "not_rss": _parse("返回内容不是 RSS"),
    "missing_rss_channel": _parse("RSS 缺少 channel"),
    "feed_parse_error": _parse("RSS 解析失败"),
    "entry_count_mismatch": _parse("RSS 条目数量异常"),
    "no_valid_entries": _parse("RSS 中没有有效帖子"),
    "unsupported_source": Guide(
        "config",
        "来源地址与内置网站不一致",
        ("数据来自旧版本或被手动修改",),
        ("检查是否有新版本", "持续出现时提交问题"),
        ACTION,
        None,
    ),
}

TARGET_CONFIG = ("令牌、地址或接收者配置有误", "消息内容不符合对方要求")
FIX_TARGET = ("打开目标配置检查并保存", "用目标测试确认，测试会真实发送一条消息")
SERVICE_DOWN = ("通知服务暂时不可用或正在限流", "本机到通知服务的网络有问题")
WAIT_RETRY = ("等待自动重试", "持续失败时用目标测试确认，测试会真实发送一条消息")
MAYBE_SENT = ("网络在发送途中中断", "通知服务响应异常")
CHECK_RECEIVED = ("先到接收端确认是否已收到", "自动重试可能产生重复消息")
SMTP_CONFIG = ("服务器、端口、账号或发件人配置有误", "邮件服务器策略拒绝了这封邮件")


def _unknown(summary: str) -> Guide:
    return Guide("send", summary + "，结果不确定", MAYBE_SENT, CHECK_RECEIVED, AUTO, TARGET_TEST)


DELIVERY_GUIDES = {
    "target_credentials_invalid": Guide(
        "config",
        "目标配置无法解密或已失效",
        ("密钥文件与数据库不匹配，例如恢复备份后", "目标配置已损坏"),
        ("打开目标配置，重新填写并保存", "用目标测试确认，测试会真实发送一条消息"),
        ACTION,
        TARGET_TEST,
    ),
    "unsupported_notifier": Guide(
        "config",
        "通知渠道不受支持",
        ("数据来自其他版本",),
        ("检查是否有新版本", "重新创建该通知目标"),
        ACTION,
        None,
    ),
    "http_connect": Guide(
        "send", "无法连接到通知服务", SERVICE_DOWN, WAIT_RETRY, AUTO, TARGET_TEST
    ),
    "http_result_unknown": _unknown("连接中断"),
    "invalid_response": _unknown("响应无法识别"),
    "unexpected_response_encoding": _unknown("响应编码异常"),
    "response_too_large": _unknown("响应过大"),
    "invalid_notifier_result": _unknown("渠道返回异常"),
    "send_timeout": _unknown("发送超时"),
    "send_exception": _unknown("发送异常"),
    "notifier_exception": _unknown("告警发送异常"),
    "lease_expired": _unknown("发送被中断"),
    "smtp_busy": Guide("send", "邮件发送繁忙", SERVICE_DOWN, WAIT_RETRY, AUTO, TARGET_TEST),
    "smtp_connect": Guide(
        "send", "无法连接到邮件服务器", SERVICE_DOWN, WAIT_RETRY, AUTO, TARGET_TEST
    ),
    "smtp_retry": Guide("send", "邮件服务器暂时拒绝", SERVICE_DOWN, WAIT_RETRY, AUTO, TARGET_TEST),
    "smtp_rejected": Guide("send", "邮件服务器拒绝", SMTP_CONFIG, FIX_TARGET, ACTION, TARGET_TEST),
    "smtp_security": Guide(
        "config",
        "邮件服务器安全校验失败",
        ("服务器证书无效", "服务器不支持所选的加密方式"),
        FIX_TARGET,
        ACTION,
        TARGET_TEST,
    ),
    "smtp_result_unknown": _unknown("邮件发送中断"),
}

DELIVERY_PREFIXES = ("http", "telegram", "bark", "webhook")
DELIVERY_OUTCOMES = {
    "rejected": Guide("send", "通知服务拒绝了请求", TARGET_CONFIG, FIX_TARGET, ACTION, TARGET_TEST),
    "retry": Guide("send", "通知服务暂时不可用", SERVICE_DOWN, WAIT_RETRY, AUTO, TARGET_TEST),
    "timeout": _unknown("通知服务请求超时"),
}

RESTART_STEPS = ("重启容器以恢复后台服务", "反复出现时，带上版本和崩溃位置提交问题")
RUNTIME_GUIDES = {
    name + "_stopped": Guide(
        "service",
        label + "已停止",
        ("程序内部错误，崩溃位置见下方", "数据库或磁盘不可用"),
        RESTART_STEPS,
        ACTION,
        RESTART,
    )
    for name, label in (
        ("collection", "采集服务"),
        ("delivery", "投递服务"),
        ("retention", "历史清理服务"),
        ("alerts", "系统告警服务"),
    )
}
RUNTIME_GUIDES["loop_stalled"] = Guide(
    "service",
    "后台循环长时间未完成",
    ("数据库被长时间占用", "后台任务卡住"),
    ("稍等片刻后刷新", "持续不变时重启容器"),
    ACTION,
    RESTART,
)
RUNTIME_GUIDES["disk_space_low"] = Guide(
    "storage",
    "磁盘可用空间不足 500 MiB",
    ("历史数据、备份或同一磁盘上的其他文件占满了空间",),
    (
        "在系统设置的“数据”页查看占用，到“备份”页删除不再需要的备份",
        "缩短历史保留天数，或清理、扩容所在磁盘",
        "可用空间回到 600 MiB 以上后自动恢复",
    ),
    ACTION,
    None,
)

RUNTIME_GUIDES["backup_failed"] = Guide(
    "storage",
    "自动备份失败",
    ("磁盘可用空间不足", "备份目录不可写", "数据库或凭据密钥校验失败"),
    (
        "到系统设置的“备份”页查看失败原因",
        "释放磁盘空间或删除旧备份后，点“立即备份”确认可以备份",
        "之后每小时自动重试，成功后自动恢复",
    ),
    ACTION,
    None,
)
RUNTIME_GUIDES["backup_overdue"] = Guide(
    "storage",
    "超过两个备份周期没有成功备份",
    ("容器长时间停机", "自动备份一直未能运行"),
    ("到系统设置的“备份”页点“立即备份”", "完成一次备份后自动恢复"),
    ACTION,
    None,
)

UNKNOWN = Guide(
    "unknown",
    "未收录的错误",
    ("这个错误码没有对应说明",),
    ("记下错误码和版本", "持续出现时提交问题"),
    ACTION,
    None,
    False,
)


def source_guide(code: str | None) -> Guide:
    if code in SOURCE_GUIDES:
        return SOURCE_GUIDES[code]
    status = re.fullmatch(r"http_([1-5][0-9]{2})", code or "")
    if status is None:
        return UNKNOWN
    number = status[1]
    if number[0] == "5":
        return Guide(
            "fetch",
            f"来源服务器错误（{number}）",
            ("论坛正在维护或暂时故障",),
            CHECK_NETWORK,
            AUTO,
            RSS_TEST,
        )
    return Guide(
        "fetch",
        f"来源返回错误（{number}）",
        ("来源调整了 RSS 地址或访问规则",),
        CHECK_FEED,
        ACTION,
        RSS_TEST,
    )


def delivery_guide(code: str | None) -> Guide:
    if code in DELIVERY_GUIDES:
        return DELIVERY_GUIDES[code]
    prefix, _, outcome = (code or "").rpartition("_")
    if prefix in DELIVERY_PREFIXES and outcome in DELIVERY_OUTCOMES:
        return DELIVERY_OUTCOMES[outcome]
    return UNKNOWN


def runtime_guide(code: str | None) -> Guide:
    return RUNTIME_GUIDES.get(code or "", UNKNOWN)


def guide_for(kind: str, code: str | None) -> Guide:
    return {"source": source_guide, "delivery": delivery_guide, "runtime": runtime_guide}[kind](
        code
    )


def guide_view(guide: Guide) -> dict:
    return asdict(guide)
