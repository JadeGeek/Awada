import os
import re
import json
import urllib3
import time
from typing import (
    Dict, Optional, List, Set, Tuple, Union
)
import xlrd

from wechaty import (
    Contact,
    FileBox,
    MessageType,
    WechatyPlugin,
    Room,
    Message,
    WechatyPluginOptions
)
from wechaty_puppet import get_logger
from utils.DFAFilter import DFAFilter


class DramaPlugin(WechatyPlugin):
    """
    AI soul 在 Pyhton-wechat的插件
    用于Awada长期运营
    Author：bigbrother666
    All rights reserved 2022
    """
    def __init__(
            self,
            options: Optional[WechatyPluginOptions] = None,
            configs: str = 'drama_configs',
            port: str = '5005'
    ) -> None:

        super().__init__(options)
        # 1. create the cache_dir
        self.config_files = configs
        self.cache_dir = f'{self.config_files}/{self.name}'
        self.file_cache_dir = f'{self.cache_dir}/file'
        os.makedirs(self.file_cache_dir, exist_ok=True)

        # 2. save the log info into <plugin_name>.log file
        log_file = os.path.join(self.cache_dir, 'log.log')
        self.logger = get_logger(self.name, log_file)

        # 3. check and load metadata
        if self._file_check() is False:
            raise RuntimeError('Drada plugin needs above config_files, pls add and try again')

        with open(os.path.join(self.config_files, 'directors.json'), 'r', encoding='utf-8') as f:
            self.directors = json.load(f)

        self.mmrules = self._load_mmrules()
        if self.mmrules is None:
            raise RuntimeError('Drada MMrules.xlsx not valid, pls refer to above info and try again')

        # 4. load self-memory data and create memory-dict for users
        self.self_memory, self.user_memory = self._load_memory()
        if self.self_memory is None or self.user_memory is None:
            raise RuntimeError('Drada memory.xlsx not valid, pls refer to above info and try again')

        # 5. test the rasa nlu server and compare the intents and entries with the meta/memory data
        self.rasa_url = 'http://localhost:'+port+'/model/parse'
        self.http = urllib3.PoolManager()

        _test_data = {'text': '苍老师德艺双馨'}
        _encoded_data = json.dumps(_test_data)
        _test_res = self.http.request('POST', self.rasa_url, body=_encoded_data)
        _result = json.loads(_test_res.data)

        if not _result:
            raise RuntimeError('Rasa server not running, pls start it first and trans the right port in str')

        for intent in _result["intent_ranking"]:
            if intent["name"] not in self.mmrules.keys():
                self.logger.warning('Intents in the MMrules.xlsx must be the same as the intents in the rasa server')
                raise RuntimeError('Intents in the MMrules.xlsx must be the same as the intents in the rasa server')

        self.gfw = DFAFilter()
        self.gfw.parse()
        self.logger.info('Drada plugin init success')

    def _file_check(self) -> bool:
        """check the config file"""

        if "directors.json" not in os.listdir(self.config_files):
            self.logger.warning(f'config file url:*{self.config_files}* does not have directors.json!')
            return False

        if "MMrules.xlsx" not in os.listdir(self.config_files):
            self.logger.warning(f'config file url:*{self.config_files}* does not have MMrules.xlsx!')
            return False

        if "memory.xlsx" not in os.listdir(self.config_files):
            self.logger.warning(f'config file url:*{self.config_files}* does not have memory.xlsx!')
            return False

        if "scenarios.xlsx" not in os.listdir(self.config_files):
            self.logger.warning(f'config file url:*{self.config_files}* does not have scenarios.xlsx!')
            return False

    def _load_memory(self) -> dict:
        """load the memory data and create memory-dict for users"""
        memory_file = os.path.join(self.config_files, 'memory.xlsx')
        data = xlrd.open_workbook(memory_file)
        table = data.sheets()[0]

        nrows = table.nrows
        if nrows == 0:
            self.logger.warning('no data in memory.xlsx,this is not allowed')
            return None, None

        self_memory = {}
        user_memory = {}

        for i in range(nrows):
            k, v = table.row_values(i)
            if k and v:
                self_memory[k] = v
                user_memory[k] = []
            else:
                self.logger.warning('No empty cell should be in the memory.xlsx, this is not allowed')
                return None, None

        return self_memory, user_memory

    def _load_mmrules(self) -> dict:
        """load the Memory Mathmatics Rules from excel"""
        mmrules = os.path.join(self.config_files, 'MMrules.xlsx')
        data = xlrd.open_workbook(mmrules)
        table = data.sheets()[0]

        nrows = table.nrows
        if nrows == 0:
            self.logger.warning('no memory in MMrules.xls,this is not allowed')
            return None

        cols = table.ncols

        if table.cell_value(0,1).lower() != 'read' or table.cell_value(0,2).lower() != 'bi':
            self.logger.warning('MMrules.xlsx is not in the right format:column 1 and 2 must be read and bi')
            return None

        rules = {}
        for i in range(1, nrows):
            for k in range(cols):
                if k == 0:
                    if table.cell_value(i,k):
                        intent = table.cell_value(i,k)
                        rules[intent] = {}
                    else:
                        self.logger.warning('MMrules.xlsx is not in the right format: intent is empty')
                        return None
                    continue
                if table.cell_value(i,k).lower() not in ['yes','no']:
                    self.logger.warning('MMrules.xlsx is not in the right format: value is not yes or no')
                    return None
                else:
                    rules[intent][table.cell_value(0,k).lower()] = table.cell_value(i,k).lower()

        return rules

    def _load_scenarios(self, scenario:str) -> dict:
        """load the scenarios data as assigned"""
        scenarios_file = os.path.join(self.config_files, 'scenarios.xlsx')
        data = xlrd.open_workbook(scenarios_file)
        table = data.sheet_by_name(scenario)

        nrows = table.nrows
        if nrows == 0:
            self.logger.warning('no data in scenario.xlsx,this is not allowed')
            return None

        cols = table.ncols

        for k in range(1, cols):
            if not table.cell_value(0,k):
                self.logger.warning('cell of the first row is empty in scenario.xlsx,this is not allowed')
                return None

        rules = {}
        for i in range(1, nrows):
            for k in range(cols):
                if k == 0:
                    if table.cell_value(i,k):
                        rule = table.cell_value(i,k)
                        rules[rule] = {}
                    else:
                        self.logger.warning('cell of the first column is empty in scenario.xlsx,this is not allowed')
                        return None
                    continue
                rules[rule][table.cell_value(0,k)] = table.cell_value(i,k)

        return rules


    async def director_message(self, msg: Message):
        """forward the message to the target conversations
        Args:
            msg (Message): the message to forward
        """
        # 1. get the type of message
        if msg.text() =="ding":
            await msg.say('dong -- Ddparser')
            return

    """
    def soul(self):

        yuan = Yuan(input_prefix="",
                    input_suffix="：“",
                    output_prefix="",
                    output_suffix="",)

        engine_name = yuan.get_engine()
        self.logger.info(engine_name)

        query = yuan.craft_query(text)
        self.logger.info(query)

        reply = yuan.submit_API(text, trun="”")

        if reply:
            await msg.say(reply)
            self.logger.info(reply)
        else:
            await msg.say('something must be wrong')
            self.logger.info('no reply, something goes wrong')
    """

    async def on_message(self, msg: Message) -> None:
        talker = msg.talker()
        room: Optional[Room] = msg.room()

        conv: Union[Room, Contact] = room or talker

        # 1. 判断是否是自己发送的消息
        if talker.contact_id == msg.is_self():
            return

        # 2. check if is director
        if not room and talker.contact_id in self.directors:
            await self.director_message(msg)
            return

        # 3. message pre-process
        """
        1. 是否是文本消息，排除不支持的消息类型（目前只支持文本，另外支持一个emoj，emoj统一识别为
        第一条判定为greating，后面都判定为meaningless）
        2. 预设声明发送（eg首次使用隐私声明）
        3. 敏感词检测
        4. 去掉特殊符号，比如@ /s等
        5. 随机等待0~0.5秒，避免线程和api申请频率过高
        """
        text = await msg.mention_text()
        if self.gfw.filter(text):
            self.logger.info(f'{text} is filtered, for the reason of {self.gfw.filter(text)}')
            return

        # 4. check the status of the talker and load the scenario rule-sheet


        # 5. intents and entity recognition

        # 6. ai sou1 response

        # 7. colorful eggs https://ai.baidu.com/ai-doc/wenxin/Zl33wtflg
