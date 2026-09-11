from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Union
from enum import Enum
import numpy as np

from .bi import BiBase


class ZhongShuType(int, Enum):
    """笔的类型"""
    UNFINISHED = 1  # 未完成
    FINISHED = 2  # 完成


class ZhongShuForward(int, Enum):
    """笔的类型"""
    MIDDLE = 0  # 没方向
    UP = 1  # 向上中枢
    DOWN = 2  # 向下中暑


@dataclass
class ZhongShuBase:
    "“”中枢“”"
    type: ZhongShuType = field(default=ZhongShuType.UNFINISHED)
    forward: ZhongShuForward = field(default=ZhongShuForward.MIDDLE)
    start_bi_idx: int = field(init=True, default=0)  # 中枢起始位置的笔索引
    end_bi_idx: int = field(init=True, default=0)  # 中枢结束位置的笔索引
    bi_list: List[BiBase] = field(init=True, default_factory=list, repr=False)
    start_idx: int = field(init=False, default=0)  # 中枢起始位置的K 线索引
    end_idx: int = field(init=False, default=0)  # 中枢结束位置的K 线索引
    start_time: str = field(init=False, default='')  # 起始时间
    end_time: str = field(init=False, default='')  # 结束时间
    high_price: float = field(init=False, default=0.0)  # 中暑上沿
    low_price: float = field(init=False, default=0.0)  # 中枢下沿

    def __post_init__(self):
        self.start_idx = self.bi_list[self.start_bi_idx].start_idx
        self.end_idx = self.bi_list[self.end_bi_idx].end_idx
        self.start_time = self.bi_list[self.start_bi_idx].start_time
        self.end_time = self.bi_list[self.end_bi_idx].end_time

        if self.bi_list[self.start_bi_idx].is_up():
            self.forward = ZhongShuForward.DOWN
        else:
            self.forward = ZhongShuForward.UP

        self.high_price = min(self.bi_list[self.start_bi_idx].high_price, self.bi_list[self.end_bi_idx].high_price)
        self.low_price = max(self.bi_list[self.start_bi_idx].low_price, self.bi_list[self.end_bi_idx].low_price)

    @property
    def is_finished(self):
        return self.type == ZhongShuType.FINISHED

    def set_finished(self):
        self.type = ZhongShuType.FINISHED

    def is_up(self):
        """是否为向上中枢"""
        return self.forward == ZhongShuForward.UP

    def is_down(self):
        """是否为向下中枢"""
        return self.forward == ZhongShuForward.DOWN

    def valid_finished(self):
        if self.bi_list[self.start_bi_idx].is_up() != self.bi_list[self.end_bi_idx].is_up():
            return False
        return True

    def is_in_zhongshu(self, high_price, low_price):
        """判断笔是否进入中枢的范围"""
        if self.low_price <= high_price and self.high_price >= low_price:
            return True
        return False

    def extend(self, new_bi: BiBase):
        if self.end_bi_idx <= new_bi.idx:
            self.end_bi_idx = new_bi.idx
            self.end_idx = new_bi.end_idx
            self.end_time = new_bi.end_time

    def bi_length(self) -> int:
        return self.end_bi_idx - self.start_bi_idx


