import os
import re
import json
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
from antigen_bot.forward_config import Conversation, ConfigFactory
from antigen_bot.utils import remove_at_info
from utils import DFAFilter


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
            configs: str = 'drama_configs'
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

        self.mmrules = self._load_MMrules()
        if self.mmrule == {}:
            raise RuntimeError('Drada MMrules.xlsx not valid, pls refer to above info and try again')

        # 4. load self-memory data and create memory-dict for users
        self.self_memory, self.user_memory = self._load_memory()
        if self.self_memory == {} or self.user_memory == {}:
            raise RuntimeError('Drada memory.xlsx not valid, pls refer to above info and try again')

        # 5. test the rasa nlu server and compare the intents and entries with the meta/memory data
        self.rasa_nlu_server = 'http://localhost:5005/parse'


    def _file_check(self) -> bool:
        """check the config file"""
        if not os.path.exists(self.config_files):
            self.logger.warning(f'config file url does not exist! {self.config_files}')
            return False

        if not os.path.isdir(self.config_files):
            self.logger.warning(f'config file url is not a directory! {self.config_files}')
            return False

        if not os.listdir(self.config_files):
            self.logger.warning(f'config file url is empty:!{self.config_files}')
            return False

        if "directors.json" not in os.listdir(self.config_files):
            self.logger.warning(f'config file url does not have directors.json:!{self.config_files}')
            return False

        if "MMrules.xlsx" not in os.listdir(self.config_files):
            self.logger.warning(f'config file url does not have MMrules.xlsx:!{self.config_files}')
            return False

        if "memory.xlsx" not in os.listdir(self.config_files):
            self.logger.warning(f'config file url does not have memory.xlsx:!{self.config_files}')
            return False

        if "scenarios.xlsx" not in os.listdir(self.config_files):
            self.logger.warning(f'config file url does not have scenarios.xlsx:!{self.config_files}')
            return False

    def _load_memory(self) -> dict:
        """load the memory data and create memory-dict for users"""
        memory_file = os.path.join(self.config_files, 'memory.xlsx')
        data = xlrd.open_workbook(memory_file)
        table = data.sheets()[0]

        nrows = table.nrows
        if nrows == 0:
            self.logger.warning(f'no memory data in {memory_file},this is not allowed')
            return {},{}

        self_memory = {}
        user_memory = {}

        for i in range(nrows):
            k,v = table.row_values(i)
            if k and v:
                self_memory[k] = v
                user_memory[k] = []
            else:
                self.logger.warning(f'{k} or {v} is empty in {memory_file}')
                return {},{}

        return self_memory, user_memory

    def _load_MMrules(self) -> dict:
        """load the Memory Mathmatics Rules from excel"""
        MMrules = os.path.join(self.config_files, 'MMrules.xlsx')
        data = xlrd.open_workbook(scenarios_file)
        table = data.sheets()[0]

        nrows = table.nrows
        if nrows == 0:
            self.logger.warning(f'no memory data in {memory_file},this is not allowed')
            return {}

        cols = table.ncols

        if table.cell_value(0,1).lower() != 'read' or table.cell_value(0,2).lower() != 'bi':
            self.logger.warning(f'{MMrules} is not in the right format')
            return {}

        rules = {}
        for i in range(1, nrows):
            for k in range(cols):
                if k == 0:
                    if table.cell_value(i,k).isalpha():
                        intent = table.cell_value(i,k)
                        rules[intent] = {}
                    else:
                        self.logger.warning(f'{MMrules} is not in the right format')
                        return {}
                    continue
                if table.cell_value(i,k).lower() not in ['yes','no']:
                    self.logger.warning(f'{MMrules} is not in the right format')
                    return {}
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
            self.logger.warning(f'no memory data in {memory_file},this is not allowed')
            return {}

        cols = table.ncols

        for k in range(1, cols):
            if not table.cell_value(0,k):
                self.logger.warning(f'{k}th column is empty in {scenarios_file},this is not allowed')
                return {}

        rules = {}
        for i in range(1, nrows):
            for k in range(cols):
                if k == 0:
                    if table.cell_value(i,k):
                        rule = table.cell_value(i,k)
                        rules[rule] = {}
                    else:
                        self.logger.warning(f'cell({k},{v}) is empty in {memory_file},this is not allowed')
                        return {}
                    continue
                rules[rule][table.cell_value(0,k)] = table.cell_value(i,k)

        return rules


    async def director_message(self, msg: Message, conversation_id: str):
        """forward the message to the target conversations
        Args:
            msg (Message): the message to forward
            conversation_id (str): the id of conversation
        """
        # 1. get the type of message
        conversations = self.admin_status.get(conversation_id, [])
        if not conversations:
            return

        file_box = None
        if msg.type() in [MessageType.MESSAGE_TYPE_IMAGE, MessageType.MESSAGE_TYPE_VIDEO,
                          MessageType.MESSAGE_TYPE_ATTACHMENT]:
            file_box = await msg.to_file_box()
            file_path = os.path.join(self.file_cache_dir, file_box.name)

            await file_box.to_file(file_path, overwrite=True)
            file_box = FileBox.from_file(file_path)
#记得读取记忆的时候，如果people的名称本身也是一个entity的话，那么要把相关的记忆也加进来
        for conversation in conversations:
            if conversation.type == 'Room':
                forwarder_target = await self.bot.Room.load(conversation.id)
            elif conversation.type == 'Contact':
                forwarder_target = await self.bot.Contact.load(conversation.id)
            else:
                continue

            # TODO: 转发图片貌似还是有些问题
            if file_box:
                await forwarder_target.say(file_box)

            # 如果是文本的话，是需要单独来转发
            elif msg.type() == MessageType.MESSAGE_TYPE_TEXT:
                await forwarder_target.say(msg.text())

            elif forwarder_target:
                await msg.forward(forwarder_target)


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
        1. 是否是文本消息，排除不支持的消息类型（目前只支持文本）
        2. 预设声明发送（eg首次使用隐私声明）
        3. 敏感词检测
        """
        
        # 4. check the status of the talker and load the scenario rule-sheet



        # 5. the soul


        text = msg.text()
        if room:
            conversation_id = room.room_id
        else:
            conversation_id = talker.contact_id

        # at 条件触发
        if conversation_id not in self.admin_status and self.trigger_with_at:
            mention_self = await msg.mention_self()
            if not mention_self:
                return
            text = remove_at_info(text=text)

        if conversation_id in self.admin_status:
            await self.forward_message(msg, conversation_id=conversation_id)
            self.admin_status.pop(conversation_id)
            return

        # filter the target conversations

        if text.startswith(self.command_prefix):
            # parse token & command
            text = text[len(self.command_prefix):]
            text = text[text.index('#') + 1:].strip()

            receivers = self.config_factory.get_receivers(conv)
            if not receivers:
                return

            self.admin_status[conversation_id] = receivers

            if text:
                # set the words to the message
                msg.payload.text = text
                await self.forward_message(msg, conversation_id=conversation_id)
                self.admin_status.pop(conversation_id)