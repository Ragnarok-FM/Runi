import csv
from pathlib import Path


class AscensionTable:
    def __init__(self, path: str | Path):
        self.path = Path(path)

        self._col_headers: set[int] = set()
        self._data: dict[int, dict[int, int]] = {}

        self._is_single_row = False
        self._loaded = False

    def load(self):
        if self._loaded:
            return

        if not self.path.exists():
            raise FileNotFoundError(f"CSV not found: {self.path}")

        with self.path.open(newline='', encoding='utf-8') as f:
            reader = csv.reader(f)

            headers = next(reader)
            rows = list(reader)

            col_headers = [
                int(float(h.replace('%', '').strip()))
                for h in headers[1:]
            ]

            self._col_headers = set(col_headers)

            # Single-row table
            if len(rows) == 1:
                self._is_single_row = True

                values = rows[0][1:]

                self._data[0] = {
                    col: int(value.replace(',', '').strip())
                    for col, value in zip(col_headers, values)
                }

            # Matrix table
            else:
                for row in rows:
                    row_header = int(row[0])

                    self._data[row_header] = {
                        col: int(value.replace(',', '').strip())
                        for col, value in zip(col_headers, row[1:])
                    }

        self._loaded = True

    def get(self, *args) -> int:
        if not self._loaded:
            raise RuntimeError("Table not loaded")

        # Single-row table
        if self._is_single_row:
            col, = args

            if col not in self._col_headers:
                raise ValueError(f"Invalid column value: {col}")

            return self._data[0][col]

        # Matrix table
        row, col = args

        if row not in self._data:
            raise ValueError(f"Invalid row value: {row}")

        if col not in self._col_headers:
            raise ValueError(f"Invalid column value: {col}")

        return self._data[row][col]