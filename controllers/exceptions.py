

__all__ = [
    'ClusterException',
    'ScalingException',
    'GiveUpWaitingException',
    'MatterhornControllerException',
    'MatterhornCommunicationException'
]

class ClusterException(Exception):
    pass

class ScalingException(ClusterException):
    pass

class GiveUpWaitingException(ClusterException):
    pass

class MatterhornControllerException(Exception):
    pass

class MatterhornCommunicationException(MatterhornControllerException):
    pass

