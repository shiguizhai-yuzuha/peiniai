"""脉 · 进程内的共享状态。

只有两样东西：输入缓冲和它的锁。
放在单独文件里，是为了让 chat 和 persona 都能拿到同一份，
而不是各自持有一份互相看不见的副本。

不负责
  · 不存用户数据（那些在 db 里）
  · 不做持久化
"""
# 名字　脉 —— 一处搏动，全身都知道。共享的、不被扰动的那点东西。


import threading

# 输入缓冲：user_id -> 待发送的文本
_input_buffers = {}
_input_lock = threading.Lock()
