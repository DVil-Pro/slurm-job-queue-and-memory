"""Entry point: python -m slurm_mem_gui"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from slurm_mem_gui.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
