from abc import ABC, abstractmethod
from pathlib import Path

class BaseWriter(ABC):
    """ Abstract base class for writing data to a file. """

    def __init__(self, output_file:str):
        if not output_file:
            raise ValueError("Output file path cannot be empty.")
        self.output_file = Path(output_file)

    @abstractmethod
    def write(self, data: list[dict]) -> None:
        """ Abstract method to write data to a file.
        Args:
            data (list[dict]): The data to be written to the file.
        """
        raise NotImplementedError("Subclasses must implement the write method.")

