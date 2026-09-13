# Linux 常用命令

## 文本处理三剑客

### grep
```bash
grep -rn "pattern" path/          # 递归搜
grep -E "a|b"                    # 或
grep -v "exclude"                # 反选
grep -A 3 "match"                # 显示后 3 行
```

### sed
```bash
sed -i 's/old/new/g' file        # 原地替换
sed -n '10,20p' file             # 取 10-20 行
sed '/^#/d' file                 # 删除注释行
```

### awk
```bash
awk '{print $1}' file            # 打印第一列
awk -F: '{print $1}' /etc/passwd # 按 : 分割
awk '$3 > 100' file              # 条件过滤
awk 'NR>1' file                  # 跳过首行（CSV 表头）
```

## 进程与端口

```bash
ps aux | grep <name>
top / htop / btop
kill -9 <pid>
ss -tlnp                        # 监听端口
lsof -i :8080                   # 端口被谁占用
```

## 网络

```bash
curl -v https://example.com
wget -c <url>                   # 断点续传
tcpdump -i eth0 port 80
ssh -L 8080:remote:80 user@host # 端口转发
```

## 磁盘

```bash
df -h                           # 磁盘使用
du -sh path/                    # 目录大小
ls -lh                          # 文件大小
find / -name "*.log" -size +100M
```

## 系统监控

```bash
free -h                         # 内存
uptime                          # 负载
sar -u 1 10                     # CPU 历史
iostat -xz 1                    # IO
vmstat 1                        # 虚拟内存
```

## 进阶

- `strace -p <pid>`：跟踪系统调用
- `ltrace`：跟踪库调用
- `perf top`：CPU 热点
- `bpftrace`：内核级追踪
