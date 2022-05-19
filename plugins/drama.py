""""""
import os
from typing import (
    Optional, List,
)
from wechaty import (
    MessageType,
    WechatyPlugin,
    Message,
    WechatyPluginOptions
)
from wechaty_puppet import get_logger
from plugins.inspurai.inspurai import Yuan

class DramaPlugin(WechatyPlugin):
    """
    功能点：应用源1.0进行场景对话模拟
    授权的群或者我本人中发出的text，直接作为输入
    """
    def __init__(
        self,
        options: Optional[WechatyPluginOptions] = None,
        admin_id: List[str] = ["wxid_a6xxa7n11u5j22", "wxid_tnv0hd5hj3rs11"]) -> None:

        super().__init__(options)

        self.cache_dir = '.drama'
        os.makedirs(self.cache_dir, exist_ok=True)

        # 2. save the log info into <plugin_name>.log file
        log_file = os.path.join(self.cache_dir, self.name + '.log')
        self.logger = get_logger(log_file)
        
        # 3. save the admin status
        self.admin_id = admin_id
        
        # 4. cache the Room/Contact data
        self._rooms: List[str] = []

    async def on_message(self, msg: Message) -> None:

        if msg.is_self() or msg.type() != MessageType.MESSAGE_TYPE_TEXT:
            return

        talker = msg.talker()
        id = talker.contact_id

        if msg.text() =="ding":
            await msg.say('dong -- Drama')
            return

        if id in self.admin_id:
            if msg.room() and await msg.mention_self():
                if await msg.mention_text() == "觉醒":
                    await msg.say("演员已就位")
                    self._rooms.append(msg.room().room_id)
                    self.logger.info("add rooms"+msg.room().room_id)
                    return

        if msg.room():
            room = msg.room()
            if room.room_id not in self._rooms:
                return
        else:
            if id not in self.admin_id:
                return

        text = msg.text()
        self.logger.info(text)

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