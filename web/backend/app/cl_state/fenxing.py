from typing import Any, Optional

from CLPainter.web.backend.app.toolbox.fenxing import FenXingType


def last_structure_right_type(cache: Any) -> Optional[int]:
    """返回当前 scope 最后一个构件右侧类型：NULL=无法判断，0=无分型，1=底分型，2=顶分型。"""
    bi_list = cache.bi_list
    if not bi_list:
        return None

    right_fx = getattr(bi_list[-1], "right_fx", None)
    if right_fx is None:
        return 0
    if right_fx.fenxing_type == FenXingType.BOTTOM:
        return 1
    if right_fx.fenxing_type == FenXingType.TOP:
        return 2
    return None
