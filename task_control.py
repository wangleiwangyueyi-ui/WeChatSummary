"""Cooperative cancellation shared by local readers and network jobs."""
class Cancelled(Exception):
    pass


def check_cancel(event):
    if event is not None and event.is_set():
        raise Cancelled('任务已取消；已保存的本地文件保留，已提交的远端请求无法撤回')
