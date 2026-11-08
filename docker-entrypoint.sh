#!/bin/sh
# Started as root: own the data directory, then run SeekBell as PUID:PGID (default
# 10001). Started as another user (Compose `user:`): only check the directory.
set -eu

data="${SEEKBELL_DATA_DIR:-/data}"

fail() {
    echo "SeekBell: $1" >&2
    exit 1
}

if [ "$(id -u)" = 0 ]; then
    uid="${PUID:-10001}"
    gid="${PGID:-10001}"
    case "$uid$gid" in
        *[!0-9]* | "") fail "PUID/PGID 必须是数字（当前 PUID=$uid PGID=$gid）。" ;;
    esac
    [ "$uid" -ne 0 ] && [ "$gid" -ne 0 ] || fail "PUID/PGID 不能为 0，SeekBell 不以 root 运行。"
    mkdir -p "$data" 2>/dev/null || true
    # Only entries with another owner are changed, so a large directory starts quickly.
    find "$data" \( ! -user "$uid" -o ! -group "$gid" \) -exec chown -h "$uid:$gid" {} + \
        2>/dev/null || true
    chmod 700 "$data" 2>/dev/null || true
    run="setpriv --reuid=$uid --regid=$gid --clear-groups --"
    $run true 2>/dev/null \
        || fail "无法切换到 UID $uid：容器缺少 SETUID/SETGID 权限（例如设置了 cap_drop: ALL 却未 cap_add）。"
else
    uid="$(id -u)"
    run=""
fi

$run sh -c 'probe="$1/.write-check.$$" && : > "$probe" && rm -f "$probe"' _ "$data" 2>/dev/null \
    || fail "数据目录 $data 无法写入（UID $uid）。请检查宿主机挂载目录；网络存储（NFS/SMB）可能不允许修改所有者。"

exec $run "$@"