def generate_zhongshu_from_bi(bi_list: List[BiBase], bi_idx_start=None, bi_idx_end=None) -> List[ZhongShuBase]:
    log_switch = False
    if len(bi_list) == 0:
        return []

    zhongshu_list: List[ZhongShuBase] = []
    last_zhongshu: Optional[ZhongShuBase] = None

    for idx, bi in enumerate(bi_list):

        if idx < 4:
            continue



        if len(zhongshu_list) > 0:
            last_zhongshu = zhongshu_list[-1]

        # 中枢进入段
        tmp_zhongshu_entry_bi = bi_list[idx - 4]
        tmp_zhongshu_first_bi = bi_list[idx - 3]
        tmp_zhongshu_third_bi = bi_list[idx - 1]
        tmp_zhongshu_exit_bi = bi_list[idx]

        if bi_idx_start is not None:
            if (idx - 3) < bi_idx_start:
                continue

        if bi_idx_end is not None:
            if (idx - 1) > bi_idx_end:
                break


        if last_zhongshu is None or (
                last_zhongshu.is_finished and tmp_zhongshu_entry_bi.start_time >= last_zhongshu.end_time):
            zhongshu_high_price = min(tmp_zhongshu_first_bi.high_price, tmp_zhongshu_third_bi.high_price)
            zhongshu_low_price = max(tmp_zhongshu_first_bi.low_price, tmp_zhongshu_third_bi.low_price)
            if tmp_zhongshu_exit_bi.high_price >= zhongshu_low_price and tmp_zhongshu_exit_bi.low_price <= zhongshu_high_price:

                zhongshu = ZhongShuBase(start_bi_idx=tmp_zhongshu_first_bi.idx, end_bi_idx=tmp_zhongshu_third_bi.idx,
                                        bi_list=bi_list)

                if (
                        zhongshu.is_up() and tmp_zhongshu_entry_bi.is_up() and tmp_zhongshu_entry_bi.low_price < zhongshu.low_price) or (
                        zhongshu.is_down() and tmp_zhongshu_entry_bi.is_down() and tmp_zhongshu_entry_bi.high_price > zhongshu.high_price):
                    zhongshu_list.append(zhongshu)
                    if log_switch:
                        print(f"中枢建立:{tmp_zhongshu_first_bi.start_time=} ,{tmp_zhongshu_third_bi.start_time=}", )
                        print(zhongshu)
                continue

        # 前一个中枢未完成时
        if last_zhongshu is None:
            if log_switch:
                print("中枢为空", bi.start_time, bi.end_time)
            continue
        if last_zhongshu.is_finished:
            if log_switch:
                print("前一中枢完成，新中枢未出现：", bi.start_time, bi.end_time)
            continue
        if last_zhongshu.is_in_zhongshu(bi.high_price, bi.low_price):
            if log_switch:
                print("中枢内：", bi.start_time, bi.end_time)
            continue
        else:
            last_zhongshu.extend(bi_list[idx - 2])
            last_zhongshu.set_finished()
            if log_switch:
                print(last_zhongshu)
                print("中枢完成:", bi.start_time, bi.end_time)
                print(last_zhongshu)
            zhongshu_list[-1] = last_zhongshu
    if last_zhongshu is not None and not last_zhongshu.is_finished:
        last_bi = bi_list[-1]
        if bi_idx_end is not None:
            last_bi = bi_list[bi_idx_end]
        last_zhongshu.extend(last_bi)
        last_zhongshu.set_finished()
        if log_switch:
            print(f"强迫完成：{bi_idx_end=}",last_zhongshu)

        zhongshu_list[-1] = last_zhongshu
    if log_switch:
        print(f"{len(zhongshu_list)=}")
    return zhongshu_list


def generate_zhongshu_in_xianduan_from_bi(bi_list: List[BiBase], xianduan_s_e_list: List[Tuple[int, int]]) -> List[
    ZhongShuBase]:
    log_switch = False
    if len(xianduan_s_e_list) == 0:
        return []
    from itertools import chain
    l = list(chain(*(generate_zhongshu_from_bi(bi_list, i, j) for i, j in xianduan_s_e_list)))
    if log_switch:
        for i in l:
            print(i.start_time, i.end_time)
    return l


def remove_bi_zhongshu_duplicates(
    bi_zhongshu_list: List[ZhongShuBase],
    bi_zhongshu_in_xianduan_list: List[ZhongShuBase],
) -> List[ZhongShuBase]:
    """删除与线段内中枢完全同区间的笔中枢，避免两类中枢重复显示。"""
    xianduan_zhongshu_keys = {
        (zhongshu.start_time, zhongshu.end_time, zhongshu.high_price, zhongshu.low_price)
        for zhongshu in bi_zhongshu_in_xianduan_list
    }
    return [
        zhongshu for zhongshu in bi_zhongshu_list
        if (zhongshu.start_time, zhongshu.end_time, zhongshu.high_price, zhongshu.low_price)
        not in xianduan_zhongshu_keys
    ]
