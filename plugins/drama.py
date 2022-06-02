import os
import re
import json
import urllib3
import time

import wechaty
from paddlenlp import Taskflow
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
            port: str = '5005',
            multiuser: bool = True
    ) -> None:

        super().__init__(options)
        # 1. create the cache_dir
        self.config_url = configs
        self.config_files = os.listdir(self.config_url)
        if len(self.config_files) < 5:
            raise RuntimeError('Drada plugin config_files not enough, pls add and try again')

        self.cache_dir = f'./{self.name}'
        self.file_cache_dir = f'{self.cache_dir}/file'
        os.makedirs(self.file_cache_dir, exist_ok=True)

        # 2. save the log info into <plugin_name>.log file
        log_file = os.path.join(self.cache_dir, 'log.log')
        self.logger = get_logger(self.name, log_file)

        # 3. check and load metadata
        if self._file_check() is False:
            raise RuntimeError('Drada plugin needs above config_files, pls add and try again')

        with open(os.path.join(self.config_url, 'directors.json'), 'r', encoding='utf-8') as f:
            self.directors = json.load(f)
        if len(self.directors) == 0:
            self.logger.warning('there must be at least one director, pls retry')
            raise RuntimeError('Drama director.json not valid, pls refer to above info and try again')

        self.mmrules = self._load_mmrules()
        if self.mmrules is None:
            raise RuntimeError('Drada MMrules.xlsx not valid, pls refer to above info and try again')

        # 4. load self-memory data and create memory-dict for users
        with open(os.path.join(self.config_url, 'focus.json'), 'r', encoding='utf-8') as f:
            schema = json.load(f)
        if len(schema) == 0 or "" in schema:
            self.logger.warning('there must be at least one in the focus.json and no empty should be, pls retry')
            raise RuntimeError('Drama focus.json not valid, pls refer to above info and try again')

        try:
            self.uie = Taskflow('information_extraction', schema=schema, task_path='uie/checkpoint/model_best')
        except Exception as e:
            self.logger.error('load uie failed, pls check the uie/checkpoint/model_best, be sure right model files exits')
            raise e

        self.self_memory = self._load_memory()
        if self.self_memory is None:
            raise RuntimeError('Drada memory.xlsx not valid, pls refer to above info and try again')

        self.user_memory_template = {}
        for key in self.self_memory.keys():
            self.user_memory_template[key] = {}

        self.multiuser = multiuser

        if "user_memory.json" in self.config_files:
            with open(os.path.join(self.config_url, 'user_memory.json'), 'r', encoding='utf-8') as f:
                self.user_memory = json.load(f)
        else:
            self.user_memory = {} if multiuser else self.user_memory_template

        if "users.json" in self.config_files:
            with open(os.path.join(self.config_url, 'users.json'), 'r', encoding='utf-8') as f:
                self.users = json.load(f)
        else:
            self.users = {}

        # 5. load scenario rule-table
        self.scenarios = self._load_scenarios()
        if self.scenarios is None:
            raise RuntimeError('Drada scenarios.xlsx not valid, pls refer to above info and try again. make sure at lease one scenario is well defined.')

        # 6. initialize & test the rasa nlu server
        self.rasa_url = 'http://localhost:'+port+'/model/parse'
        self.http = urllib3.PoolManager()

        _test_data = {'text': '苍老师德艺双馨'}
        _encoded_data = json.dumps(_test_data)
        _test_res = self.http.request('POST', self.rasa_url, body=_encoded_data)
        _result = json.loads(_test_res.data)

        if not _result:
            raise RuntimeError('Rasa server not running, pls start it first and trans the right port in str')

        self.gfw = DFAFilter()
        self.gfw.parse()

        self.take_over = False
        self.temp_talker = wechaty.Contact

        self.logger.info('Drada plugin init success')

    def _file_check(self) -> bool:
        """check the config file"""

        if "directors.json" not in self.config_files:
            self.logger.warning(f'config file url:/{self.config_url} does not have directors.json!')
            return False

        if "focus.json" not in self.config_files:
            self.logger.warning(f'config file url:/{self.config_url} does not have focus.json!')
            return False

        if "MMrules.xlsx" not in self.config_files:
            self.logger.warning(f'config file url:/{self.config_url} does not have MMrules.xlsx!')
            return False

        if "memory.txt" not in self.config_files:
            self.logger.warning(f'config file url:/{self.config_url} does not have memory.txt!')
            return False

        if "scenarios.xlsx" not in self.config_files:
            self.logger.warning(f'config file url:/{self.config_url} does not have scenarios.xlsx!')
            return False

    def _load_memory(self) -> None or dict:
        """load the memory data"""
        memory_file = os.path.join(self.config_url, 'memory.txt')
        with open(memory_file, 'r', encoding='utf-8') as f:
            datas = [line.strip() for line in f.readlines() if line.strip()]

        if len(datas) == 0:
            self.logger.warning('no data in memory.txt,this is not allowed')
            return None

        focus = self.uie(datas)

        self_memory = {}
        for i in range(len(datas)):
            for result in focus[i].values():
                for entity in result:
                    if entity['text'] in self_memory.keys():
                        self_memory[entity['text']].append(datas[i])
                    else:
                        self_memory[entity['text']] = [datas[i]]

        return self_memory

    def _load_mmrules(self) -> None or dict:
        """load the Memory Mathmatics Rules from excel"""
        mmrules = os.path.join(self.config_url, 'MMrules.xlsx')
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

    def _load_scenarios(self) -> None or dict:
        """load the scenarios data"""
        scenarios_file = os.path.join(self.config_url, 'scenarios.xlsx')
        data = xlrd.open_workbook(scenarios_file)

        rules = {}
        for name in data.sheet_names():
            table = data.sheet_by_name(name)
            nrows = table.nrows
            if nrows == 0:
                continue

            cols = table.ncols
            for k in range(1, cols):
                if not table.cell_value(0,k):
                    self.logger.warning('cell of the first row is empty in scenario.xlsx,this is not allowed')
                    return None

            rules[name] = {}
            for i in range(1, nrows):
                for k in range(cols):
                    if k == 0:
                        if table.cell_value(i,k):
                            rule = table.cell_value(i,k)
                            rules[name][rule] = {}
                        else:
                            self.logger.warning('cell of the first column is empty in scenario.xlsx,this is not allowed')
                            return None
                        continue
                    rules[name][rule][table.cell_value(0,k)] = table.cell_value(i,k)
        return rules


    async def director_message(self, msg: Message):
        """
        Director Module
        the multy-media-message would be added in next stage
        """
        # 1. check the heartbeat of DramaPlugin
        if msg.text() == "ding":
            await msg.say('dong -- DramaPlugin')
            return
        # 2. help menu
        if msg.text() == 'help':
            await msg.say("Drama Director Code: /n"
                          "ding -- check heartbeat /n"
                          "reload directors --- reload director.json /n"
                          "reload MMrules -- reload MMrules.xlsx /n"
                          "reload SelfMemory -- reload memory.txt /n"
                          "reload scenarios -- reload scenarios.xlsx"
                          "save -- save the users status and users memory so that game will continue instead of restart/n"
                          "take over -- take over the AI for a time /n"
                          "take over off -- stop the take_over")
            return
        # 3.functions
        if msg.text() == 'reload directors':
            with open(os.path.join(self.config_url, 'directors.json'), 'r', encoding='utf-8') as f:
                directors = json.load(f)
            if len(directors) == 0:
                await msg.say('there must be at least one director, director list not changed')
            else:
                self.directors = directors
                await msg.say('Drama director list has been updated')
            return

        if msg.text() == 'reload MMrules':
            mmrules = self._load_mmrules()
            if mmrules is None:
                await msg.say("Drada MMrules.xlsx not valid, I'll keep the old set. no change happened")
            else:
                self.mmrules = mmrules
                await msg.say("Drada MMrules has been updated")
            return

        if msg.text() == 'reload SelfMemory':
            selfmemory = self._load_memory()
            if selfmemory is None:
                await msg.say("memory.txt is empty, so I will not change my memory")
            else:
                self.self_memory = selfmemory
                await msg.say("self memory has been updated")
            return

        if msg.text() == 'reload scenarios':
            scenarios = self._load_scenarios()
            if scenarios in None:
                await msg.say("scenarios.xlsx is empty, so I will not reload scenarios. No change happened")
            else:
                self.scenarios = scenarios
                await msg.say("scenarios has been updated")
            return

        if msg.text() == 'save':
            with open(os.path.join(self.config_url, 'users.json'), 'r', encoding='utf-8') as f:
                json.dump(self.users, f)
            with open(os.path.join(self.config_url, 'user_memory.json'), 'r', encoding='utf-8') as f:
                json.dump(self.user_memory, f)
            await msg.say(f"user status and memory has been saved in {self.config_url}. I'll read instead of create new till you delete the files")
            return

        if msg.text() == "take over":
            self.take_over = True
            await msg.say("ok your turn. to give the wheel back to me send: take over off")
            return

        if msg.text() == 'take over off':
            self.take_over = False
            await msg.say("I will take the talk again. to take over send: take over")
            return

        if self.take_over:
            await msg.forward(self.temp_talker)
        else:
            await msg.say("send help to me to check what you can do")


    def soul(self, text, talker_id):

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


    async def on_message(self, msg: Message) -> None:
        talker = msg.talker()

        # 1. 判断是否是自己发送的消息
        if talker.contact_id == msg.is_self() or msg.room():
            return

        # 2. check if is director
        if talker.contact_id in self.directors:
            await self.director_message(msg)
            return

        # 3. new-user register and old-user session load
        if talker.contact_id not in self.users.keys():
            self.users[talker.contact_id] = ['zhangwuji', 'yitiantulong', 'inturn']
            if self.multiuser:
                self.user_memory[talker.contact_id] = self.user_memory_template
            await talker.say("") #statement
            return

        # 4. message pre-process
        """
        1. 是否是文本消息，排除不支持的消息类型（目前只支持文本，另外支持一个emoj，emoj统一识别为
        第一条判定为greating，后面都判定为meaningless）
        3. 敏感词检测
        4. 去掉特殊符号，比如@ /n等
        5. 随机等待0~0.5秒，避免线程和api申请频率过高
        """
        if msg.type() not in [MessageType.MESSAGE_TYPE_TEXT, MessageType.MESSAGE_TYPE_EMOTICON]:
            return

        if msg.room():
            text = await msg.mention_text()
        else:
            text = msg.text()

        text = text.strip().replace('/n', '')

        if self.gfw.filter(text):
            self.logger.info(f'{text} is filtered, for the reason of {self.gfw.filter(text)}')
            await msg.say('请勿发表不当言论，谢谢配合')
            return

        # 5. check the status of the talker and load the scenario rule-sheet
        if self.users[talker.contact_id][2] == 'endofstory':
            await talker.say("")
            return

        character = self.users[talker.contact_id][0]
        memory = self.user_memory[talker.contact_id] if self.multiuser else self.user_memory
        rules = self.scenarios[self.users[talker.contact_id][1]]

        if 'welcome' in self.scenarios[self.users[talker.contact_id][1]].keys():
            if self.scenarios[self.users[talker.contact_id][1]]['welcome'][self.users[talker.contact_id][0]]:
                await talker.say(
                    self.scenarios[self.users[talker.contact_id][1]]['welcome'][self.users[talker.contact_id][0]][1:])


        # 6. intents and entity recognition

        # 7. ai sou1 response

        # colorful eggs https://ai.baidu.com/ai-doc/wenxin/Zl33wtflg


