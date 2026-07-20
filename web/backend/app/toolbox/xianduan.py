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

    # 初始化
    log_switch = True
    trade_s = "2021-01-01"
    trade_e = "2026-07-20"

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

    ########################### 辅助函数
    def _advance_both():
        """推进 lm 和 mr：lm=mr，从 tzxl_deque 取下一对创建新 mr"""
        nonlocal xd_lm, xd_mr, tzxl_deque
        xd_lm = xd_mr
        if len(tzxl_deque) > 0:
            x_tzxl, y_tzxl = tzxl_deque.popleft()
            xd_mr = XianDuan.from_tzxl(x_tzxl, y_tzxl)
        else:
            xd_mr = None

    def find_first_xd_in_finish_deque():
        """适合在lm未完成但mr已完成的情况下，在已完成的队列中寻找笔"""
        nonlocal xd_lm, xd_mr
        while len(xianduan_finish_deque) > 0:
            last_xd_finish = xianduan_finish_deque.pop()
            if log_switch and trade_e >= last_xd_finish.start_time >= trade_s:
                print("#" * 50, "lm弹出")
                print(f"last_xd_finish:{last_xd_finish.start_time}~{last_xd_finish.end_time}")
            if (last_xd_finish.xianduan_type == xd_lm.xianduan_type) and (
                (
                    last_xd_finish.xianduan_type == XianDuanDirectionType.UP and last_xd_finish.start_price <= xd_lm.start_price) or (
                    last_xd_finish.xianduan_type == XianDuanDirectionType.DOWN and last_xd_finish.start_price >= xd_lm.start_price)):
                xd_lm = XianDuan.from_tzxl(last_xd_finish.left_tzxl, xd_lm.right_tzxl)
                if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                    print("#" * 50, "lm被替换")
                    print(f"xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
                return True

            #  这行代码按理来说会触发，但从来没有遇到过触发的情况
            if (last_xd_finish.xianduan_type == xd_mr.xianduan_type) and (
                (
                    last_xd_finish.xianduan_type == XianDuanDirectionType.UP and last_xd_finish.start_price <= xd_mr.start_price) or (
                    last_xd_finish.xianduan_type == XianDuanDirectionType.DOWN and last_xd_finish.start_price >= xd_mr.start_price)):
                xd_mr = XianDuan.from_tzxl(last_xd_finish.left_tzxl, xd_mr.right_tzxl)
                if log_switch and trade_e >= last_xd_finish.start_time >= trade_s:
                    print("#" * 50, "mr被替换")
                    print(f"last_xd_finish:{last_xd_finish.start_time}~{last_xd_finish.end_time}")
                    print(f"xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
                    print(f"xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")
                # raise ValueError(f"xd_mr:{xd_mr.left_tzxl.mid_bi.start_time}~{xd_mr.right_tzxl.mid_bi.start_time}")
        return False

    ###########################

    if len(tzxl_list_new) < 2:
        return xianduan_list
    # print([i.start_time for i in tzxl_list_new])
    tzxl_deque = deque((tzxl_list_new[i], tzxl_list_new[i + 1]) for i in range(len(tzxl_list_new) - 1))
    xianduan_finish_deque = deque([])

    if len(tzxl_deque) == 1:
        l_tzxl, r_tzxl = tzxl_deque.popleft()
        xd = XianDuan.from_tzxl(l_tzxl, r_tzxl)
        if xd.is_finished():
            xianduan_list.append(xd)
        return xianduan_list

    # 在此 tzxl_deque至少有两个元素
    l_tzxl, m_tzxl = tzxl_deque.popleft()
    m_tzxl, r_tzxl = tzxl_deque.popleft()
    xd_lm = XianDuan.from_tzxl(l_tzxl, m_tzxl)
    xd_mr = XianDuan.from_tzxl(m_tzxl, r_tzxl)

    while len(tzxl_deque) > 0:
        if xd_lm is None or xd_mr is None:
            break
        is_xd_lm_finished = xd_lm.is_finished()
        is_xd_mr_finished = xd_mr.is_finished()

        if is_xd_lm_finished and is_xd_mr_finished:
            if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                print("#" * 50, "加入前")
                print(f"xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
                print(f"xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")
            xianduan_finish_deque.append(xd_lm)
            _advance_both()
            if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                print("#" * 50, "变更")
                print(f"new xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
                print(f"new xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")
            continue

        if log_switch and trade_e >= trade_e >= xd_lm.start_time >= trade_s:
            print("lm和mr任一未完成")
            print(f"xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
            print(f"xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")

        if not is_xd_lm_finished and is_xd_mr_finished:
            print("lm未完成,所以往前寻找，寻找结果如下")
            if not find_first_xd_in_finish_deque():
                _advance_both()
                if log_switch and trade_e >= trade_e >= xd_lm.start_time >= trade_s:
                    print(f"new xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
                    print(f"new xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")

            continue

        # 无论lm是否完成，只要mr未完成
        if not is_xd_mr_finished:
            x_tzxl, y_tzxl = tzxl_deque.popleft()
            xd_xy = XianDuan.from_tzxl(x_tzxl, y_tzxl)
            if (xd_xy.xianduan_type == xd_lm.xianduan_type) and (
                (xd_xy.xianduan_type == XianDuanDirectionType.UP and xd_xy.end_price >= xd_lm.end_price) or (
                xd_xy.xianduan_type == XianDuanDirectionType.DOWN and xd_xy.end_price <= xd_lm.end_price)):
                xd_lm = XianDuan.from_tzxl(xd_lm.left_tzxl, xd_xy.right_tzxl)
                if len(tzxl_deque) > 0:
                    x_tzxl, y_tzxl = tzxl_deque.popleft()
                    xd_mr = XianDuan.from_tzxl(x_tzxl, y_tzxl)
                    if log_switch and trade_e >= trade_e >= xd_lm.start_time >= trade_s:
                        print("@" * 50, "mr未完成,xy与lm同趋势")
                        print(f"xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
                        print(f"new xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")
                else:
                    xd_mr = None
                    if log_switch and trade_e >= trade_e >= xd_lm.start_time >= trade_s:
                        print("@" * 50, "和lm同趋势，tzxl_deque为空，退出")
                    break

            if (xd_xy.xianduan_type == xd_mr.xianduan_type) and (
                (
                    xd_xy.xianduan_type == XianDuanDirectionType.UP and xd_xy.end_price >= xd_mr.end_price) or (
                    xd_xy.xianduan_type == XianDuanDirectionType.DOWN and xd_xy.end_price <= xd_mr.end_price)):
                xd_mr = XianDuan.from_tzxl(xd_mr.left_tzxl, xd_xy.right_tzxl)
                if log_switch and trade_e >= trade_e >= xd_lm.start_time >= trade_s:
                    print("@" * 50, "mr未完成,xy与mr同趋势")
                    print(f"xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
                    print(f"new xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")

            continue

        # print(xd_lm)
        # print("##########")
        # print(xd_mr)

    if xd_lm.is_finished():
        xianduan_finish_deque.append(xd_lm)
        if xd_mr is not None and xd_mr.is_finished():
            xianduan_finish_deque.append(xd_mr)
            xd_lm = xd_mr
            xd_mr = None

    xianduan_list = list(xianduan_finish_deque)

    ####################### 检查
    # 检查笔上下交替
    assert np.all(np.diff([xd.is_up() for xd in xianduan_list]) != 0), "不满足线段上下交替的要求"

    # # 检查线段日期连续性
    # for i in range(len(xianduan_list) - 1):
    #     r_trade_date = xianduan_list[i].end_time
    #     l_trade_date = xianduan_list[i + 1].start_time
    #
    #     if r_trade_date != l_trade_date:
    #         print(r_trade_date, l_trade_date)
    #         raise RuntimeError("线段连续性检查失败")

    ####################### 检查
    print(f"共{len(xianduan_list)}段")
    return xianduan_list
