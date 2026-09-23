
from abc import ABC, abstractmethod

class LLMAdapter(ABC):
    @abstractmethod
    def stream(self, messages:list[dict]):
        pass
