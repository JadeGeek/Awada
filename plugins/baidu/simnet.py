import requests
import json
import os
import paddlehub as hub

class SimNet():
    """
    ai.baidu.com/https://ai.baidu.com/ai-doc/NLP/ek6z52frp
    simnet poewred by Ernie2.0
    """

    def __init__(self):
        AK, SK = os.environ.g.split('||')
        host = 'https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id='+AK+'&client_secret='+SK
        response = requests.get(host)
        token = access["access_token"]
        print("token got",token)
        self.headers = {'Content-Type': 'application/json'}
        self.request_url = "https://aip.baidubce.com/rpc/2.0/nlp/v2/simnet?charset=UTF-8access_token="+token

    def predict(self, text1, text2):
        data = {"text_1": text1, "text_2": text2, "model": "ERNIE"}
        response = requests.post(self.request_url, headers=self.headers, data=json.dumps(data))
        if response:
            print(response.json())
        return response.json()

if __name__ == "__main__":
    import time
    ernie = SimNet()
    bow = hub.Module(name="simnet_bow")

    print("====Simnet Test====")

    while (1):
        print("输入Q退出")
        prompt1 = input("输入待测文本1：")
        if prompt1.lower() == "q":
            break

        prompt2 = input("输入待测文本2：")
        if prompt2.lower() == "q":
            break

        time0 = time.time()
        result1 = ernie.predict(prompt1, prompt2)
        if result1:
            print("ERNIE:")
            print(result1)
        time1 = time.time()
        print('总共耗时：' + str(time1 - time0) + 's')

        time2 = time.time()
        test_text = [prompt1, prompt2]
        result2 = bow.similarity(texts=test_text, use_gpu=True)
        if result2:
            print("Bow:")
            print(result2)
        time3 = time.time()
        print('总共耗时：' + str(time3 - time2) + 's')