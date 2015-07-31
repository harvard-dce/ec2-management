

class MatterhornCommunicationException(Exception):
    def __init__(self, code, value):
        self.code = int(code)
        self.value = value
    def __str__(self):
        return repr(self.value)
    def code(self):
        return self.code

