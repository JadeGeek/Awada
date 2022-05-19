""""""
import os
import json
import urllib3
from typing import (
    Optional, List,
)
from wechaty import (
    MessageType,
    WechatyPlugin,
    Message,
    WechatyPluginOptions
)

http = urllib3.PoolManager()

from wechaty_puppet import get_logger

class DdpPlugin(WechatyPlugin):
    """
    功能点：测试ddparser
    """
    def __init__(
        self,
        options: Optional[WechatyPluginOptions] = None,
        sent_to: str = "无空") -> None:

        super().__init__(options)

        self.cache_dir = '.ddparser'
        os.makedirs(self.cache_dir, exist_ok=True)

        # 2. save the log info into <plugin_name>.log file
        log_file = os.path.join(self.cache_dir, self.name + '.log')
        self.logger = get_logger(log_file)
        
        # 3. save the admin status
        self.sent_to = sent_to

    async def on_message(self, msg: Message) -> None:

        if msg.is_self() or msg.type() != MessageType.MESSAGE_TYPE_TEXT:
            return

        if msg.text() =="ding":
            await msg.say('dong -- Ddparser')
            return

        text = msg.text()
        data = {'text': text}

        #contact = await self.bot.Contact.find(self.sent_to)
        #await contact.say(text)

        encoded_data = json.dumps(data)
        # for linux r = http.request('POST','http://0.0.0.0:5005/model/parse',body=encoded_data)
        res = http.request('POST', 'http://localhost:5005/model/parse', body=encoded_data)
        result = json.loads(res.data)

        if not result:
            self.logger.info("rasa failed")
            return

        intent = result['intent']['name']
        print(intent)
        print(result['entities'])

        if intent == "interr":
            await msg.say("对方好像有疑问，我应该找个合适的答案")
        elif intent == "asking":
            await msg.say("对方在让我做事，真懒得理他")
        elif intent == "state":
            await msg.say("对方在陈述，我应该倾听")
        elif intent == "rquestion":
            await msg.say("对方居然在反问，好想跟他杠到底")
        elif intent == "exclam":
            await msg.say("对方在感叹，我应该附和或者安慰")
        else:
            await msg.say("抱歉，没有识别出来，真很罕见")

        if result['entities']:
            for entity in result['entities']:
                await msg.say("entity find:"+ entity["value"]+ entity["entity"])