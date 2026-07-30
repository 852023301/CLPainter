from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from typing import List, Optional, Union

import numpy as np

from .bi import BiBase
from .tezhengxulie import TeZhengXuLie


class XianDuanDirectionType(str, Enum):
    """线段的类型"""
    UP = 'up'  # 上升段：底→顶
    DOWN = 'down'  # 下降段：顶→底


@dataclass
class XianDuanBase:
    """线段数据结构基类

    所有字段均为 init=False + 默认值: 由子类的 __post_init__ 或外部构造逻辑
    (如 make_fake_last_xd) 事后填充
    """
    start_idx: int = field(init=False, default=0)  # 线段起始位置索引(特征序列所在 K 线索引)
    end_idx: int = field(init=False, default=0)  # 线段结束位置索引(特征序列所在 K 线索引)
    start_bi_idx: int = field(init=False, default=0)  # 线段起始位置的笔索引(特征序列所在笔索引)
    end_bi_idx: int = field(init=False, default=0)  # 线段结束位置的笔索引(特征序列所在笔索引)
    start_time: str = field(init=False, default='')  # 起始时间
    end_time: str = field(init=False, default='')  # 结束时间
    start_price: float = field(init=False, default=0.0)  # 起始价格(顶/底特征序列的极值)
    end_price: float = field(init=False, default=0.0)  # 结束价格(顶/底特征序列的极值)
    xianduan_type: Optional[XianDuanDirectionType] = field(init=False, default=None)  # 线段的方向

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


@dataclass
class FakeXianDuanLast(XianDuanBase):
    """最末尾的假线段"""

    # xianduan索引(由 generate_xian_duan 事后填充)
    idx: int = field(init=False, default=0)


@dataclass
class FakeXianDuanFirst(XianDuanBase):
    """最早的假线段"""

    # 右侧特征序列(由 make_fake_first_xd 事后填充)
    right_tzxl: Optional[TeZhengXuLie] = field(init=False, default=None)


