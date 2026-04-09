from abc import ABC, abstractmethod
from langchain_core.language_models.chat_models import BaseChatModel

class BaseAgent(ABC):
    def __init__(self,name:str,model: BaseChatModel, description:str,instructions:str = ""):
        self.name=name
        self.model=model
        self.description=description
        self.instructions=instructions
    
    @abstractmethod
    def run(self, state):
        pass