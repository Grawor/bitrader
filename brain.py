import config, utils
import time, math
import itertools
from utils import logger
from sklearn.linear_model import LinearRegression as LR
import numpy as np


class Brain:
    def __init__(self, _memory, _my_hand):
        self.memory = _memory
        self.hand = _my_hand
        self.thinking = True

    def get_trend(self, now_time):
        trend = []

        interval = config.INDICATER_INETRVAL_INIT
        time_point = now_time - interval
        price_sum = 0

        buffer_len = len(self.memory.buffer)
        for buffer_iter in range(0, buffer_len):
            item = self.memory.buffer[buffer_iter]
            timestamp = int(item[0])
            mid = utils.kv2mid(item)
            # print item, timestamp, mid, time_point
            if timestamp <= time_point:
                average = float(price_sum) / float(buffer_iter)
                trend.append((time_point, (self.memory.mid - average) / float(average)))
                # print now_time-time_point, average, '|', self.buffer.mid
                interval *= config.INTERVAL_GROW_FACTOR
                time_point -= interval
            price_sum += mid
        if len(trend) > config.TREND_LEN:
            trend = trend[:config.TREND_LEN]
        logger.debug('trend: ' + str([(int(now_time - a), b) for (a, b) in trend]))
        return trend

    def get_momentum(self):
        momentum = []
        for lr_range in config.MOMENTUM_LR_RANGE:
            lr_range = lr_range / config.WATCH_INTERVAL
            y = list(itertools.islice(self.memory.first_order, 0, lr_range))
            x = range(1, lr_range + 1)
            x = np.asarray(x).reshape(-1, 1)
            y = np.asarray(y).reshape(-1, 1)
            lr = LR()
            lr.fit(x, y)
            momentum.append(lr.predict(0)[0][0])
        logger.debug('momentums: ' + str(momentum))
        return momentum

    def decide_trade(self, trend, momentum):
        trend_avg = sum([float(b) for (a, b) in trend]) / float(len(trend))
        momentum_avg = float(sum(momentum)) / float(len(momentum))
        trade_amount = config.TRADE_AMOUNT_BASE * (-trend_avg)
        delta = min(abs(trade_amount), config.DAMP_COEF * momentum_avg * momentum_avg)
        trade_amount = trade_amount - delta if trade_amount >= 0 else trade_amount + delta
        history_buy_avg, history_sell_avg = self.memory.history_trade_avg
        if trade_amount > 0:
            trade_amount *= min(1, math.sqrt(float(self.memory.balance_jpy)/float(self.memory.balance_eth*self.memory.ask)))
            trade_amount *= float(history_sell_avg)/float(self.memory.ask)
            history_avg = 'history_sell_avg: '+str(int(history_sell_avg))
        else:
            trade_amount *= min(1, math.sqrt(float(self.memory.balance_eth*self.memory.bid)/float(self.memory.balance_jpy)))
            trade_amount *= float(self.memory.bid)/float(history_buy_avg)
            history_avg = 'history_buy_avg: '+str(int(history_buy_avg))
        logger.debug(history_avg+' trend_avg: '+str(trend_avg)+' momentum_avg: '+str(momentum_avg)+' proposed trading amount: '+str(int(trade_amount)))
        return int(trade_amount)

    def thinkable(self, timestamp):
        if not self.memory.buffer or not self.memory.cache or not self.memory.first_order:
            return False
        if int(self.memory.buffer[0][0]) < timestamp - config.INDICATER_INETRVAL_INIT + config.THINK_INTERVAL:
            return False
        return True

    def think(self, timestamp):
        if not self.thinkable(timestamp):
            if self.thinking:
                self.thinking = False
                logger.warn('data outdated, not thinking now')
            return
        if not self.thinking:
            logger.warn('start thinking again')
        self.thinking = True
        trend = self.get_trend(timestamp)
        momentum = self.get_momentum()

        if len(trend) >= config.TREND_LEN and len(momentum) >= len(config.MOMENTUM_LR_RANGE):
            #history_buy_avg, history_sell_avg = self.memory.history_trade_avg
            trade_amount = self.decide_trade(trend, momentum)
            if trade_amount > config.MIN_TRADE_AMOUNT and trade_amount < self.memory.balance_jpy:
                self.hand.buy(self.memory.ask, jpy=trade_amount)
            if trade_amount < -config.MIN_TRADE_AMOUNT and -trade_amount < self.memory.balance_eth*self.memory.bid:
                self.hand.sell(self.memory.bid, jpy=-trade_amount)

    def start_thinking(self):
        while True:
            time.sleep(config.THINK_INTERVAL)
            self.think(int(time.time()))