@dataclass
class XianDuan(XianDuanBase):
    # 左右分型
    left_tzxl: TeZhengXuLie
    right_tzxl: TeZhengXuLie

    # 完整的笔列表引用（用于第二种特征序列判断等场景）
    bi_list: List[Union[BiBase]] = field(default_factory=list, repr=False)

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

        if self.start_time >= self.end_time:
            raise ValueError(f"线段起始时间不能大于结束时间:{self.start_time=}>={self.end_time=}")

    @classmethod
    def from_tzxl(cls, left_tzxl: TeZhengXuLie, right_tzxl: TeZhengXuLie,
                  bi_list: Optional[List[Union[BiBase]]] = None) -> "XianDuan":
        """从一左一右两个特征序列分型构造候选线段。"""
        if bi_list is None:
            bi_list = []
        return cls(left_tzxl=left_tzxl, right_tzxl=right_tzxl, bi_list=bi_list)

    @cached_property
    def is_finished(self) -> bool:
        """判断候选线段是否满足线段成立条件。"""
        if not self.has_enough_bi():
            return False
        if not self.is_fanbao():
            return False

        # 判断第二种特征序列时，要考虑第一笔和第二笔的包含关系
        if self.left_tzxl.is_second_category() and self.is_second_bi_contain_first_bi():
            return False
        return True

    def has_enough_bi(self) -> bool:
        """缠论线段至少由三笔构成。"""
        return self.bi_count >= 3

    # def is_broken(self) -> bool:
    #     """第三笔要超出第一笔"""
    #     if self.is_up():
    #         return (
    #             self.left_tzxl.low_price < self.right_tzxl.low_price
    #             and self.left_tzxl.high_price < self.right_tzxl.high_price
    #         )
    #
    #     return (
    #         self.left_tzxl.high_price > self.right_tzxl.high_price
    #         and self.left_tzxl.low_price > self.right_tzxl.low_price
    #     )

    def is_fanbao(self) -> bool:
        """若特征序列完成前已经反包原趋势，则前一个特征序列只是中继"""
        if self.is_up() and self.right_tzxl.right_bi.end_price < self.left_tzxl.low_price:
            return False
        elif self.is_down() and self.right_tzxl.right_bi.end_price > self.left_tzxl.high_price:
            return False
        return True

    def is_second_bi_contain_first_bi(self) -> bool:
        """判断在第二种特征序列中，第二条线段的结束特征序列中，第二笔是否包含第一笔（以此来判断第二段是否无效）"""
        # 使用完整的 bi_list，如果未提供则回退到 right_tzxl.bi_list
        target_bi_list = self.bi_list

        start_bi_idx = self.left_tzxl.mid_bi_idx + 1
        end_bi_idx = self.right_tzxl.mid_bi_idx
        merged_deque = deque([])
        bi = target_bi_list[start_bi_idx]
        merged_low = bi.end_price
        merged_high = bi.start_price

        # 第二段线段向上的情况
        if self.xianduan_type == XianDuanDirectionType.UP:
            forward_up = True
            # 笔向下
            assert bi.is_down(), "判断第二种特征序列是否成立时发生笔方向错误的情况"

            for idx in range(start_bi_idx + 2, end_bi_idx + 1, 2):
                bi = target_bi_list[idx]
                if (bi.start_price > merged_high and bi.end_price > merged_low):
                    merged_deque.append((merged_low, merged_high))
                    merged_high = bi.start_price
                    merged_low = bi.end_price
                    forward_up = True
                    continue
                elif (bi.start_price < merged_high and bi.end_price < merged_low):
                    merged_deque.append((merged_low, merged_high))
                    merged_high = bi.start_price
                    merged_low = bi.end_price
                    forward_up = False
                    continue
                elif (bi.end_price >= merged_low and bi.start_price <= merged_high) or (
                    bi.end_price <= merged_low and bi.start_price >= merged_high):
                    # 合并
                    if forward_up:
                        func = max
                    else:
                        func = min
                    merged_high = func(merged_high, bi.start_price)
                    merged_low = func(merged_low, bi.end_price)
                else:
                    raise ValueError(f"判断第二种特征序列是否成立时发现意外的笔")

            # 寻找是否存在不被合并的笔，能够完成第二种特征序列
            for ml, mh in merged_deque:
                if ml < merged_low and mh < merged_high:
                    return False

        # 第二段线段向下的情况
        else:
            forward_up = False
            # 笔向上
            assert bi.is_up(), "判断第二种特征序列是否成立时发生笔方向错误的情况"

            for idx in range(start_bi_idx + 2, end_bi_idx + 1, 2):
                bi = target_bi_list[idx]
                if (bi.start_price > merged_low and bi.end_price > merged_high):
                    merged_deque.append((merged_low, merged_high))
                    merged_low = bi.start_price
                    merged_high = bi.end_price
                    forward_up = True
                    continue
                elif (bi.start_price < merged_low and bi.end_price < merged_high):
                    merged_deque.append((merged_low, merged_high))
                    merged_low = bi.start_price
                    merged_high = bi.end_price
                    forward_up = False
                    continue
                elif (bi.start_price >= merged_low and bi.end_price <= merged_high) or (
                    bi.start_price <= merged_low and bi.end_price >= merged_high):
                    # 合并
                    if forward_up:
                        func = max
                    else:
                        func = min
                    merged_high = func(merged_high, bi.end_price)
                    merged_low = func(merged_low, bi.start_price)
                else:
                    raise ValueError(f"判断第二种特征序列是否成立时发现意外的笔")

            # 寻找是否存在不被合并的笔，能够完成第二种特征序列
            for ml, mh in merged_deque:
                if ml > merged_low and mh > merged_high:
                    return False

        return True


