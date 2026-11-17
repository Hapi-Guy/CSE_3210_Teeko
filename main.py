"""Teeko AI — run the game:  python main.py

pygame is imported inside main() so that benchmark worker processes (which
re-import this module on Windows) never load it.
"""

import multiprocessing


def main() -> None:
    from teeko.ui.app import App
    App().run()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
