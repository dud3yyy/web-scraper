import json

from writers.base_writer import BaseWriter


class JSONWriter(BaseWriter):
    """ Class for writing data to a JSON file. """

    def write(self, data: list[dict]) -> None:
        """ Method to write data to a JSON file.
        Args:
            data (list[dict]): The data to be written to the JSON file.
        """
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self.output_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
