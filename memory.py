import collections
import time
import sys
import config, utils
from utils import logger


class Memory:
    def __init__(self, _price_db, _trade_db, timestamp):
        self.price_db = _price_db
        self.trade_db = _trade_db
        self.buffer = collections.deque([], config.PRICE_BUFFER_SIZE)
        self.cache = collections.deque([], config.PRICE_CACHE_SIZE)
        self.first_order = collections.deque([], config.PRICE_CACHE_SIZE)
        self.mid = None
        self.ask = None
        self.bid = None
        self.balance_eth = None
        self.balance_jpy = None
        self.record_timestamp = None
        self.retrospect_price(config.DAY0_TIMESTAMP, timestamp)
        self.history_trade_avg = self.retrospect_trade(config.DAY0_TIMESTAMP, timestamp)

    def print_state(self):
        buffer_state = 'buffer: '+str(len(self.buffer))+'/'+str(config.PRICE_BUFFER_SIZE)
        cache_state = 'cache: '+str(len(self.cache))+'/'+str(config.PRICE_CACHE_SIZE)
        first_order_state = 'first_order: '+str(len(self.first_order))+'/'+str(config.PRICE_CACHE_SIZE)
        logger.debug(', '.join([buffer_state, cache_state, first_order_state]))

    def check_recent_transactions(self, recent_transactions):
        phrase = {'Buy': 'bought', 'Sell': 'sold'}
        for tran in recent_transactions:
            try:
                self.trade_db.Get(str(tran['timestamp']))
            except KeyError:
                success = tran['status']=='Transaction Complete'
                sign = 1 if tran['buy_sell'] == 'Buy' else -1
                self.memorize_trade(tran['price'], sign*int(tran['amount']*tran['price']), tran['timestamp'], success)
                if success:
                    logger.info(str(tran['amount'])+' ether were '+phrase[tran['buy_sell']]+' with price '+str(tran['price']))
                else:
                    logger.warn(tran['status']+' when '+str(tran['amount'])+' ether were going to be '+phrase[tran['buy_sell']]+' with price '+str(tran['price']))

    def update(self, ask_price, bid_price, balance_eth, balance_jpy, timestamp):
        self.balance_jpy, self.balance_eth = int(balance_jpy), float(balance_eth)
        self.ask, self.bid = int(ask_price), int(bid_price)
        self.mid = (self.ask + self.bid) / 2
        if self.cache:
            self.first_order.appendleft(self.mid - self.cache[0])
        self.cache.appendleft(self.mid)
        if self.record_timestamp is None or timestamp - self.record_timestamp > config.RECORD_INTERVAL:
            self.record_timestamp = timestamp
            self.price_db.Put(str(timestamp), str(self.ask) + '|' + str(self.bid))
            self.buffer.appendleft((str(timestamp), str(self.ask) + '|' + str(self.bid)))
        self.print_state()

    def retrospect_trade(self, time_from, time_to):
        history_trade = list(self.trade_db.RangeIter(key_from=str(time_from), key_to=str(time_to)))
        buy_avg, sell_avg, buy_amount, sell_amount = 0, 0, 0, 0
        for trade in history_trade:
            trade = trade[1].split('|')
            price, amount = int(trade[0]), int(trade[1])
            if amount == 'FAILED':
                continue
            elif amount >= 0:
                buy_avg += price * amount
                buy_amount += amount
            else:
                sell_avg += price * amount
                sell_amount += amount
        buy_avg /= buy_amount
        sell_avg /= sell_amount
        return (buy_avg, sell_avg)

    def memorize_trade(self, price, amount, timestamp, success=True):
        seperator = '|' if success else '|FAILED|'
        self.trade_db.Put(str(timestamp), str(int(price)) + seperator + str(int(amount)))
        self.history_trade_avg = self.retrospect_trade(config.DAY0_TIMESTAMP, int(time.time()))

    def retrospect_price(self, time_from, time_to): # time_from -> time_to = past -> now
        past_data = list(self.price_db.RangeIter(key_from=str(time_from), key_to=str(time_to)))
        if len(past_data) > config.PRICE_BUFFER_SIZE:
            past_data = past_data[len(past_data) - config.PRICE_BUFFER_SIZE:]
        for ele in past_data:
            if ele[1] != 'CLOSED|CLOSED':
                self.buffer.appendleft(ele)
                ele_mid = utils.kv2mid(ele)
                if self.cache:
                    self.first_order.appendleft(ele_mid - self.cache[0])
                self.cache.appendleft(ele_mid)
        # interval = 36000
        # while True:
        #     timestamp = time_to - interval
        #     interval *= 2
        #     past_data = list(self.price_db.RangeIter(key_from=str(timestamp), key_to=str(time_to)))
        #     logger.debug('try to prefill data (' + str(len(past_data)) + ') from timestamp ' + str(timestamp) + ' to ' + str(time_to))
        #     if len(past_data) >= config.PRICE_BUFFER_SIZE or timestamp < time_from:
        #         for ele in past_data[len(past_data) - config.PRICE_BUFFER_SIZE:]:
        #             if ele[1] != 'CLOSED|CLOSED':
        #                 self.buffer.appendleft(ele)
        #                 ele_mid = utils.kv2mid(ele)
        #                 if self.cache:
        #                     self.first_order.appendleft(ele_mid - self.cache[0])
        #                 self.cache.appendleft(ele_mid)
        #         break
        logger.debug('price buffer prefilled with past data ('+str(len(past_data))+')')
