from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum
from collections import deque
import numpy as np
from .tezhengxulie import TeZhengXuLie


class XianDuanDirectionType(str, Enum):
    """线段的类型"""
    UP = 'up'  # 上升段：底→顶
    DOWN = 'down'  # 下降段：顶→底


@dataclass
class XianDuan:
    """线段数据结构"""
    start_idx: int = field(init=False)  # 线段起始位置索引（特征序列所在 K 线索引）
    end_idx: int = field(init=False)  # 线段结束位置索引（特征序列所在 K 线索引）
    start_bi_idx: int = field(init=False)  # 线段起始位置的笔索引（特征序列所在 笔索引）
    end_bi_idx: int = field(init=False)  # 线段结束位置的笔索引（特征序列所在 笔索引）
    start_time: str = field(init=False)  # 起始时间
    end_time: str = field(init=False)  # 结束时间
    start_price: float = field(init=False)  # 起始价格（顶/底特征序列的极值）
    end_price: float = field(init=False)  # 结束价格（顶/底特征序列的极值）
    xianduan_type: XianDuanDirectionType = field(init=False)  # 线段的方向

    # 左右分型
    left_tzxl: TeZhengXuLie
    right_tzxl: TeZhengXuLie

    def __post_init__(self):
        """根据左右两个特征序列分型初始化线段端点、方向和价格。"""
        if self.left_tzxl.type == self.right_tzxl.type:
            raise ValueError(f"特征序列分型方向一致: {self.left_tzxl.type=}")

        self.xianduan_type = (
            XianDuanDirectionType.UP if self.right_tzxl.is_top() else XianDuanDirectionType.DOWN
        )

        self.start_idx = self.left_tzxl.start_idx
        self.end_idx = self.right_tzxl.start_idx
        if self.end_idx <= self.start_idx:
            raise ValueError(f"线段结束索引不能小于起始索引:{self.end_idx=}<={self.start_idx=}")

        self.start_bi_idx = self.left_tzxl.mid_bi_idx
        self.end_bi_idx = self.right_tzxl.mid_bi_idx
        self.start_time = self.left_tzxl.start_time
        self.end_time = self.right_tzxl.start_time
        self.start_price = self.left_tzxl.start_price
        self.end_price = self.right_tzxl.start_price

    def is_up(self) -> bool:
        """判断当前线段是否为上升线段。"""
        return self.xianduan_type == XianDuanDirectionType.UP

    def is_down(self) -> bool:
        """判断当前线段是否为下降线段。"""
        return self.xianduan_type == XianDuanDirectionType.DOWN

    @property
    def bi_count(self) -> int:
        """返回线段覆盖的笔数量。"""
        return self.end_bi_idx - self.start_bi_idx + 1

    def to_dict(self) -> dict:
        """转换成前端画线更容易消费的字典结构。"""
        return {
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "start_bi_idx": self.start_bi_idx,
            "end_bi_idx": self.end_bi_idx,
            "direction": self.xianduan_type.value,
            "start_price": self.start_price,
            "end_price": self.end_price,
        }

    @classmethod
    def from_tzxl(cls, left_tzxl: TeZhengXuLie, right_tzxl: TeZhengXuLie) -> "XianDuan":
        """从一左一右两个特征序列分型构造候选线段。"""
        return cls(left_tzxl=left_tzxl, right_tzxl=right_tzxl)

    def is_finished(self) -> bool:
        """判断候选线段是否满足线段成立条件。"""
        if not self.has_enough_bi():
            return False

        if not self.is_broken():
            return False

        if not self.is_fanbao():
            return False

        # TODO 判断第二种特征序列时，要考虑第一笔和第二笔的包含关系
        if self.left_tzxl.is_second_category() and self.is_second_bi_contain_first_bi():
            return False

        return True

    def has_enough_bi(self) -> bool:
        """缠论线段至少由三笔构成。"""
        return self.bi_count >= 3

    def is_broken(self) -> bool:
        """第三笔要超出第一笔"""
        if self.is_up():
            return (
                self.left_tzxl.low_price < self.right_tzxl.low_price
                and self.left_tzxl.high_price < self.right_tzxl.high_price
            )

        return (
            self.left_tzxl.high_price > self.right_tzxl.high_price
            and self.left_tzxl.low_price > self.right_tzxl.low_price
        )

    def is_fanbao(self) -> bool:
        """若特征序列完成前已经反包原趋势，则前一个特征序列只是中继"""
        if self.is_up() and self.right_tzxl.right_bi.end_price < self.left_tzxl.low_price:
            return False
        elif self.is_down() and self.right_tzxl.right_bi.end_price > self.left_tzxl.high_price:
            return False
        return True

    def is_second_bi_contain_first_bi(self) -> bool:
        """判断第二笔是否包含第一笔"""
        return False


def generate_xian_duan(tzxl_list: List[TeZhengXuLie]) -> List[XianDuan]:
    """
    根据特征序列分型划分线段。

    实现思路和 generate_bi 保持一致：相邻异类特征序列先形成候选线段，
    在确认前允许同向端点继续延长；满足三笔以上、端点离开区间、第二种
    特征序列缺口被后续确认后，才把候选线段加入结果。
    """

    # 取连续极值
    tzxl_list_new = []
    is_top = True
    _temp = []
    for tzxl in tzxl_list:
        if tzxl.is_top() == is_top:
            _temp.append(tzxl)
        else:
            if _temp:
                if is_top == True:
                    tzxl_list_new.append(max(_temp, key=lambda x: x.high_price))
                else:
                    tzxl_list_new.append(min(_temp, key=lambda x: x.low_price))
            is_top = not is_top
            _temp.clear()
            _temp.append(tzxl)
    if _temp:
        if is_top == True:
            tzxl_list_new.append(max(_temp, key=lambda x: x.high_price))
        else:
            tzxl_list_new.append(min(_temp, key=lambda x: x.low_price))

    # 检查特征序列顶底交替
    assert np.all(np.diff([tzxl.is_top() for tzxl in tzxl_list_new]) != 0), "不满足特征序列顶底交替的要求"
    xianduan_list = []
    if len(tzxl_list_new) < 2:
        return xianduan_list

    tzxl_deque = deque((tzxl_list_new[i], tzxl_list_new[i + 1]) for i in range(len(tzxl_list_new) - 1))
    xianduan_finish_deque = deque([])

    if len(tzxl_deque) == 1:
        l_tzxl, r_tzxl = tzxl_deque.popleft()
        xd = XianDuan.from_tzxl(l_tzxl, r_tzxl)
        if xd.is_finished():
            xianduan_list.append(xd)
        return xianduan_list

    # 在此 tzxl_deque至少有两个元素
    while len(tzxl_deque) > 1:
        l_tzxl, r_tzxl = tzxl_deque.popleft()
        m_tzxl, r_tzxl = tzxl_deque.popleft()
        break



    xianduan_list = list(xianduan_finish_deque)[::-1]
    # 检查笔上下交替
    assert np.all(np.diff([xd.is_up() for xd in xianduan_list]) != 0), "不满足线段上下交替的要求"
    # TODO # 检查线段日期连续性

    return xianduan_list
