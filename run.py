import asyncio
import os

from wechaty import Wechaty, WechatyOptions

from plugins.drama import DramaPlugin
from plugins.ding_dong import DingDongPlugin

if __name__ == "__main__":
    options = WechatyOptions(
        port=int(os.environ.get('PORT', 8004)),
    )
    bot = Wechaty(options)
    bot.use([
        DramaPlugin(),
        DingDongPlugin(),
    ])
    asyncio.run(bot.start())