def generate_xian_duan(tzxl_list: List[TeZhengXuLie], bi_list: List[Union[BiBase]]) -> List[XianDuanBase]:
    """
    根据特征序列分型划分线段。

    实现思路和 generate_bi 保持一致：相邻异类特征序列先形成候选线段，
    在确认前允许同向端点继续延长；满足三笔以上、不出现翻包、第二种
    特征序列缺口被后续确认后，才把候选线段加入结果。
    """

    # 初始化
    log_switch = False
    trade_s = "2012-12-04"
    trade_e = "2016-03-01"

    xianduan_list = []

    ########################### 辅助函数
    def _adjust_xian_duan(xd_lm, xd_mr):
        """
        在lm和mr都完成的前提下，追寻lm延伸到更极值的价格
        """
        nonlocal tzxl_list
        if xd_lm is None or xd_mr is None:
            return xd_lm, xd_mr
        origin_type = xd_mr.left_tzxl.type
        origin_tzxl = xd_mr.left_tzxl
        old_tzxl = xd_mr.left_tzxl
        start_idx = xd_mr.left_tzxl.idx
        end_idx = xd_mr.right_tzxl.idx

        for i in range(start_idx + 1, end_idx):
            new_tzxl = tzxl_list[i]
            if new_tzxl.type == origin_type and ((new_tzxl.is_top() and new_tzxl.high_price > old_tzxl.high_price)
                                                 or (new_tzxl.is_bottom() and new_tzxl.low_price < old_tzxl.low_price)):
                new_xd_lm = XianDuan.from_tzxl(xd_lm.left_tzxl, new_tzxl, bi_list)
                new_xd_mr = XianDuan.from_tzxl(new_tzxl, xd_mr.right_tzxl, bi_list)
                if new_xd_lm.is_finished and new_xd_mr.is_finished:
                    xd_lm = new_xd_lm
                    xd_mr = new_xd_mr
                    old_tzxl = new_tzxl

        if log_switch and xd_mr.left_tzxl is not origin_tzxl and trade_e >= xd_lm.start_time >= trade_s:
            print("#" * 50, "微调后")
            print(f"xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
            print(f"xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")
        return xd_lm, xd_mr

    def _advance_both():
        """推进 lm 和 mr：lm=mr，从 tzxl_deque 取下一对创建新 mr"""
        nonlocal xd_lm, xd_mr, tzxl_deque
        xd_lm = xd_mr
        if len(tzxl_deque) > 0:
            x_tzxl, y_tzxl = tzxl_deque.popleft()
            xd_mr = XianDuan.from_tzxl(x_tzxl, y_tzxl, bi_list)
        else:
            xd_mr = None

    def find_first_xd_in_finish_deque():
        """适合在lm未完成但mr已完成的情况下，在已完成的队列中寻找线段"""
        nonlocal xd_lm, xd_mr
        while len(xianduan_finish_deque) > 0:
            last_xd_finish = xianduan_finish_deque.pop()
            if last_xd_finish.xianduan_type == xd_lm.xianduan_type:
                xd_lm = last_xd_finish
                if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                    print("#" * 50, "finished lm弹出")
                    print(f"xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
                xd_mr = XianDuan.from_tzxl(xd_lm.right_tzxl, xd_mr.right_tzxl, bi_list)
                if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                    print(f"xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")
                if xd_lm.is_finished and xd_mr.is_finished:
                    return True
                continue

        if log_switch:
            print("#" * 50, "find_first_xd_in_finish_deque没找到，退出")

        return False

    ###########################

    if len(tzxl_list) < 2:
        return xianduan_list
    if log_switch:
        print([i.start_time for i in tzxl_list])

    tzxl_deque = deque((tzxl_list[i], tzxl_list[i + 1]) for i in range(len(tzxl_list) - 1))
    xianduan_finish_deque = deque([])

    if len(tzxl_deque) == 1:
        l_tzxl, r_tzxl = tzxl_deque.popleft()
        xd = XianDuan.from_tzxl(l_tzxl, r_tzxl, bi_list)
        if xd.is_finished:
            xianduan_list.append(xd)
        return xianduan_list

    # 在此 tzxl_deque至少有两个元素
    l_tzxl, m_tzxl = tzxl_deque.popleft()
    m_tzxl, r_tzxl = tzxl_deque.popleft()
    xd_lm = XianDuan.from_tzxl(l_tzxl, m_tzxl, bi_list)
    xd_mr = XianDuan.from_tzxl(m_tzxl, r_tzxl, bi_list)

    while len(tzxl_deque) > 0:
        if xd_lm is None or xd_mr is None:
            break
        is_xd_lm_finished = xd_lm.is_finished
        is_xd_mr_finished = xd_mr.is_finished

        if is_xd_lm_finished and is_xd_mr_finished:
            if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                print("#" * 50, "加入前")
                print(f"xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
                print(f"xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")

            xd_lm, xd_mr = _adjust_xian_duan(xd_lm, xd_mr)

            xianduan_finish_deque.append(xd_lm)
            _advance_both()
            if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                print("#" * 50, "加入后变更")
                print(f"new xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
                print(f"new xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")
            continue

        # if log_switch and trade_e >= xd_lm.start_time >= trade_s:
        #     print(f"lm和mr任一未完成: {is_xd_lm_finished=}  {is_xd_mr_finished=}")
        #     print(f"xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
        #     print(f"xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")

        elif not is_xd_lm_finished and is_xd_mr_finished:
            if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                print("lm未完成,所以往前寻找，寻找结果如下")
            if not find_first_xd_in_finish_deque():
                _advance_both()
                if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                    print(f"new xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
                    print(f"new xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")

            continue

        # 无论lm是否完成，只要mr未完成
        elif not is_xd_mr_finished:
            x_tzxl, y_tzxl = tzxl_deque.popleft()
            xd_xy = XianDuan.from_tzxl(x_tzxl, y_tzxl, bi_list)
            if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                print("%" * 50, f"{is_xd_lm_finished=}  mr未完成  ")
                print(f"xd_xy:{xd_xy.start_time}~{xd_xy.end_time}")
            if (xd_xy.xianduan_type == xd_lm.xianduan_type) and (
                (xd_xy.xianduan_type == XianDuanDirectionType.UP and xd_xy.end_price >= xd_lm.end_price) or (
                xd_xy.xianduan_type == XianDuanDirectionType.DOWN and xd_xy.end_price <= xd_lm.end_price)):
                xd_lm = XianDuan.from_tzxl(xd_lm.left_tzxl, xd_xy.right_tzxl, bi_list)
                if len(tzxl_deque) > 0:
                    x_tzxl, y_tzxl = tzxl_deque.popleft()
                    xd_mr = XianDuan.from_tzxl(x_tzxl, y_tzxl, bi_list)
                    if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                        print("@" * 50, "mr未完成,xy与lm同趋势")
                        print(f"xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
                        print(f"new xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")
                else:
                    xd_mr = None
                    if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                        print("@" * 50, "和lm同趋势，tzxl_deque为空，退出")
                    break

            if (xd_xy.xianduan_type == xd_mr.xianduan_type):
                new_xd_mr = XianDuan.from_tzxl(xd_mr.left_tzxl, xd_xy.right_tzxl, bi_list)
                if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                    print("@" * 50, "mr未完成,xy与mr同趋势")
                    # print(f"{new_xd_mr.has_enough_bi()=}  {new_xd_mr.is_fanbao()=}")
                if ((xd_xy.xianduan_type == XianDuanDirectionType.UP and xd_xy.end_price >= xd_mr.end_price) or (
                    xd_xy.xianduan_type == XianDuanDirectionType.DOWN and xd_xy.end_price <= xd_mr.end_price)) or new_xd_mr.is_finished:
                    xd_mr = new_xd_mr
                    if log_switch and trade_e >= xd_lm.start_time >= trade_s:
                        print(f"new xd_mr:{xd_lm.start_time}~{xd_lm.end_time}")

            continue
        else:
            raise RuntimeError("不应该存在其他情况")

        # print(xd_lm)
        # print("##########")
        # print(xd_mr)

    if xd_lm.is_finished and xd_mr is not None and xd_mr.is_finished:
        if log_switch and trade_e >= xd_lm.start_time >= trade_s:
            print("#" * 50, "加入前")
            print(f"xd_lm:{xd_lm.start_time}~{xd_lm.end_time}")
            print(f"xd_mr:{xd_mr.start_time}~{xd_mr.end_time}")
        xd_lm, xd_mr = _adjust_xian_duan(xd_lm, xd_mr)
        xianduan_finish_deque.append(xd_lm)
        xianduan_finish_deque.append(xd_mr)
        xd_lm = None
        xd_mr = None
    elif xd_lm.is_finished and xd_mr is not None and not xd_mr.is_finished:
        xianduan_finish_deque.append(xd_lm)
        xd_lm = xd_mr

    def make_fake_last_xd():
        """
        制造fake last线段
        """
        nonlocal xianduan_finish_deque, bi_list
        if len(xianduan_finish_deque) == 0:
            return
        last_xd: XianDuan = xianduan_finish_deque.pop()
        xianduan_finish_deque.append(last_xd)

        if last_xd.is_up():
            fake_last_xd_direction_type = XianDuanDirectionType.DOWN
        else:
            fake_last_xd_direction_type = XianDuanDirectionType.UP

        first_bi_index = last_xd.end_bi_idx
        end_bi_index = last_xd.right_tzxl.right_bi_idx
        sl = slice(end_bi_index, len(bi_list))

        bi_high_prices = np.array([bi.high_price for bi in bi_list[sl]])
        bi_low_prices = np.array([bi.low_price for bi in bi_list[sl]])
        local_max_idx = int(np.argmax(bi_high_prices))
        local_min_idx = int(np.argmin(bi_low_prices))

        if fake_last_xd_direction_type == XianDuanDirectionType.UP and local_max_idx > 0 and bi_high_prices[
            local_max_idx] > \
            bi_list[end_bi_index].high_price:
            end_bi_index = end_bi_index + local_max_idx
        elif fake_last_xd_direction_type == XianDuanDirectionType.DOWN and local_min_idx > 0 and bi_low_prices[
            local_min_idx] < bi_list[end_bi_index].low_price:
            end_bi_index = end_bi_index + local_min_idx

        first_bi = bi_list[first_bi_index]
        end_bi = bi_list[end_bi_index]

        fake_last_xd = FakeXianDuanLast()
        fake_last_xd.start_bi_idx = first_bi_index
        fake_last_xd.end_bi_idx = end_bi_index
        fake_last_xd.start_idx = first_bi.start_idx
        fake_last_xd.end_idx = end_bi.end_idx
        fake_last_xd.start_time = first_bi.start_time
        fake_last_xd.end_time = end_bi.end_time
        fake_last_xd.start_price = first_bi.start_price
        fake_last_xd.end_price = end_bi.end_price

        fake_last_xd.xianduan_type = fake_last_xd_direction_type

        xianduan_finish_deque.append(fake_last_xd)

    def make_fake_first_xd():
        """
         制造fake first线段
        """
        nonlocal xianduan_finish_deque, bi_list
        if len(xianduan_finish_deque) == 0:
            return
        first_xd: XianDuan = xianduan_finish_deque.popleft()

        origin_first_bi_index = first_xd.left_tzxl.mid_bi_idx
        first_bi_index = origin_first_bi_index
        sl = slice(0, origin_first_bi_index + 1)

        bi_high_prices = np.array([bi.high_price for bi in bi_list[sl]])
        bi_low_prices = np.array([bi.low_price for bi in bi_list[sl]])
        local_max_idx = int(np.argmax(bi_high_prices))
        local_min_idx = int(np.argmin(bi_low_prices))

        if first_xd.is_down() and local_max_idx < origin_first_bi_index and \
            bi_high_prices[local_max_idx] >= bi_list[origin_first_bi_index].high_price:
            first_bi_index = local_max_idx
        elif first_xd.is_up() and local_min_idx < origin_first_bi_index and \
            bi_low_prices[local_min_idx] <= bi_list[origin_first_bi_index].low_price:
            first_bi_index = local_min_idx

        first_bi = bi_list[first_bi_index]
        if first_bi.is_up() != bi_list[origin_first_bi_index].is_up():
            first_bi_index += 1
            first_bi = bi_list[first_bi_index]

        # 如果没找到更早更极值的笔，则不变
        if first_bi_index == origin_first_bi_index:
            xianduan_finish_deque.appendleft(first_xd)
            return

        end_bi = bi_list[first_xd.end_bi_idx]

        fake_first_xd = FakeXianDuanFirst()
        fake_first_xd.start_bi_idx = first_bi_index
        fake_first_xd.end_bi_idx = first_xd.end_bi_idx
        fake_first_xd.start_idx = first_bi.start_idx
        fake_first_xd.end_idx = end_bi.start_idx
        fake_first_xd.start_time = first_bi.start_time
        fake_first_xd.end_time = end_bi.start_time
        fake_first_xd.start_price = first_bi.start_price
        fake_first_xd.end_price = end_bi.start_price
        fake_first_xd.xianduan_type = first_xd.xianduan_type
        fake_first_xd.right_tzxl = first_xd.right_tzxl

        xianduan_finish_deque.appendleft(fake_first_xd)

    make_fake_first_xd()
    make_fake_last_xd()

    xianduan_list = list(xianduan_finish_deque)

    ####################### 检查
    # 检查笔上下交替
    assert np.all(np.diff([xd.is_up() for xd in xianduan_list]) != 0), "不满足线段上下交替的要求"

    # 检查线段日期连续性
    for i in range(len(xianduan_list) - 1):
        r_trade_date = xianduan_list[i].end_time
        l_trade_date = xianduan_list[i + 1].start_time

        if r_trade_date != l_trade_date:
            print(r_trade_date, l_trade_date)
            raise RuntimeError("线段连续性检查失败")
    ####################### 检查

    print(f"共{len(xianduan_list)}段")
    # 分配序号
    for i in range(len(xianduan_list)):
        xianduan_list[i].idx = i

    # 微调线段
    for i in range(len(xianduan_list) - 1):
        temp_xd_lm = xianduan_list[i]
        temp_xd_mr = xianduan_list[i + 1]

        if type(temp_xd_lm) == FakeXianDuanFirst:
            continue

        if type(temp_xd_lm) == FakeXianDuanLast or type(temp_xd_mr) == FakeXianDuanLast:
            break
        xianduan_list[i], xianduan_list[i + 1] = _adjust_xian_duan(temp_xd_lm, temp_xd_mr)
    return xianduan_list
